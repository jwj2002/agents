#!/usr/bin/env python3
"""
Session-end hook: detect commits per project during session, write pending
focus-review entries so Claude can propose focus updates on next /dashboard.

Non-blocking — never blocks session end.

Writes: ~/.claude/pending_focus_reviews.json
Format: { "{project}": { "commits": [...], "current_focus": "...",
                        "session_end": "..." } }

Merges with existing pending reviews — multiple sessions accumulate until
user resolves them via /review-session.

Reads project state from filesystem YAMLs at ~/agents/knowledge/projects/.
The Knowledge MCP / SQLite cache was retired in Phase 6C (issue #146).
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

PROJECTS_DIR = Path.home() / "projects"
KNOWLEDGE_PROJECTS_DIR = Path.home() / "agents" / "knowledge" / "projects"
PENDING_FILE = Path.home() / ".claude" / "pending_focus_reviews.json"


def log(msg: str) -> None:
    try:
        log_path = Path.home() / ".claude" / "hooks.log"
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] session_end_context: {msg}\n")
    except Exception:
        pass


def get_session_commits(project_dir: Path, since: datetime) -> list[dict]:
    """Return list of commits made in project after the given cutoff."""
    since_iso = since.strftime("%Y-%m-%d %H:%M:%S")
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_dir), "log", "--since", since_iso, "--pretty=format:%H|%s"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        commits = []
        for line in proc.stdout.strip().split("\n"):
            if "|" in line:
                sha, message = line.split("|", 1)
                commits.append({"sha": sha[:8], "message": message})
        return commits
    except Exception:
        return []


def get_project_state(project: str) -> tuple[str | None, datetime | None]:
    """Return (focus, updated_at) read from knowledge/projects/<project>.yaml.

    updated_at is parsed naive (no timezone). Returns (None, None) on any
    error — the hook is non-blocking so missing/malformed YAML is silently OK.
    """
    if not HAS_YAML:
        return None, None
    yaml_path = KNOWLEDGE_PROJECTS_DIR / f"{project}.yaml"
    if not yaml_path.exists():
        return None, None
    try:
        data = yaml.safe_load(yaml_path.read_text()) or {}
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None

    focus = data.get("focus")
    updated_at = None
    raw = data.get("updated_at")
    if raw is not None:
        try:
            # YAML can give a date object or a string; normalize to a datetime.
            if hasattr(raw, "isoformat"):
                stamp = raw.isoformat()
            else:
                stamp = str(raw)
            stamp = stamp.replace("Z", "").strip()
            if " " in stamp:
                updated_at = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            elif "T" in stamp:
                updated_at = datetime.fromisoformat(stamp)
            else:
                updated_at = datetime.strptime(stamp, "%Y-%m-%d")
        except Exception:
            updated_at = None
    return focus, updated_at


def get_tracked_projects() -> set[str]:
    """Projects registered in knowledge/projects/. Empty if the dir is missing."""
    if not KNOWLEDGE_PROJECTS_DIR.exists():
        return set()
    return {p.stem for p in KNOWLEDGE_PROJECTS_DIR.glob("*.yaml")}


def main() -> int:
    try:
        _ = sys.stdin.read() if not sys.stdin.isatty() else ""

        if not PROJECTS_DIR.exists():
            return 0

        tracked = get_tracked_projects()
        if not tracked:
            log("no tracked projects")
            return 0

        # Load existing pending reviews (merge — don't overwrite prior sessions)
        pending: dict = {}
        if PENDING_FILE.exists():
            try:
                pending = json.loads(PENDING_FILE.read_text())
            except Exception:
                pending = {}

        updated = False
        session_window_cutoff = datetime.now() - timedelta(minutes=240)

        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir() or not (proj_dir / ".git").is_dir():
                continue
            if proj_dir.name not in tracked:
                continue

            # Cutoff = max(session window, last focus update)
            # Only surface commits newer than when focus was last set —
            # otherwise we re-propose things the user already acknowledged.
            focus, updated_at = get_project_state(proj_dir.name)
            cutoff = session_window_cutoff
            if updated_at and updated_at > cutoff:
                cutoff = updated_at

            commits = get_session_commits(proj_dir, since=cutoff)
            if not commits:
                continue

            # Merge new commits with any existing pending ones, dedupe by sha
            existing = pending.get(proj_dir.name, {})
            existing_commits = existing.get("commits", [])
            existing_shas = {c["sha"] for c in existing_commits}
            new_commits = [c for c in commits if c["sha"] not in existing_shas]

            if not new_commits:
                continue

            pending[proj_dir.name] = {
                "commits": existing_commits + new_commits,
                "current_focus": focus,
                "session_end": datetime.now().isoformat(),
            }
            updated = True

        if updated:
            PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
            PENDING_FILE.write_text(json.dumps(pending, indent=2))
            log(f"wrote pending reviews for {len(pending)} projects")

    except Exception as e:
        log(f"error (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
