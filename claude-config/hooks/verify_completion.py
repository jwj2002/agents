#!/usr/bin/env python3
"""
Anti-rationalization Stop hook.

Runs when Claude stops responding. Prints warnings about potential
incomplete work (uncommitted changes, TODO markers) as advisory output.

Always exits 0 to avoid feedback loops. The output is visible to the user
as context for whether to continue the conversation.
"""

import os
import shlex
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


def run(cmd: str, timeout: int = 10) -> tuple[int, str]:
    """Run a shell command and return (returncode, output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, Exception):
        return -1, ""


def check_uncommitted_changes() -> str | None:
    """Check if there are staged or unstaged changes."""
    code, output = run("git diff --name-only HEAD 2>/dev/null")
    if code != 0 or not output:
        return None

    changed_files = [f for f in output.split("\n") if f.strip()]
    if not changed_files:
        return None

    n = len(changed_files)
    preview = ", ".join(changed_files[:5])
    suffix = f", +{n - 5} more" if n > 5 else ""
    return f"Uncommitted changes ({n} files): {preview}{suffix}"


def check_unpushed_commits() -> str | None:
    """Check for commits not pushed to upstream."""
    code, output = run("git log @{u}..HEAD --oneline 2>/dev/null")
    if code != 0:
        return None  # no upstream set; not applicable
    if not output.strip():
        return None
    n = len(output.strip().split("\n"))
    return f"{n} commit(s) not pushed to upstream"


def check_branch_ahead_no_pr() -> str | None:
    """Check for feature branch ahead of origin/main with no open PR."""
    code, branch = run("git branch --show-current 2>/dev/null")
    if code != 0 or not branch or branch in ("main", "master"):
        return None
    code, ahead = run("git log origin/main..HEAD --oneline 2>/dev/null")
    if code != 0 or not ahead.strip():
        return None
    n = len(ahead.strip().split("\n"))
    code, pr_state = run(
        f"gh pr list --head {shlex.quote(branch)} --state open --json number 2>/dev/null",
        timeout=3,
    )
    if code != 0:
        return None  # gh unavailable / unauthed / timeout — skip silently
    if pr_state.strip() not in ("", "[]"):
        return None  # PR is open; not incomplete
    return f"branch '{branch}' is {n} commit(s) ahead of origin/main with no open PR"


def check_todos_in_changes() -> str | None:
    """Check for TODO/FIXME in recently changed files."""
    code, output = run("git diff HEAD 2>/dev/null")
    if code != 0 or not output:
        return None

    added_lines = [
        line for line in output.split("\n")
        if line.startswith("+") and not line.startswith("+++")
    ]

    todo_lines = [
        line for line in added_lines
        if "TODO" in line or "FIXME" in line or "HACK" in line
    ]

    if todo_lines:
        return f"{len(todo_lines)} TODO/FIXME/HACK marker(s) in diff"

    return None


def main() -> None:
    issues = []

    uncommitted = check_uncommitted_changes()
    if uncommitted:
        issues.append(uncommitted)

    unpushed = check_unpushed_commits()
    if unpushed:
        issues.append(unpushed)

    branch_no_pr = check_branch_ahead_no_pr()
    if branch_no_pr:
        issues.append(branch_no_pr)

    todos = check_todos_in_changes()
    if todos:
        issues.append(todos)

    if issues:
        # Advisory only — print warnings but always exit 0 to avoid loops
        print("[verify_completion] " + " | ".join(issues))
        log(f"Warning: {len(issues)} issue(s) found")
    else:
        log("Clean stop")

    sys.exit(0)


if __name__ == "__main__":
    main()
