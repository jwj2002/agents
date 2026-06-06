#!/usr/bin/env python3
"""
Stop hook: capture universal session-level telemetry.

Fires at every session end, parses the transcript for artifact evidence,
classifies work-type (implementation / deliberative / ops), writes a heartbeat
file for the dead-man's-switch watchdog, and appends a structured session
record to the per-host shard.

Build order item 1 from specs/telemetry-validation.md §5.

Always exits 0 (fail-open). Stdlib-only.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    """Append a timestamped line to ~/.claude/hooks.log."""
    try:
        log_path = Path.home() / ".claude" / "hooks.log"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(
                f"[{datetime.now().isoformat()}] capture_session_telemetry: {msg}\n"
            )
    except Exception:
        pass


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with microsecond precision (mirrors state_manager)."""
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _get_host_name() -> str:
    """Read canonical host name (mirrors aggregate_metrics_to_global.py)."""
    host_name_path = Path.home() / ".claude" / "host-name"
    try:
        text = host_name_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except FileNotFoundError:
        pass
    import socket
    return (socket.gethostname() or "unknown").split(".")[0].lower()


def _append_jsonl_fsync(target: Path, record: dict) -> None:
    """Append one JSON line to target; fsync for durability (mirrors state_manager)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# File extensions that count as "code" edits (not docs/config-only)
SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb",
    ".java", ".sh", ".c", ".cpp", ".h", ".hpp", ".cs", ".kt",
    ".swift", ".scala", ".clj", ".ex", ".exs",
}

# Keywords in first user message that signal deliberative work
_SPEC_KEYWORDS = {
    "spec", "design", "plan", "research", "review", "discuss",
    "architecture", "proposal", "rfc", "analysis", "investigate",
    "brainstorm", "strategy", "evaluate", "assessment",
}


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------


def _parse_transcript(transcript_path: str) -> dict:
    """Parse a JSONL transcript and return structured artifact evidence.

    Returns a dict with keys:
      files_touched: list of file paths written/edited
      pr_links: list of PR URL strings
      issue_refs: list of issue numbers (int)
      bash_patterns: list of Bash command strings seen
      has_code_edits: bool — Write/Edit to a source-code file
      has_pr_link: bool
      has_test_run: bool
      has_commit: bool
      first_user_text: str — text of first user turn (empty if none)
    """
    evidence: dict = {
        "files_touched": [],
        "pr_links": [],
        "issue_refs": [],
        "bash_patterns": [],
        "has_code_edits": False,
        "has_pr_link": False,
        "has_test_run": False,
        "has_commit": False,
        "first_user_text": "",
    }

    try:
        path = Path(transcript_path).expanduser()
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue

                entry_type = entry.get("type", "")

                # pr-link entries
                if entry_type == "pr-link":
                    pr_url = entry.get("prUrl", "")
                    if pr_url:
                        evidence["pr_links"].append(pr_url)
                        evidence["has_pr_link"] = True
                    continue

                # First user message text (for deliberative signal)
                if entry_type == "user" and not evidence["first_user_text"]:
                    content = entry.get("message", {}).get("content", "")
                    if isinstance(content, str):
                        evidence["first_user_text"] = content[:500]
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                evidence["first_user_text"] = block.get("text", "")[:500]
                                break

                # Assistant messages — tool_use items
                if entry_type == "assistant":
                    msg = entry.get("message", {})
                    content_list = msg.get("content", [])
                    if not isinstance(content_list, list):
                        continue
                    for block in content_list:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_use":
                            continue
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {}) or {}

                        if tool_name in ("Write", "Edit"):
                            file_path = tool_input.get("file_path", "")
                            if file_path:
                                evidence["files_touched"].append(file_path)
                                if Path(file_path).suffix.lower() in SOURCE_EXTS:
                                    evidence["has_code_edits"] = True

                        elif tool_name == "Bash":
                            cmd = tool_input.get("command", "")
                            if cmd:
                                evidence["bash_patterns"].append(cmd[:300])
                                if "git commit" in cmd or "git push" in cmd:
                                    evidence["has_commit"] = True
                                if "pytest" in cmd or " test" in cmd.lower():
                                    evidence["has_test_run"] = True

    except OSError as exc:
        log(f"_parse_transcript: cannot read {transcript_path}: {exc}")
        evidence["_parse_error"] = str(exc)
    except Exception as exc:
        log(f"_parse_transcript: unexpected error: {exc}")
        evidence["_parse_error"] = str(exc)

    # Extract issue refs from pr_links and first_user_text
    _extract_issue_refs(evidence)

    return evidence


def _extract_issue_refs(evidence: dict) -> None:
    """Populate evidence['issue_refs'] from pr_links and first_user_text."""
    import re
    refs: set = set()
    pattern = re.compile(r"#(\d+)")

    for url in evidence.get("pr_links", []):
        for m in pattern.finditer(url):
            refs.add(int(m.group(1)))

    text = evidence.get("first_user_text", "")
    for m in pattern.finditer(text):
        refs.add(int(m.group(1)))

    evidence["issue_refs"] = sorted(refs)


# ---------------------------------------------------------------------------
# Work-type classification
# ---------------------------------------------------------------------------


def _has_spec_keywords(text: str) -> bool:
    """Return True if text contains deliberative-work keywords."""
    lower = text.lower()
    return any(kw in lower for kw in _SPEC_KEYWORDS)


def _classify_work_type(evidence: dict) -> tuple[str, list]:
    """Classify work_type and compute watchdog flags from artifact evidence.

    Returns:
        (work_type, flags)
        work_type: "implementation" | "deliberative" | "ops"
        flags: list of flag strings (e.g. ["implementation-like-but-excluded"])
    """
    has_code_edits = evidence.get("has_code_edits", False)
    has_pr_link = evidence.get("has_pr_link", False)
    has_test_run = evidence.get("has_test_run", False)
    has_commit = evidence.get("has_commit", False)
    issue_refs = evidence.get("issue_refs", [])
    first_user_text = evidence.get("first_user_text", "")

    if has_code_edits or has_pr_link or has_commit or has_test_run:
        work_type = "implementation"
    elif issue_refs or _has_spec_keywords(first_user_text):
        work_type = "deliberative"
    else:
        work_type = "ops"

    # §2.5 watchdog: deliberative session that also has code edits
    flags: list = []
    if work_type == "deliberative" and has_code_edits:
        flags.append("implementation-like-but-excluded")

    return work_type, flags


# ---------------------------------------------------------------------------
# Task attribution
# ---------------------------------------------------------------------------


def _get_task_attribution() -> dict:
    """Derive task attribution from PERSISTENT_STATE.yaml or git branch.

    Returns a dict with keys: issue, branch, phase, source.
    Fails open: returns a stub dict if nothing is readable.
    """
    attribution = {
        "issue": None,
        "branch": None,
        "phase": None,
        "source": "none",
    }

    # Try PERSISTENT_STATE.yaml via CLAUDE_PROJECT_DIR
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    state_path = project_dir / "PERSISTENT_STATE.yaml"
    try:
        import yaml  # type: ignore[import-untyped]
        if state_path.exists():
            state = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
            issue = state.get("issue") or state.get("issue_number")
            phase = state.get("phase") or state.get("current_phase")
            if issue is not None:
                attribution["issue"] = int(issue)
                attribution["phase"] = str(phase) if phase else None
                attribution["source"] = "PERSISTENT_STATE"
    except ImportError:
        pass  # PyYAML not available — fall through to git
    except Exception as exc:
        log(f"_get_task_attribution: YAML parse error (non-fatal): {exc}")

    # Try git branch for issue number and branch name
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = result.stdout.strip()
        if branch:
            attribution["branch"] = branch
            if attribution["source"] == "none":
                # Parse issue number from branch name e.g. feat/issue-229-slug
                import re
                m = re.search(r"issue[-_](\d+)", branch, re.IGNORECASE)
                if m:
                    attribution["issue"] = int(m.group(1))
                    attribution["source"] = "git_branch"
    except Exception as exc:
        log(f"_get_task_attribution: git branch failed (non-fatal): {exc}")

    return attribution


# ---------------------------------------------------------------------------
# Boundary computation
# ---------------------------------------------------------------------------


def _compute_boundary(evidence: dict, task_attribution: dict, recorded_at: str) -> dict:
    """Compute task boundary frozen_at value from artifact evidence.

    Returns a dict: {frozen_at: str, frozen_recorded_at: str}
    frozen_at values: "intake" | "first_impl_artifact" | "none"
    """
    # If we already have attribution (issue from PERSISTENT_STATE or git branch),
    # the task boundary was established at intake.
    if task_attribution.get("issue") is not None:
        return {
            "frozen_at": "intake",
            "frozen_recorded_at": recorded_at,
        }

    # If we have code edits, commits, or a PR link, boundary is at first impl artifact.
    has_code_edits = evidence.get("has_code_edits", False)
    has_pr_link = evidence.get("has_pr_link", False)
    has_commit = evidence.get("has_commit", False)
    has_test_run = evidence.get("has_test_run", False)

    if has_code_edits or has_pr_link or has_commit or has_test_run:
        return {
            "frozen_at": "first_impl_artifact",
            "frozen_recorded_at": recorded_at,
        }

    return {
        "frozen_at": "none",
        "frozen_recorded_at": recorded_at,
    }


# ---------------------------------------------------------------------------
# Prior session loading (for boundary freeze idempotency)
# ---------------------------------------------------------------------------


def _load_prior_session(session_id: str, host: str) -> dict | None:
    """Return the most recent prior record for session_id from the shard, or None."""
    agents_root = Path.home() / "agents"
    shard_file = agents_root / "telemetry" / host / "sessions.jsonl"
    if not shard_file.exists():
        return None
    try:
        prior = None
        with open(shard_file, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("session_id") == session_id:
                    prior = rec
        return prior
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Heartbeat + session record writers
# ---------------------------------------------------------------------------


def _write_heartbeat(host: str, session_id: str, recorded_at: str) -> None:
    """Write/overwrite the capture heartbeat file for the dead-man's-switch watchdog."""
    agents_root = Path.home() / "agents"
    heartbeat_dir = agents_root / "telemetry" / host
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_path = heartbeat_dir / "capture_heartbeat.json"
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "host": host,
        "recorded_at": recorded_at,
    }
    try:
        with open(heartbeat_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
    except OSError as exc:
        log(f"_write_heartbeat: failed (non-fatal): {exc}")


def _write_session_record(record: dict, host: str) -> None:
    """Append a session record to the per-host sessions.jsonl shard."""
    agents_root = Path.home() / "agents"
    shard_path = agents_root / "telemetry" / host / "sessions.jsonl"
    try:
        _append_jsonl_fsync(shard_path, record)
    except OSError as exc:
        log(f"_write_session_record: failed (non-fatal): {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    try:
        # Drain stdin as expected by the Stop hook contract.
        raw_stdin = sys.stdin.read() if not sys.stdin.isatty() else "{}"
        try:
            hook_in = json.loads(raw_stdin) if raw_stdin.strip() else {}
        except json.JSONDecodeError:
            hook_in = {}

        session_id = hook_in.get("session_id", "unknown")
        transcript_path = hook_in.get("transcript_path", "")

        recorded_at = _utc_now_iso()
        host = _get_host_name()

        # Parse transcript for artifact evidence
        flags_extra: list = []
        if transcript_path:
            evidence = _parse_transcript(transcript_path)
            if "_parse_error" in evidence:
                flags_extra.append("transcript_unavailable")
        else:
            evidence = {
                "files_touched": [],
                "pr_links": [],
                "issue_refs": [],
                "bash_patterns": [],
                "has_code_edits": False,
                "has_pr_link": False,
                "has_test_run": False,
                "has_commit": False,
                "first_user_text": "",
            }
            flags_extra.append("transcript_unavailable")

        # Derive task attribution
        task_attribution = _get_task_attribution()

        # Classify work type
        work_type, flags = _classify_work_type(evidence)
        flags = flags + flags_extra

        # Load any prior record for this session (boundary freeze idempotency)
        prior = _load_prior_session(session_id, host)

        # Compute boundary — carry forward if already frozen
        if (
            prior is not None
            and isinstance(prior.get("boundary"), dict)
            and prior["boundary"].get("frozen_at", "none") != "none"
        ):
            boundary = prior["boundary"]
        else:
            boundary = _compute_boundary(evidence, task_attribution, recorded_at)

        # Build the session record
        record: dict = {
            "schema_version": 1,
            "event_type": "session_capture",
            "session_id": session_id,
            "host": host,
            "recorded_at": recorded_at,
            "work_type": work_type,
            "flags": flags,
            "task_attribution": {
                "issue": task_attribution.get("issue"),
                "branch": task_attribution.get("branch"),
                "phase": task_attribution.get("phase"),
                "source": task_attribution.get("source", "none"),
            },
            "artifact_evidence": {
                "files_touched": evidence.get("files_touched", []),
                "pr_links": evidence.get("pr_links", []),
                "issue_refs": evidence.get("issue_refs", []),
                "bash_patterns": evidence.get("bash_patterns", []),
                "has_code_edits": evidence.get("has_code_edits", False),
                "has_pr_link": evidence.get("has_pr_link", False),
                "has_test_run": evidence.get("has_test_run", False),
            },
            "boundary": boundary,
        }

        # Write heartbeat (overwrite each run)
        _write_heartbeat(host, session_id, recorded_at)

        # Append session record to host shard
        _write_session_record(record, host)

        log(
            f"done — session={session_id} host={host} work_type={work_type} "
            f"files={len(evidence.get('files_touched', []))} "
            f"flags={flags} boundary={boundary['frozen_at']}"
        )

    except Exception as exc:
        log(f"error (non-fatal): {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
