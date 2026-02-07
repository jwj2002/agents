"""Extract git commits for a project (deterministic, no LLM needed)."""
import subprocess
from pathlib import Path

from .extractor import CommitRef


def get_recent_commits(project_path: str, since_date: str = "") -> list[CommitRef]:
    """Get git commits for a project since a given date.

    Args:
        project_path: Path to the git repository.
        since_date: ISO date string (YYYY-MM-DD). If empty, gets today's commits.

    Returns:
        List of CommitRef with short hash and message.
    """
    if not Path(project_path).exists():
        return []

    cmd = ["git", "-C", project_path, "log", "--oneline", "--no-decorate"]
    if since_date:
        cmd.extend(["--since", since_date])
    else:
        cmd.extend(["--since", "midnight"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    commits = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        # Format: "abc1234 commit message here"
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append(CommitRef(hash=parts[0], message=parts[1]))
        elif len(parts) == 1:
            commits.append(CommitRef(hash=parts[0], message=""))

    return commits
