#!/usr/bin/env python3
"""
Centralized state manager for PERSISTENT_STATE.yaml + outcome recording.

Used by: orchestrate command (inline), precompact hook, sessionstart hook.

Two responsibilities:
1. PERSISTENT_STATE.yaml read/write (active_work tracking)
2. Outcome recording — append to .claude/memory/{metrics,failures}.jsonl
   after PROVE returns. Recording is the orchestrator's job, NOT PROVE's,
   so the write is deterministic across runs (see issue #104).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

_log_file = Path.home() / ".claude" / "hooks.log"
logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [state_manager] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _state_path(project_dir: Path) -> Path:
    return project_dir / ".agents" / "outputs" / "claude_checkpoints" / "PERSISTENT_STATE.yaml"


def load_state(project_dir: Path) -> dict:
    """Read PERSISTENT_STATE.yaml and return its contents as a dict."""
    if not HAS_YAML:
        return {}
    path = _state_path(project_dir)
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logging.warning(f"Failed to load state: {e}")
        return {}


def _write_state(project_dir: Path, data: dict) -> None:
    """Write state dict back to PERSISTENT_STATE.yaml."""
    if not HAS_YAML:
        return
    path = _state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def update_phase(project_dir: Path, issue: int, branch: str, phase: str, action: str,
                  worktree_path: str | None = None) -> None:
    """Update active_work with current phase. Tracks completed phases for --resume.

    Args:
        worktree_path: Absolute path to worktree (--parallel mode only). None for normal mode.
    """
    data = load_state(project_dir)
    active = data.get("active_work", {})

    # Track the previous phase as completed (if transitioning)
    prev_phase = active.get("phase")
    completed = active.get("completed_phases", [])
    if prev_phase and prev_phase != phase and prev_phase not in completed:
        completed.append(prev_phase)

    # Preserve existing worktree_path if not explicitly provided
    if worktree_path is None:
        worktree_path = active.get("worktree_path")

    data["active_work"] = {
        "issue": issue,
        "branch": branch,
        "phase": phase,
        "last_action": action,
        "completed_phases": completed,
        "worktree_path": worktree_path,
    }

    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_state(project_dir, data)


def clear_active(project_dir: Path, issue: int) -> None:
    """Clear active workflow state after successful completion."""
    data = load_state(project_dir)
    data["active_work"] = {
        "issue": None,
        "branch": "main",
        "phase": None,
        "last_action": f"Completed issue #{issue}",
        "completed_phases": [],
        "worktree_path": None,
    }

    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_state(project_dir, data)


def get_completed_phases(project_dir: Path, issue: int) -> list[str]:
    """Get list of completed phases for an issue. Used by --resume."""
    data = load_state(project_dir)
    active = data.get("active_work", {})
    if active.get("issue") != issue:
        return []
    return active.get("completed_phases", [])


def get_worktree_for_issue(project_dir: Path, issue: int) -> str | None:
    """Get worktree path for an issue from persisted state. Used by --resume."""
    data = load_state(project_dir)
    active = data.get("active_work", {})
    if active.get("issue") != issue:
        return None
    return active.get("worktree_path")


def get_active_work(project_dir: Path) -> dict:
    """Get the active_work section. Used by sessionstart hook."""
    data = load_state(project_dir)
    return data.get("active_work", {})


def update_from_extracted(project_dir: Path, extracted: dict) -> None:
    """Update state from precompact transcript extraction."""
    data = load_state(project_dir)

    if "active_work" not in data:
        data["active_work"] = {}

    if extracted.get("last_issue"):
        data["active_work"]["issue"] = extracted["last_issue"]
    if extracted.get("last_phase"):
        data["active_work"]["phase"] = extracted["last_phase"]
    if extracted.get("artifacts_created"):
        data["active_work"]["last_action"] = f"Created {extracted['artifacts_created'][-1]}"

    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["updated"] = datetime.now().strftime("%Y-%m-%d")

    _write_state(project_dir, data)


# ---------------------------------------------------------------------------
# Outcome recording (issue #104)
# ---------------------------------------------------------------------------
#
# Recording is the orchestrator's job, not PROVE's. PROVE produces the data
# (status / complexity / stack / agents_run / root_cause via its artifact
# frontmatter); the orchestrator calls these helpers to perform the write.
# This makes recording deterministic — a long PROVE prompt can no longer
# elide the tail-end echo command (the failure pattern documented in #104).
#
# Idempotency: callers should invoke each function exactly once per outcome.
# These helpers do NOT dedupe internally — appending two records for the
# same issue (e.g., a re-run that produces a second BLOCKED record) is
# meaningful history, not a duplicate.
#
# Failure mode: fail-open. If the JSONL file can't be written (permissions,
# read-only filesystem, etc.) we log a warning to ~/.claude/hooks.log and
# return None. Losing one metric line is acceptable; failing a successful
# orchestrate run because we couldn't write a metric is not.

def _memory_dir(project_dir: Path) -> Path:
    return project_dir / ".claude" / "memory"


def _append_jsonl(target: Path, record: dict) -> None:
    """Append one JSON line to ``target``, creating parent dirs if needed.

    Uses append mode so concurrent ``--parallel`` orchestrate runs don't
    clobber each other. ``fsync`` after write so a crash doesn't lose the
    line. Single-line JSON writes ≤ PIPE_BUF are atomic on POSIX.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # fsync can fail on some filesystems (e.g. /tmp on macOS,
            # NFS mounts). The write itself succeeded; safe to ignore.
            pass


