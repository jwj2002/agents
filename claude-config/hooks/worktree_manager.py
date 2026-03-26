#!/usr/bin/env python3
"""
Worktree manager for parallel orchestrate sessions.

Creates and manages git worktrees at .worktrees/issue-{N}/ to enable
concurrent orchestrate workflows on independent issues.

Used by: orchestrate command (--parallel), pr command (post-merge cleanup).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

_log_file = Path.home() / ".claude" / "hooks.log"
logging.basicConfig(
    filename=str(_log_file),
    level=logging.WARNING,
    format="%(asctime)s [worktree_manager] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class WorktreeExistsError(Exception):
    """Raised when a worktree already exists for the given issue."""

    def __init__(self, issue: int, path: Path):
        self.issue = issue
        self.path = path
        super().__init__(f"Worktree already exists for issue #{issue} at {path}")


def get_repo_root() -> Path:
    """Return the main repository root via git rev-parse --show-toplevel.

    Works correctly even when CWD is inside a worktree — always returns
    the main repo root (not the worktree path).
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def _worktree_dir(repo_root: Path) -> Path:
    """Return the .worktrees/ directory path."""
    return repo_root / ".worktrees"


def _issue_path(repo_root: Path, issue: int) -> Path:
    """Return the worktree path for a given issue."""
    return _worktree_dir(repo_root) / f"issue-{issue}"


def create_worktree(issue: int, branch_slug: str) -> Path:
    """Create an isolated worktree at .worktrees/issue-{N}/.

    Args:
        issue: GitHub issue number.
        branch_slug: Branch name (e.g., 'feature/issue-42-description').

    Returns:
        Absolute path to the created worktree.

    Raises:
        WorktreeExistsError: If a worktree already exists for this issue.
        subprocess.CalledProcessError: If git worktree add fails.
    """
    repo_root = get_repo_root()
    wt_path = _issue_path(repo_root, issue)

    # Check if worktree already exists
    existing = get_worktree_path(issue)
    if existing is not None:
        raise WorktreeExistsError(issue, existing)

    # Ensure .worktrees/ directory exists
    _worktree_dir(repo_root).mkdir(parents=True, exist_ok=True)

    # Fetch latest main and create worktree with new branch
    subprocess.run(
        ["git", "fetch", "origin", "main"],
        capture_output=True, text=True, check=True,
        cwd=str(repo_root),
    )
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "-b", branch_slug, "origin/main"],
        capture_output=True, text=True, check=True,
        cwd=str(repo_root),
    )

    return wt_path.resolve()


def list_worktrees() -> list[dict]:
    """List active worktrees with metadata.

    Returns:
        List of dicts: {path, branch, issue (int|None)}.
        Filters out the main worktree.
    """
    repo_root = get_repo_root()
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=True,
        cwd=str(repo_root),
    )

    worktrees = []
    current: dict = {}
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = {"path": line[len("worktree "):]}
        elif line.startswith("branch "):
            current["branch"] = line[len("branch refs/heads/"):]
        elif line == "":
            if current and current.get("path") != str(repo_root):
                # Extract issue number from path (e.g., .worktrees/issue-42)
                match = re.search(r"issue-(\d+)$", current.get("path", ""))
                current["issue"] = int(match.group(1)) if match else None
                worktrees.append(current)
            current = {}

    # Handle last entry if no trailing blank line
    if current and current.get("path") != str(repo_root):
        match = re.search(r"issue-(\d+)$", current.get("path", ""))
        current["issue"] = int(match.group(1)) if match else None
        worktrees.append(current)

    return worktrees


def get_worktree_path(issue: int) -> Path | None:
    """Return the worktree path for a given issue, or None if not found.

    Used by --resume to locate an existing worktree.
    """
    for wt in list_worktrees():
        if wt.get("issue") == issue:
            return Path(wt["path"])
    return None


def check_file_conflicts(planned_files: list[str]) -> list[dict]:
    """Check if active worktrees have uncommitted changes in planned files.

    Args:
        planned_files: List of file paths the current issue plans to modify.

    Returns:
        List of {worktree, file, issue} conflict dicts.
    """
    conflicts = []
    for wt in list_worktrees():
        wt_path = wt["path"]
        try:
            # Get both staged and unstaged changes
            unstaged = subprocess.run(
                ["git", "-C", wt_path, "diff", "--name-only"],
                capture_output=True, text=True, check=True,
            )
            staged = subprocess.run(
                ["git", "-C", wt_path, "diff", "--cached", "--name-only"],
                capture_output=True, text=True, check=True,
            )
            changed = set(unstaged.stdout.splitlines() + staged.stdout.splitlines())

            for pf in planned_files:
                if pf in changed:
                    conflicts.append({
                        "worktree": wt_path,
                        "file": pf,
                        "issue": wt.get("issue"),
                    })
        except subprocess.CalledProcessError:
            logging.warning(f"Failed to check worktree at {wt_path}")

    return conflicts


def remove_worktree(issue: int) -> bool:
    """Clean up a worktree after PR merge.

    Args:
        issue: GitHub issue number.

    Returns:
        True if worktree was found and removed, False if not found.
    """
    repo_root = get_repo_root()
    wt_path = get_worktree_path(issue)
    if wt_path is None:
        return False

    try:
        subprocess.run(
            ["git", "worktree", "remove", str(wt_path), "--force"],
            capture_output=True, text=True, check=True,
            cwd=str(repo_root),
        )
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True, text=True, check=True,
            cwd=str(repo_root),
        )
        return True
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to remove worktree for issue #{issue}: {e}")
        return False
