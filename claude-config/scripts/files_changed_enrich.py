"""D7e — files_changed enrichment (cost-telemetry-v0 §D7e).

Strict precedence, first match wins:
  1. pr_git          — git --stat on squash-merge commit for the task's issue
  2. project_metrics — ~/.claude/memory/metrics.jsonl by issue number
  3. session_shard   — telemetry/<host>/sessions.jsonl files_touched,
                       ONLY for single-task sessions (multi-task → disqualified)
  4. none            → (None, "none")

All paths are injectable (pure / testable). Never raises: returns (None, "none") on error.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

# Pattern: squash-merge commit subject ends with (#N)
_ISSUE_SUBJECT_RE = re.compile(r"\(#(\d+)\)\s*$")

# Paths to exclude from session_shard files_touched
_EXCLUDE_PREFIXES = ("telemetry/", "telemetry\\", ".claude/telemetry/")
_EXCLUDE_PARTS = {"telemetry", "temp", ".tmp"}


# ---------------------------------------------------------------------------
# Tier 1: pr_git
# ---------------------------------------------------------------------------


def _git_files_for_issue(issue_number: int, repo_root: Path) -> int | None:
    """Return files-changed count for the squash-merge commit of `issue_number`,
    or None if no matching commit is found or git fails."""
    try:
        log = subprocess.run(
            ["git", "-C", str(repo_root), "log", "--pretty=%H\t%s", "-n", "500"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None

    for line in log.splitlines():
        sha, _, subj = line.partition("\t")
        m = _ISSUE_SUBJECT_RE.search(subj)
        if not m:
            continue
        if int(m.group(1)) != issue_number:
            continue
        # Found the commit — count changed files
        try:
            stat = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "show",
                    "--stat",
                    "--name-only",
                    "--format=",
                    sha,
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError):
            return None
        count = len([ln for ln in stat.splitlines() if ln.strip()])
        return count
    return None


# ---------------------------------------------------------------------------
# Tier 2: project_metrics
# ---------------------------------------------------------------------------


# metrics.jsonl records `complexity` (the tier), not a raw file count. Map it to a representative
# files-band so the existing usage_aggregator.task_tier() (1→TRIVIAL, 2-3→SIMPLE, 4+→COMPLEX) yields
# that same tier. This is a TIER PROXY, not a literal file count — the report marks project_metrics
# rows "(tier approximate)" (only pr_git is authoritative), so it is honestly labelled.
_COMPLEXITY_FILES = {"TRIVIAL": 1, "SIMPLE": 2, "COMPLEX": 4}


def _project_metrics_files(issue_number: int, metrics_path: Path) -> int | None:
    """files_changed for issue_number from metrics.jsonl: a real `files_changed` int if present, else
    a tier-band derived from `complexity` (metrics carries the tier, not a file count). First match wins."""
    if not metrics_path or not metrics_path.exists():
        return None
    try:
        for raw in metrics_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("issue") == issue_number:
                fc = rec.get("files_changed")
                if isinstance(fc, int) and fc >= 0:
                    return fc
                band = _COMPLEXITY_FILES.get(str(rec.get("complexity") or "").upper())
                if band is not None:
                    return band
    except OSError:
        return None
    return None


# ---------------------------------------------------------------------------
# Tier 3: session_shard
# ---------------------------------------------------------------------------


def _is_excluded_path(file_path: str) -> bool:
    """Return True if the path should be excluded (telemetry/ or temp/ files)."""
    p = file_path.replace("\\", "/")
    for prefix in _EXCLUDE_PREFIXES:
        prefix_norm = prefix.replace("\\", "/")
        if p.startswith(prefix_norm) or f"/{prefix_norm}" in p:
            return True
    parts = set(Path(file_path).parts)
    return bool(parts & _EXCLUDE_PARTS)


def _session_shard_files(issue_number: int, sessions_shard: Path) -> int | None:
    """Count deduplicated repo files from sessions.jsonl for issue_number.

    Rules:
    - Only use if the session has a SINGLE task mapping to this issue
    - A session mapping to multiple issues/tasks is disqualified entirely
    - Exclude telemetry/ and temp/ paths
    - Deduplicate paths
    Returns None if disqualified or no match.
    """
    if not sessions_shard or not sessions_shard.exists():
        return None

    try:
        lines = sessions_shard.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    # Collect all files from all sessions for this issue, checking single-task constraint
    all_files: set[str] = set()

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue

        # Check task_attribution
        ta = rec.get("task_attribution", {})
        if not isinstance(ta, dict):
            continue

        session_issue = ta.get("issue")

        # Get issue_refs from artifact_evidence to detect multi-task sessions
        ae = rec.get("artifact_evidence", {})
        issue_refs = ae.get("issue_refs", []) if isinstance(ae, dict) else []
        files_touched = ae.get("files_touched", []) if isinstance(ae, dict) else []

        # Determine if this session maps to our issue
        maps_to_issue = session_issue == issue_number or (
            isinstance(issue_refs, list) and issue_number in issue_refs
        )
        if not maps_to_issue:
            continue

        # Multi-task disqualification: if the session references more than one distinct issue,
        # it is a multi-task session — do NOT use it.
        all_issues: set = set()
        if session_issue is not None:
            all_issues.add(session_issue)
        if isinstance(issue_refs, list):
            all_issues.update(issue_refs)

        if len(all_issues) > 1:
            # Multi-task session — disqualified, return None
            return None

        # Single-task session — collect files
        for fp in files_touched:
            if isinstance(fp, str) and fp.strip() and not _is_excluded_path(fp):
                all_files.add(fp)

    if not all_files:
        return None
    return len(all_files)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _parse_issue_number(task: Any) -> int | None:
    """Extract an integer issue number from a task string like 'issue:42' or None."""
    if task is None:
        return None
    task_str = str(task)
    m = re.match(r"^issue:(\d+)$", task_str)
    if m:
        return int(m.group(1))
    return None


def enrich_task(
    task: Any,
    *,
    repo_root: Path | None = None,
    metrics_path: Path | None = None,
    sessions_shard: Path | None = None,
) -> tuple[int | None, str]:
    """Return (files_changed, files_changed_source) for a task string.

    Strict precedence — first match wins:
      1. pr_git          source="pr_git"
      2. project_metrics source="project_metrics"
      3. session_shard   source="session_shard"
      4. (None, "none")

    All path arguments are optional (injectable for tests). Returns (None, "none")
    on any error or when no signal is found.
    """
    issue_number = _parse_issue_number(task)
    if issue_number is None:
        return (None, "none")

    # Tier 1: pr_git
    if repo_root is not None:
        try:
            n = _git_files_for_issue(issue_number, Path(repo_root))
            if n is not None:
                return (n, "pr_git")
        except Exception:
            pass

    # Tier 2: project_metrics
    if metrics_path is not None:
        try:
            n = _project_metrics_files(issue_number, Path(metrics_path))
            if n is not None:
                return (n, "project_metrics")
        except Exception:
            pass

    # Tier 3: session_shard
    if sessions_shard is not None:
        try:
            n = _session_shard_files(issue_number, Path(sessions_shard))
            if n is not None:
                return (n, "session_shard")
        except Exception:
            pass

    return (None, "none")
