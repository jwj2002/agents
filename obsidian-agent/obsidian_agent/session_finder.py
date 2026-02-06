"""Find Claude Code session logs on the filesystem.

Bug fix from v1: Always uses filesystem mtime — never trusts sessions-index.json.
"""
import os
from pathlib import Path

from .config import Config


def _project_folder(claude_projects_path: Path, cwd: str) -> Path:
    """Resolve CWD to Claude's project folder naming convention."""
    # Claude encodes paths as -home-user-project
    folder_name = cwd.replace("/", "-")
    if not folder_name.startswith("-"):
        folder_name = "-" + folder_name

    candidate = claude_projects_path / folder_name
    if candidate.exists():
        return candidate

    # Try with leading dash stripped then re-added (edge cases)
    alt = claude_projects_path / ("-" + cwd.replace("/", "-").lstrip("-"))
    if alt.exists():
        return alt

    raise FileNotFoundError(
        f"No Claude project folder found for {cwd}\n"
        f"Looked in: {claude_projects_path}"
    )


def _most_recent_jsonl(folder: Path) -> Path:
    """Return the most recently modified .jsonl file in folder."""
    jsonl_files = list(folder.glob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"No session logs found in {folder}")
    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def get_current_session_log(config: Config) -> Path:
    """Find the most recent session log for the current working directory."""
    cwd = os.getcwd()
    folder = _project_folder(config.claude_projects_path, cwd)
    return _most_recent_jsonl(folder)


def get_session_log_by_id(config: Config, session_id: str) -> Path:
    """Find a session log by its ID (searches all project folders)."""
    for project_folder in config.claude_projects_path.iterdir():
        if not project_folder.is_dir():
            continue
        log_file = project_folder / f"{session_id}.jsonl"
        if log_file.exists():
            return log_file
    raise FileNotFoundError(f"Session {session_id} not found")


def get_session_log_by_project(config: Config, project_path: str) -> Path:
    """Find the most recent session log for a specific project path."""
    folder = _project_folder(config.claude_projects_path, project_path)
    return _most_recent_jsonl(folder)


def list_recent_projects(config: Config, limit: int = 10) -> list[tuple[str, Path]]:
    """List recently active projects by most-recent session mtime.

    Returns list of (project_name, most_recent_log_path) tuples.
    """
    projects: list[tuple[str, Path, float]] = []
    for folder in config.claude_projects_path.iterdir():
        if not folder.is_dir():
            continue
        jsonl_files = list(folder.glob("*.jsonl"))
        if not jsonl_files:
            continue
        latest = max(jsonl_files, key=lambda p: p.stat().st_mtime)
        # Decode folder name back to project name
        # e.g., -home-jjob-projects-VE-RAG-System → VE-RAG-System
        name = folder.name.rsplit("-", 1)[-1] if "-" in folder.name else folder.name
        # Better: take last path component from decoded path
        decoded = folder.name.replace("-", "/")
        if decoded.startswith("/"):
            name = Path(decoded).name
        projects.append((name, latest, latest.stat().st_mtime))

    projects.sort(key=lambda t: t[2], reverse=True)
    return [(name, path) for name, path, _ in projects[:limit]]
