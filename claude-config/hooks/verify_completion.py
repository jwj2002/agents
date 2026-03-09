#!/usr/bin/env python3
"""
Anti-rationalization Stop hook.

Runs when Claude declares a task complete. Checks for common signs of
premature completion:
  - Uncommitted changes that should have been committed
  - Failing tests
  - TODO/FIXME markers in recently changed files

Exit codes:
  0 = Allow stop (task appears complete)
  2 = Block stop (send feedback to Claude to continue working)
"""

import json
import os
import subprocess
import sys
from datetime import datetime


def log(msg: str) -> None:
    """Log to hooks.log for debugging."""
    log_path = os.path.expanduser("~/.claude/hooks.log")
    try:
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] verify_completion: {msg}\n")
    except Exception:
        pass


def run(cmd: str, timeout: int = 30) -> tuple[int, str]:
    """Run a shell command and return (returncode, output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


def check_uncommitted_changes() -> str | None:
    """Check if there are staged or unstaged changes that look like work in progress."""
    code, output = run("git diff --name-only HEAD 2>/dev/null")
    if code != 0 or not output:
        return None

    changed_files = [f for f in output.split("\n") if f.strip()]
    if not changed_files:
        return None

    # Only flag if there are substantive changes (not just config/lock files)
    substantive = [
        f for f in changed_files
        if not f.endswith((".lock", ".json", ".yaml", ".yml", ".toml"))
        or f.endswith("package.json")
    ]

    if substantive:
        file_list = ", ".join(substantive[:5])
        return f"You have uncommitted changes in: {file_list}. Did you forget to commit?"

    return None


def check_todos_in_changes() -> str | None:
    """Check for TODO/FIXME markers in recently changed files."""
    code, output = run("git diff HEAD 2>/dev/null")
    if code != 0 or not output:
        return None

    # Only check added lines (lines starting with +)
    added_lines = [
        line for line in output.split("\n")
        if line.startswith("+") and not line.startswith("+++")
    ]

    todo_lines = [
        line for line in added_lines
        if "TODO" in line or "FIXME" in line or "HACK" in line
    ]

    if todo_lines:
        count = len(todo_lines)
        return f"Found {count} TODO/FIXME/HACK marker(s) in your changes. These should be resolved before completing the task."

    return None


def main() -> None:
    issues = []

    # Run checks
    uncommitted = check_uncommitted_changes()
    if uncommitted:
        issues.append(uncommitted)

    todos = check_todos_in_changes()
    if todos:
        issues.append(todos)

    if issues:
        feedback = "COMPLETION CHECK FAILED:\n" + "\n".join(f"- {i}" for i in issues)
        log(f"Blocked: {len(issues)} issue(s) found")
        print(feedback)
        sys.exit(2)  # Exit 2 = block and send feedback
    else:
        log("Passed: no issues found")
        sys.exit(0)


if __name__ == "__main__":
    main()
