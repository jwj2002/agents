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

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from hook_common import utc_now_iso as _utc_now_iso  # shared (#369)

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


def _event_id(
    issue: int, date: str, project: str, root_cause: str, details: str
) -> str:
    """Stable content-hash identifier for a failure record (M4).

    SHA-1 of ``issue|date|project|root_cause|details`` (pipe-delimited, UTF-8).
    Used as the deduplication key in ``write_host_shard()`` and
    ``_collect_failures()`` so that two same-day same-issue failures with
    *different* root_cause/details both survive (they produce different hashes).

    Backward-compat: records that were written before event_id was added have
    no ``event_id`` field.  Callers should call ``ensure_event_id(record)``
    on read to synthesize one before deduplication.
    """
    payload = f"{issue}|{date}|{project}|{root_cause}|{details}"
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


def ensure_event_id(record: dict) -> dict:
    """Return *record* with ``event_id`` guaranteed to be present (M4 backward-compat).

    If the record already carries ``event_id``, it is returned unchanged.
    Otherwise a stable hash is synthesized from the salient fields and
    injected — the original record dict is mutated in-place and also returned.
    This allows the deduplication logic in ``write_host_shard`` and
    ``_collect_failures`` to always key on ``event_id``.
    """
    if "event_id" in record:
        return record
    record["event_id"] = _event_id(
        issue=record.get("issue", 0),
        date=record.get("date", ""),
        project=record.get("project", ""),
        root_cause=record.get("root_cause", ""),
        details=record.get("details", ""),
    )
    return record


def _state_path(project_dir: Path) -> Path:
    return (
        project_dir
        / ".agents"
        / "outputs"
        / "claude_checkpoints"
        / "PERSISTENT_STATE.yaml"
    )


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


