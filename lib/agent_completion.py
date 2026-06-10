"""Completion-discipline checks shared by lifecycle hooks."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


def run(args: list[str], cwd: Path, timeout: int = 10) -> CommandResult:
    """Run a small local command and return stripped stdout.

    Hooks are advisory and must fail open. Callers treat non-zero return codes
    as missing signal, not fatal errors.
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return CommandResult(-1, "")
    return CommandResult(result.returncode, result.stdout.strip())


def check_uncommitted_changes(cwd: Path) -> str | None:
    result = run(["git", "diff", "--name-only", "HEAD"], cwd)
    if result.returncode != 0 or not result.stdout:
        return None
    files = [line for line in result.stdout.splitlines() if line.strip()]
    if not files:
        return None
    preview = ", ".join(files[:5])
    suffix = f", +{len(files) - 5} more" if len(files) > 5 else ""
    return f"Uncommitted changes ({len(files)} files): {preview}{suffix}"


def check_unpushed_commits(cwd: Path) -> str | None:
    result = run(["git", "log", "@{u}..HEAD", "--oneline"], cwd)
    if result.returncode != 0 or not result.stdout:
        return None
    count = len(result.stdout.splitlines())
    return f"{count} commit(s) not pushed to upstream"


def check_branch_ahead_no_pr(cwd: Path) -> str | None:
    branch_result = run(["git", "branch", "--show-current"], cwd)
    branch = branch_result.stdout.strip()
    if branch_result.returncode != 0 or not branch or branch in {"main", "master"}:
        return None

    ahead_result = run(["git", "log", "origin/main..HEAD", "--oneline"], cwd)
    if ahead_result.returncode != 0 or not ahead_result.stdout:
        return None

    pr_result = run(
        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"],
        cwd,
        timeout=3,
    )
    if pr_result.returncode != 0:
        return None
    try:
        prs = json.loads(pr_result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if prs:
        return None
    count = len(ahead_result.stdout.splitlines())
    return f"branch '{branch}' is {count} commit(s) ahead of origin/main with no open PR"


def check_todos_in_changes(cwd: Path) -> str | None:
    result = run(["git", "diff", "HEAD"], cwd)
    if result.returncode != 0 or not result.stdout:
        return None
    count = 0
    for line in result.stdout.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if re.search(r"\b(TODO|FIXME|HACK)\b", line):
            count += 1
    if not count:
        return None
    return f"{count} TODO/FIXME/HACK marker(s) in diff"


def completion_warnings(cwd: Path) -> list[str]:
    """Return advisory warnings that work may be unfinished."""
    warnings: list[str] = []
    for check in (
        check_uncommitted_changes,
        check_unpushed_commits,
        check_branch_ahead_no_pr,
        check_todos_in_changes,
    ):
        warning = check(cwd)
        if warning:
            warnings.append(warning)
    return warnings
