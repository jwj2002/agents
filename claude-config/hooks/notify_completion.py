#!/usr/bin/env python3
"""
iTerm2 / macOS notification hook for Claude Code session completion.

Runs on Stop. Sends a macOS Notification Center alert via osascript so the user
knows Claude has finished, even if the terminal is in the background.

Always exits 0 — notification failure must never block the session.
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
    """Log to hooks.log for debugging."""
    log_path = os.path.expanduser("~/.claude/hooks.log")
    try:
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] notify_completion: {msg}\n")
    except Exception:
        pass


def sanitize(text: str) -> str:
    """Sanitize text for safe embedding in an AppleScript string.

    Removes control characters and escapes characters that could break
    the osascript command or enable injection.
    """
    # Strip control characters (keep printable ASCII + common unicode)
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    # Escape backslashes first, then double quotes
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    # Truncate to reasonable notification length
    return text[:200]


def get_context() -> dict:
    """Read active work context from state_manager (best-effort)."""
    try:
        # state_manager lives alongside this file
        hook_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(hook_dir))
        from state_manager import get_active_work

        # Determine project dir: CWD is typically the project root
        project_dir = Path.cwd()
        return get_active_work(project_dir)
    except Exception:
        return {}


def build_message(active_work: dict) -> str:
    """Build notification message from active work context."""
    phase = active_work.get("phase")
    issue = active_work.get("issue")
    last_action = active_work.get("last_action")

    if phase and issue:
        return f"{phase} finished for issue #{issue}"

    if last_action:
        return f"Session complete — {sanitize(last_action)}"

    return "Session complete"


def send_notification(title: str, message: str) -> None:
    """Send macOS notification via osascript."""
    safe_title = sanitize(title)
    safe_message = sanitize(message)

    script = (
        f'display notification "{safe_message}" '
        f'with title "{safe_title}" '
        f'sound name "Glass"'
    )

    try:
        subprocess.run(
            ["osascript", "-e", script],
            timeout=5,
            capture_output=True,
        )
        log(f"Notification sent: {safe_message}")
    except Exception as e:
        log(f"Notification failed: {e}")


def main() -> None:
    # Platform guard — only macOS has osascript / Notification Center
    if sys.platform != "darwin":
        sys.exit(0)

    active_work = get_context()
    message = build_message(active_work)
    send_notification("Claude Code", message)

    # Always exit 0 regardless of outcome
    sys.exit(0)


if __name__ == "__main__":
    main()