def update_phase(
    project_dir: Path,
    issue: int,
    branch: str,
    phase: str,
    action: str,
    worktree_path: str | None = None,
) -> None:
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
        data["active_work"]["last_action"] = (
            f"Created {extracted['artifacts_created'][-1]}"
        )

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
    *,
    tier_corrected_to: str | None = None,
    guards_fired: list[str] | None = None,
    codex_overturned: dict | None = None,
    recall: dict | None = None,
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
        tier_corrected_to: Final complexity tier when the issue was
            re-classified mid-flight (e.g. "COMPLEX" when it started
            as "SIMPLE"). Omitted when no re-tier occurred.
        guards_fired: Names of pattern-guards that fired during the
            run (e.g. ["ENUM_VALUE", "VERIFICATION_GAP"]). Only names
            in ``_VALID_GUARDS`` are written; unknown names are dropped
            with a WARNING log. Omitted entirely when empty after
            filtering. DORMANT — schema only; no producer yet.
        codex_overturned: Dict with shape
            ``{"state": "not_run"|"confirmed"|"overturned",
            "category": str}`` recording whether Codex review changed
            the PROVE verdict. Both ``state`` and ``category`` must
            pass validation; the whole dict is dropped (with a WARNING)
            if either is invalid. DORMANT — schema only; no producer yet.
        recall: Optional dict written by the orchestrator sidecar
            (issue #456) with shape
            ``{"fired": bool, "n": int, "facts": list[str],
            "flag": "on"|"off"}``.
            ``flag`` must be in ``_VALID_RECALL_FLAGS``; ``fired`` must
            be bool; ``facts`` must be list. On any validation failure
            the whole dict is omitted (WARNING logged, no raise).
            Included in the record only when supplied.

    Returns: None. Errors are logged to ``~/.claude/hooks.log``; the
    function never raises into the orchestrator.
    """
    record: dict = {
        "issue": int(issue),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "recorded_at": _utc_now_iso(),
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

    if tier_corrected_to is not None:
        record["tier_corrected_to"] = str(tier_corrected_to)

    if guards_fired is not None:
        valid = [g for g in guards_fired if g in _VALID_GUARDS]
        dropped = set(guards_fired) - set(valid)
        if dropped:
            logging.warning("record_metrics: dropped unknown guards %r", dropped)
        if valid:
            record["guards_fired"] = valid

    if codex_overturned is not None:
        _state = codex_overturned.get("state", "")
        _cat = codex_overturned.get("category", "")
        if _state not in _VALID_CODEX_STATES:
            logging.warning(
                "record_metrics: dropped codex_overturned with invalid state %r", _state
            )
        elif _cat not in _VALID_CODEX_CATEGORIES:
            logging.warning(
                "record_metrics: dropped codex_overturned with invalid category %r",
                _cat,
            )
        else:
            record["codex_overturned"] = dict(codex_overturned)

    if recall is not None:
        if not isinstance(recall, dict):
            logging.warning("record_metrics: dropped non-dict recall %r", recall)
        else:
            _flag = recall.get("flag", "")
            _fired = recall.get("fired")
            _facts = recall.get("facts")
            _n = recall.get("n")
            if _flag not in _VALID_RECALL_FLAGS:
                logging.warning(
                    "record_metrics: dropped recall with invalid flag %r", _flag
                )
            elif not isinstance(_fired, bool):
                logging.warning(
                    "record_metrics: dropped recall with non-bool fired %r", _fired
                )
            elif not isinstance(_facts, list):
                logging.warning(
                    "record_metrics: dropped recall with non-list facts %r", _facts
                )
            else:
                try:
                    _n_val = max(0, int(_n)) if _n is not None else 0
                except (TypeError, ValueError):
                    _n_val = 0
                record["recall"] = {
                    "fired": _fired,
                    "n": _n_val,
                    "facts": [str(f) for f in _facts],
                    "flag": _flag,
                }

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
    _date = datetime.now().strftime("%Y-%m-%d")
    _details = details or ""
    # Derive project name from project_dir at record time so that two failures
    # from different projects that are otherwise identical get different event_ids.
    # Mirrors the convention in aggregate_metrics_to_global._derive_project():
    # the directory name of project_dir is the repo/project name.
    _project = project_dir.name
    record: dict = {
        "issue": int(issue),
        "date": _date,
        "recorded_at": _utc_now_iso(),
        "root_cause": root_cause,
        "project": _project,
        # Stable content-hash dedup key (M4).  Project is included at write
        # time so cross-project failures with identical other fields get
        # distinct event_ids.  ensure_event_id() is a no-op on re-read because
        # the field is already present.
        "event_id": _event_id(int(issue), _date, _project, root_cause, _details),
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
            logging.warning(f"flip_to_correction: metrics.jsonl not found at {target}")
            return False

        lines = [
            ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
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
        corrected["recorded_at"] = _utc_now_iso()
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


# ── PROVE per-AC audit (issue #1612) ──────────────────────────────────────


_VALID_AC_STATUSES = frozenset({"implemented", "partial", "missing", "deferred", "n/a"})

# Reasonable issue-reference shapes accepted as evidence for status="deferred".
# Plain "#1234" or "issue #1234" or "GH-1234" all count; bare prose without a
# referenced number does NOT — that's the load-bearing rule that prevents
# "deferred to a follow-up" from becoming an APPROVE escape hatch.
_DEFERRED_REF_RE = re.compile(r"#\d+|GH-\d+", re.IGNORECASE)

# Evidence-token patterns accepted as proof for status="implemented".
# At least ONE match is required; tokenless/empty evidence downgrades to FAIL.
# Accepted forms: file:line  |  path.py::test_name  |  test:/command:/smoke: prefix.
_EVIDENCE_TOKEN_RE = re.compile(
    r"[\w./\-]+\.\w+:\d+"          # file:line or file:line-range
    r"|[\w./\-]+\.py::[\w\[\]_-]+" # pytest node id (path.py::test_name)
    r"|(?:test:|command:|smoke:)\s*\S",  # verifier prefix MUST have non-whitespace payload
)

# Issue #460 — runtime_smoke (Level 5) status set. Compared case-insensitively
# on read (see validate_runtime_smoke); prove.md emits the lowercase/`n/a` forms.
_VALID_SMOKE_STATUSES = frozenset({"pass", "fail", "n/a"})

_VALID_GUARDS = frozenset(
    {
        "VERIFICATION_GAP",
        "ENUM_VALUE",
        "COMPONENT_API",
    }
)
_VALID_CODEX_STATES = frozenset({"not_run", "confirmed", "overturned"})
_VALID_CODEX_CATEGORIES = frozenset(
    {
        "auth",
        "migration",
        "enum_contract",
        "cross_module",
        "secrets",
    }
)
_VALID_RECALL_KEYS = frozenset({"fired", "n", "facts", "flag"})
_VALID_RECALL_FLAGS = frozenset({"on", "off"})


def _ac_label(entry: dict, idx: int) -> str:
    """Human-readable label for an AC entry in failure summaries.

    Prefers ``ac`` (verbatim bullet text), trimmed. Falls back to the index.
    """
    text = entry.get("ac") if isinstance(entry, dict) else None
    if isinstance(text, str) and text.strip():
        snippet = text.strip().splitlines()[0]
        return snippet[:80] + ("…" if len(snippet) > 80 else "")
    return f"AC#{idx + 1}"


def count_acceptance_bullets(issue_body: str) -> int:
    """Count markdown task items under an "Acceptance" heading.

    Scans ``issue_body`` for the first heading containing the word
    ``acceptance`` (case-insensitive) and counts ``- [ ]`` / ``- [x]``
    bullets until the next ``## ``/``### `` heading or end-of-body.

    Returns 0 when no Acceptance section can be located — the caller
    should treat that as "cannot enforce one-row-per-AC" and fall back
    to the emit-only validator.

    Args:
        issue_body: The full GitHub issue body markdown.

    Returns:
        Number of AC bullets found, or 0 when the section is absent.
    """
    if not isinstance(issue_body, str) or not issue_body:
        return 0
    lines = issue_body.splitlines()
    in_ac = False
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # New heading. Decide whether we're entering or leaving the AC block.
            if in_ac:
                break
            heading = stripped.lstrip("# ").lower()
            if "acceptance" in heading:
                in_ac = True
            continue
        if not in_ac:
            continue
        # Match markdown task items: "- [ ] ..." or "- [x] ..." (case
        # insensitive). Allow indented variants but reject deeply nested
        # sub-items (4+ spaces) — those are typically clarifications, not
        # top-level ACs.
        if re.match(r"^(\s{0,3}- \[[ xX]\] )", line):
            count += 1
    return count


def validate_ac_audit(
    ac_audit: list | None, expected_ac_count: int | None = None
) -> dict:
    """Validate a PROVE ``ac_audit`` array against the AC-FORBIDS-APPROVE rule.

    Mirrors the Codex-side rule from issue #1609: a PROVE verdict of PASS
    is FORBIDDEN if ANY ac_audit entry has ``status="missing"`` or
    ``status="partial"``. A ``status="deferred"`` entry is acceptable ONLY
    when ``evidence`` cites a follow-up issue # (e.g. ``"deferred to #1620"``).
    A bare "deferred" without a # is treated as missing.

    When ``expected_ac_count`` is provided (the orchestrator passes the
    count derived from the issue body's Acceptance section), the
    validator also FAILS if ``len(ac_audit) < expected_ac_count``. This
    closes the "PROVE silently omits an AC" bypass that an emit-only
    validator misses.

    Args:
        ac_audit: List of dicts shaped
            ``{"ac": str, "status": str, "evidence": str}``. May be None
            (missing array entirely → cannot validate; treat as failure).
        expected_ac_count: Number of AC bullets the issue body declares.
            ``None`` means "skip the count check" (used by unit tests +
            issues where the AC section can't be parsed).

    Returns:
        ``{"valid": bool, "downgrade_to": str|None, "missing": list[dict]}``
        where ``missing`` enumerates the offending entries with a ``reason``
        field. ``downgrade_to`` is ``"FAIL"`` when the audit forbids APPROVE,
        else ``None``. ``valid`` is False iff ``ac_audit`` is missing,
        empty, or contains an entry with an invalid status string.

    The function is pure (no I/O). Callers persist the result via
    ``record_prove_audit``.
    """
    missing: list[dict] = []
    if not isinstance(ac_audit, list) or not ac_audit:
        return {
            "valid": False,
            "downgrade_to": "FAIL",
            "missing": [
                {
                    "ac": "(no ac_audit array)",
                    "status": "missing",
                    "reason": "PROVE artifact has no ac_audit entries; cannot verify AC coverage",
                }
            ],
        }

    valid = True
    # Coverage gate: if the issue declares N ACs and PROVE only emits M < N,
    # the audit silently misses (N - M) ACs. Force missing entries for the
    # uncovered slots so the verdict downgrades.
    if isinstance(expected_ac_count, int) and expected_ac_count > len(ac_audit):
        for slot in range(len(ac_audit), expected_ac_count):
            missing.append(
                {
                    "ac": f"AC#{slot + 1}",
                    "status": "missing",
                    "reason": (
                        f"issue declares {expected_ac_count} AC bullets but "
                        f"ac_audit has only {len(ac_audit)} entries; "
                        f"AC #{slot + 1} omitted"
                    ),
                }
            )

    for idx, entry in enumerate(ac_audit):
        if not isinstance(entry, dict):
            valid = False
            missing.append(
                {
                    "ac": _ac_label({}, idx),
                    "status": "invalid",
                    "reason": f"ac_audit[{idx}] is not an object",
                }
            )
            continue
        status = entry.get("status")
        if status not in _VALID_AC_STATUSES:
            valid = False
            missing.append(
                {
                    "ac": _ac_label(entry, idx),
                    "status": str(status),
                    "reason": f"unknown status {status!r}; expected one of {sorted(_VALID_AC_STATUSES)}",
                }
            )
            continue
        if status in ("missing", "partial"):
            missing.append(
                {
                    "ac": _ac_label(entry, idx),
                    "status": status,
                    "reason": f"AC #{idx + 1} marked {status}",
                }
            )
        elif status == "deferred":
            evidence = entry.get("evidence")
            if not isinstance(evidence, str) or not _DEFERRED_REF_RE.search(evidence):
                missing.append(
                    {
                        "ac": _ac_label(entry, idx),
                        "status": "missing",
                        "reason": "deferred without follow-up issue # — treated as missing",
                    }
                )
        elif status == "implemented":
            evidence = entry.get("evidence")
            if not isinstance(evidence, str) or not _EVIDENCE_TOKEN_RE.search(evidence):
                missing.append(
                    {
                        "ac": _ac_label(entry, idx),
                        "status": "missing",
                        "reason": (
                            "implemented evidence lacks a verifier token "
                            "(need file:line, path.py::test_name, or test:/command:/smoke: prefix)"
                        ),
                    }
                )
        # n/a is clean; nothing to record.

    downgrade = "FAIL" if missing else None
    return {"valid": valid, "downgrade_to": downgrade, "missing": missing}


def validate_runtime_smoke(value) -> dict:
    """Validate a PROVE ``runtime_smoke`` (Level 5) value for the merge gate.

    Issue #460 evolves ``runtime_smoke`` from the #459 scalar string into a
    structured ``{status, command, evidence}`` block and binds a fail-closed
    merge gate to it. This validator enforces *structural completeness* of the
    declared result; it is the source of truth that ``prove_gate.check_gate``
    calls after the ac_audit block.

    **Trust model (Option A).** The gate TRUSTS PROVE's declared ``status``. It
    does NOT re-derive runnable-ness from a git diff and does NOT re-execute the
    smoke command — full re-execution / auto-run is out of scope here (that is
    AC5 / issue #461). What this validator enforces:

    - ``status`` is one of PASS / FAIL / n/a (case-insensitive).
    - ``status: PASS`` requires BOTH a non-empty STRING ``command`` (what was
      run) and a non-empty STRING ``evidence`` (the result). Non-string types
      (lists, dicts, bools) FAIL closed — they carry no real evidence (#460).
    - ``status: n/a`` requires non-empty STRING ``evidence`` (the
      justification); ``command`` is optional.
    - ``status: FAIL`` blocks — a failed smoke run cannot ship.
    - Absent / missing block blocks fail-CLOSED ("PROVE did not record it").
    - A NON-empty bare string (the #459 scalar form) is coerced to ``n/a`` with
      the string itself as evidence — backward compatible, never blocks on its
      own. An empty / whitespace-only scalar FAILs closed (no evidence, #460).

    Args:
        value: The ``runtime_smoke`` frontmatter value. May be a mapping
            (structured block), a string (#459 scalar), ``None`` (absent), or
            some other type (treated as a violation).

    Returns:
        ``{"valid": bool, "downgrade_to": str|None, "missing": list[dict]}`` —
        the SAME shape as ``validate_ac_audit`` so ``check_gate`` reuses the
        same consumption pattern. Each ``missing`` entry is shaped
        ``{"field": "runtime_smoke", "status": <str>, "reason": <str>}``.
        ``downgrade_to`` is ``"FAIL"`` on any violation, else ``None``.

    The function is pure (no I/O). Callers persist / act on the result.
    """

    def _violation(status: str, reason: str) -> dict:
        return {
            "valid": False,
            "downgrade_to": "FAIL",
            "missing": [
                {"field": "runtime_smoke", "status": status, "reason": reason}
            ],
        }

    def _ok() -> dict:
        return {"valid": True, "downgrade_to": None, "missing": []}

    def _empty(v) -> bool:
        return v is None or not str(v).strip()

    def _nonempty_str(v) -> bool:
        # command / evidence must be an actual non-empty STRING. Non-string
        # types (lists, dicts, bools, ints) carry no recorded evidence and must
        # NOT satisfy the "non-empty" requirement via repr coercion — that was
        # the type-confusion bypass (#460 Codex review): ``command: []`` would
        # stringify to ``"[]"`` and wrongly pass.
        return isinstance(v, str) and bool(v.strip())

    if value is None:
        return _violation(
            "missing",
            "PROVE did not record runtime_smoke (Level 5) — re-run PROVE",
        )

    # #459 backward-compat: a NON-empty bare string is coerced to n/a with the
    # string as evidence — never blocks on its own. An empty / whitespace-only
    # scalar carries no evidence and must FAIL closed (#460 Codex review).
    if isinstance(value, str):
        if value.strip():
            return _ok()
        return _violation(
            "n/a",
            "runtime_smoke scalar is empty — no evidence recorded; re-run PROVE",
        )

    if not isinstance(value, dict):
        return _violation(
            "invalid",
            f"runtime_smoke must be a mapping or string — got {type(value).__name__}",
        )

    raw_status = value.get("status")
    if _empty(raw_status):
        return _violation(
            "missing",
            "runtime_smoke.status absent — must be PASS, FAIL, or n/a",
        )
    status = str(raw_status).strip().lower()
    if status not in _VALID_SMOKE_STATUSES:
        return _violation(
            status,
            f"runtime_smoke.status={raw_status!r} invalid — expected PASS/FAIL/n/a",
        )

    command = value.get("command")
    evidence = value.get("evidence")

    if status == "fail":
        return _violation("fail", "runtime_smoke reported FAIL — smoke run failed")

    if status == "pass":
        if not _nonempty_str(evidence):
            return _violation(
                "pass",
                "runtime_smoke PASS requires non-empty string evidence",
            )
        if not _nonempty_str(command):
            return _violation(
                "pass",
                "runtime_smoke PASS requires the command that was run "
                "(a non-empty string; none recorded)",
            )
        return _ok()

    # status == "n/a"
    if not _nonempty_str(evidence):
        return _violation(
            "n/a",
            "runtime_smoke n/a requires non-empty string evidence (the justification)",
        )
    return _ok()


def record_prove_audit(
    project_dir: Path,
    issue: int,
    verdict: str,
    ac_audit: list | None,
    applicable_evals: list[str] | None = None,
    eval_results: dict[str, str] | None = None,
    downgrade_reason: str | None = None,
) -> None:
    """Append one PROVE per-AC audit row to ``.claude/memory/prove-log.jsonl``.

    Companion to ``record_metrics`` — keeps the AC discipline trail separate
    so /learn and the recurring-pattern detector can analyze AC coverage
    independently of the overall PASS/BLOCKED metric stream.

    Schema (per issue #1612):

        {
          "ts": "...UTC iso...",
          "issue": N,
          "phase": "PROVE",
          "verdict": "PASS|FAIL|BLOCKED",
          "ac_audit": [...],
          "applicable_evals": [...],
          "eval_results": {...},
          "downgrade_reason": "..." (optional)
        }

    Args:
        project_dir: Project root. File lives at
            ``<project_dir>/.claude/memory/prove-log.jsonl``.
        issue: GitHub issue number.
        verdict: ``"PASS"``, ``"FAIL"``, or ``"BLOCKED"``. ``FAIL`` is the
            new verdict that AC-FORBIDS-APPROVE downgrades a PASS to.
        ac_audit: The verbatim ac_audit array PROVE emitted (or ``[]`` if
            absent).
        applicable_evals: The behavioral-eval IDs PROVE ran (e.g.
            ``["E01", "E03", "E15"]``).
        eval_results: Per-eval pass/fail map (e.g.
            ``{"E01": "pass", "E03": "fail"}``).
        downgrade_reason: When ``verdict="FAIL"`` because ``validate_ac_audit``
            forced the downgrade, the human-readable reason.

    Returns: None. Errors are logged; the function never raises.
    """
    record: dict = {
        "ts": _utc_now_iso(),
        "issue": int(issue),
        "phase": "PROVE",
        "verdict": verdict,
        "ac_audit": list(ac_audit) if ac_audit else [],
    }
    if applicable_evals:
        record["applicable_evals"] = list(applicable_evals)
    if eval_results:
        record["eval_results"] = dict(eval_results)
    if downgrade_reason:
        record["downgrade_reason"] = downgrade_reason

    target = _memory_dir(project_dir) / "prove-log.jsonl"
    try:
        _append_jsonl(target, record)
    except OSError as e:
        logging.warning(f"record_prove_audit: could not append to {target}: {e}")