def record_metrics(
    project_dir: Path,
    issue: int,
    status: str,
    complexity: str,
    stack: str,
    agents_run: list[str],
    duration_seconds: int | None = None,
    root_cause: str | None = None,
    blocking_agent: str | None = None,
    agent_versions: dict[str, str] | None = None,
    first_pass_correct: bool | None = None,
    corrections: list | None = None,
) -> None:
    """Append a single record to ``.claude/memory/metrics.jsonl``.

    Schema matches the existing 2 records (subset of _base.md §11):
        {"issue":N,"date":"YYYY-MM-DD","status":"PASS|BLOCKED",
         "complexity":"...","stack":"...","agents_run":[...]}

    Optional fields (root_cause, blocking_agent, duration_seconds,
    agent_versions, first_pass_correct, corrections) are included only
    when supplied — keeps a PASS record compact and parseable by
    /learn's existing jq filters.

    Args:
        project_dir: Project root. The file lives at
            ``<project_dir>/.claude/memory/metrics.jsonl``.
        issue: GitHub issue number.
        status: "PASS" or "BLOCKED".
        complexity: "TRIVIAL", "SIMPLE", or "COMPLEX".
        stack: "backend", "frontend", or "fullstack".
        agents_run: Ordered list of phase names (e.g.
            ["MAP-PLAN", "PATCH", "PROVE"]).
        duration_seconds: Optional total wall-clock duration.
        root_cause: Required if ``status == "BLOCKED"``. One of the
            codes from ``_base.md`` §10.
        blocking_agent: Which agent surfaced the BLOCKED outcome
            (usually "PROVE"). Recorded only when status is BLOCKED.
        agent_versions: Optional version map, e.g. {"prove": "1.5"}.
        first_pass_correct: True if the issue required no post-PROVE
            corrections; False if a correction was recorded via
            /correction. Absent on the initial PASS record (field
            added retroactively by flip_to_correction).
        corrections: List of correction reason strings. Only present
            after /correction has been run at least once.

    Returns: None. Errors are logged to ``~/.claude/hooks.log``; the
    function never raises into the orchestrator.
    """
    record: dict = {
        "issue": int(issue),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "complexity": complexity,
        "stack": stack,
        "agents_run": list(agents_run),
    }
    if duration_seconds is not None:
        record["duration_seconds"] = int(duration_seconds)
    if root_cause:
        record["root_cause"] = root_cause
    if blocking_agent:
        record["blocking_agent"] = blocking_agent
    if agent_versions:
        record["agent_versions"] = dict(agent_versions)
    if first_pass_correct is not None:
        record["first_pass_correct"] = first_pass_correct
    if corrections is not None:
        record["corrections"] = list(corrections)

    target = _memory_dir(project_dir) / "metrics.jsonl"
    try:
        _append_jsonl(target, record)
    except OSError as e:
        logging.warning(f"record_metrics: could not append to {target}: {e}")


def record_failure(
    project_dir: Path,
    issue: int,
    root_cause: str,
    files: list[str] | None = None,
    agent: str | None = None,
    prevention: str | None = None,
    details: str | None = None,
    fix: str | None = None,
) -> None:
    """Append a single record to ``.claude/memory/failures.jsonl``.

    Schema follows ``_base.md`` §12:
        {"issue":N,"date":"YYYY-MM-DD","root_cause":"...",
         "files":[...],"agent":"...","prevention":"...",
         "details":"...","fix":"..."}

    Only ``issue``, ``date``, and ``root_cause`` are mandatory; everything
    else is included only if supplied. /learn's clustering reads
    ``root_cause`` and (optionally) ``files``.

    Args:
        project_dir: Project root.
        issue: GitHub issue number.
        root_cause: One of the codes from ``_base.md`` §10
            (ENUM_VALUE, COMPONENT_API, MULTI_MODEL, ...).
        files: Files involved in the failure.
        agent: Which agent's work failed (usually "PATCH").
        prevention: Brief prevention recommendation for next time.
        details: Free-form description of what went wrong.
        fix: What was done (or needs to be done) to unblock.

    Returns: None. Fails open with a logged warning on IOError.
    """
    record: dict = {
        "issue": int(issue),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "root_cause": root_cause,
    }
    if files:
        record["files"] = list(files)
    if agent:
        record["agent"] = agent
    if prevention:
        record["prevention"] = prevention
    if details:
        record["details"] = details
    if fix:
        record["fix"] = fix

    target = _memory_dir(project_dir) / "failures.jsonl"
    try:
        _append_jsonl(target, record)
    except OSError as e:
        logging.warning(f"record_failure: could not append to {target}: {e}")


