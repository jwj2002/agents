#!/usr/bin/env python3
"""
Session-end hook: detect commits made during session, prompt user to update project context.

Reads commits from all ~/projects/* repos made during the session window.
If commits exist, writes a reminder to ~/.claude/session_context_reminders.log
for the user to see next /dashboard invocation.

Non-blocking — never blocks session end.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_DIR = Path.home() / "projects"
REMINDER_LOG = Path.home() / ".claude" / "session_context_reminders.log"


def log(msg: str) -> None:
    try:
        log_path = Path.home() / ".claude" / "hooks.log"
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] session_end_context: {msg}\n")
    except Exception:
        pass


def get_recent_commits_per_project(since_minutes: int = 240) -> dict:
    """Scan ~/projects/* for commits in the last N minutes. Returns {project: [commit_msgs]}."""
    since = datetime.now() - timedelta(minutes=since_minutes)
    since_iso = since.strftime("%Y-%m-%d %H:%M:%S")
    results = {}

    if not PROJECTS_DIR.exists():
        return results

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        if not (proj_dir / ".git").is_dir():
            continue

        try:
            proc = subprocess.run(
                ["git", "-C", str(proj_dir), "log", "--since", since_iso, "--pretty=format:%s"],
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                commits = [line for line in proc.stdout.strip().split("\n") if line]
                if commits:
                    results[proj_dir.name] = commits
        except Exception as e:
            log(f"skipping {proj_dir.name}: {e}")

    return results


def main() -> int:
    try:
        # Read session context from stdin (claude code hook format)
        _ = sys.stdin.read() if not sys.stdin.isatty() else ""

        commits_by_project = get_recent_commits_per_project(since_minutes=240)
        if not commits_by_project:
            log("no commits in session")
            return 0

        # Write reminder file (consumed by /dashboard skill on next invocation)
        REMINDER_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "commits_by_project": commits_by_project,
        }
        with open(REMINDER_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")

        log(f"wrote reminder for {len(commits_by_project)} projects")
    except Exception as e:
        log(f"error (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
