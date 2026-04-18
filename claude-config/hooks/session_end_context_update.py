#!/usr/bin/env python3
"""
Session-end hook: detect commits per project during session, write pending
focus-review entries so Claude can propose focus updates on next /dashboard.

Non-blocking — never blocks session end.

Writes: ~/.claude/pending_focus_reviews.json
Format: { "{project}": { "commits": [...], "current_focus": "...",
                        "session_end": "..." } }

Merges with existing pending reviews — multiple sessions accumulate until
user resolves them via /dashboard.
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_DIR = Path.home() / "projects"
KNOWLEDGE_DB = Path.home() / "agents" / "knowledge" / "knowledge.db"
PENDING_FILE = Path.home() / ".claude" / "pending_focus_reviews.json"


def log(msg: str) -> None:
    try:
        log_path = Path.home() / ".claude" / "hooks.log"
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] session_end_context: {msg}\n")
    except Exception:
        pass


def get_session_commits(project_dir: Path, since_minutes: int = 240) -> list[dict]:
    """Return list of commits made in project during session window."""
    since = datetime.now() - timedelta(minutes=since_minutes)
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


def get_current_focus(project: str) -> str | None:
    """Read current focus from knowledge.db."""
    if not KNOWLEDGE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(KNOWLEDGE_DB))
        row = conn.execute(
            "SELECT focus FROM project_tracker WHERE project = ?", (project,)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def get_tracked_projects() -> set[str]:
    """Projects registered in knowledge tracker (we only propose updates for these)."""
    if not KNOWLEDGE_DB.exists():
        return set()
    try:
        conn = sqlite3.connect(str(KNOWLEDGE_DB))
        rows = conn.execute("SELECT project FROM project_tracker").fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


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
        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir() or not (proj_dir / ".git").is_dir():
                continue
            if proj_dir.name not in tracked:
                continue

            commits = get_session_commits(proj_dir)
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
                "current_focus": get_current_focus(proj_dir.name),
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