def flip_to_correction(
    project_dir: Path,
    issue: int,
    reason: str,
    emit_failure: bool = True,
) -> bool:
    """Find the most-recent metrics record for ``issue`` and append a
    corrected copy with ``first_pass_correct=False`` and
    ``corrections=[reason]``.

    The original record is preserved (append-only invariant). The new
    record is the canonical one — /learn and agent_metrics read the
    most-recent record per issue.

    Args:
        project_dir: Project root.
        issue: GitHub issue number to flip.
        reason: Human-readable description of what was missed.
        emit_failure: If True (default), also append a
            FIRST_PASS_DEFECT entry to failures.jsonl.

    Returns:
        True if a record was found and the correction was appended.
        False if no record for ``issue`` was found (logs a warning).
        Fails open on IOError (logs warning, returns False).
    """
    issue = int(issue)
    target = _memory_dir(project_dir) / "metrics.jsonl"
    try:
        if not target.exists():
            logging.warning(
                f"flip_to_correction: metrics.jsonl not found at {target}"
            )
            return False

        lines = [l for l in target.read_text(encoding="utf-8").splitlines() if l.strip()]
        last_record: dict | None = None
        for line in lines:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("issue") == issue:
                last_record = rec

        if last_record is None:
            logging.warning(
                f"flip_to_correction: no metrics record found for issue #{issue}"
            )
            return False

        # Build the corrected record from the last one.
        corrected = dict(last_record)
        corrected["date"] = datetime.now().strftime("%Y-%m-%d")
        corrected["first_pass_correct"] = False
        existing = corrected.get("corrections")
        if isinstance(existing, list):
            corrected["corrections"] = existing + [reason]
        else:
            corrected["corrections"] = [reason]

        _append_jsonl(target, corrected)

        if emit_failure:
            record_failure(
                project_dir,
                issue,
                "FIRST_PASS_DEFECT",
                details=reason,
            )

        return True

    except OSError as e:
        logging.warning(f"flip_to_correction: IOError for issue #{issue}: {e}")
        return False


# ---------------------------------------------------------------------------
# Derive agents_run from artifact directory (issue #107)
# ---------------------------------------------------------------------------
#
# The orchestrator's Step 4 needs the ordered list of phase names that
# actually ran for an issue. Tracking that across phase dispatches is
# error-prone (the orchestrator command is stateless between agent calls),
# so we derive it after the fact from `.agents/outputs/`. Every agent that
# ran wrote a `<phase>-<issue>-<mmddyy>.md` artifact — the directory IS the
# ground truth for what ran.

# Compiled per-call (issue number is variable). Match `<phase>-<issue>-NNNNNN.md`
# where phase is lowercase letters with optional hyphens (map, map-plan,
# plan-check, test-plan, etc.) and the date is exactly 6 digits.
_PHASE_RE_TEMPLATE = r"^([a-z\-]+)-{issue}-\d{{6}}\.md$"


def derive_agents_run(project_dir: Path, issue: int) -> list[str]:
    """Scan ``.agents/outputs/`` for this issue's artifact files; return phase
    names in mtime order.

    Each agent that ran wrote a ``<phase>-<issue>-<mmddyy>.md`` artifact.
    Reading the directory is the ground truth for what actually ran — more
    reliable than tracking state across phase dispatches in the orchestrator
    command (which is stateless between Task() calls).

    Phase name mapping: filename stem → uppercase canonical name.
    Examples::

        map-184-042926.md          → MAP
        map-plan-184-042926.md     → MAP-PLAN
        plan-check-184-042926.md   → PLAN-CHECK
        test-plan-184-042926.md    → TEST-PLAN

    Args:
        project_dir: Project root. Artifacts live under
            ``<project_dir>/.agents/outputs/``.
        issue: GitHub issue number.

    Returns:
        Ordered list of uppercase phase names. Empty list if the
        ``.agents/outputs/`` directory doesn't exist or no matching
        artifacts are found.
    """
    out_dir = project_dir / ".agents" / "outputs"
    if not out_dir.is_dir():
        return []

    pattern = re.compile(_PHASE_RE_TEMPLATE.format(issue=issue))

    # Glob first (fast directory scan), then regex-validate each name.
    # The glob is permissive — it catches anything matching the issue stem;
    # the regex enforces the actual `<phase>-<issue>-NNNNNN.md` shape and
    # rejects oddities like `random-1234-thing.md`.
    matches: list[tuple[float, str]] = []
    for p in out_dir.glob(f"*-{issue}-*.md"):
        m = pattern.match(p.name)
        if not m:
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            # Fail open: if we can't stat the file, skip rather than raise.
            continue
        matches.append((mtime, m.group(1).upper()))

    # Sort by mtime to preserve actual execution order. Alphabetical sort
    # would put `map` after `map-plan`; mtime is more honest about what
    # ran when.
    matches.sort()
    return [phase for _, phase in matches]
