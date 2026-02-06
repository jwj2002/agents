"""Search daily logs in Obsidian vault."""
from __future__ import annotations

import re
from pathlib import Path

from .vault_common import get_vault_path


def vault_search(query: str, project: str | None = None) -> dict:
    """Search daily logs for a query string.

    Args:
        query: Text to search for (case-insensitive)
        project: Optional project name to scope search. If None, searches all projects.

    Returns:
        Dict with matches grouped by project and date.
    """
    vault = get_vault_path()
    projects_dir = vault / "Projects"

    if not projects_dir.exists():
        return {"error": f"Projects directory not found: {projects_dir}", "matches": []}

    results = {"query": query, "matches": []}

    # Determine which projects to search
    if project:
        project_dirs = [projects_dir / project]
    else:
        project_dirs = [d for d in projects_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for proj_dir in sorted(project_dirs):
        if not proj_dir.exists():
            continue

        daily_dir = proj_dir / "Log" / "Daily"
        if not daily_dir.exists():
            continue

        for log_file in sorted(daily_dir.glob("*.md"), reverse=True):
            date_str = log_file.stem
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                continue

            content = log_file.read_text(encoding="utf-8")
            matching_lines = []
            for i, line in enumerate(content.split("\n"), 1):
                if pattern.search(line):
                    matching_lines.append({"line_number": i, "text": line.strip()})

            if matching_lines:
                results["matches"].append({
                    "project": proj_dir.name,
                    "date": date_str,
                    "file": str(log_file),
                    "lines": matching_lines[:10],  # Limit per file
                })

        # Limit total results
        if len(results["matches"]) > 50:
            results["truncated"] = True
            break

    results["total_matches"] = len(results["matches"])
    return results
