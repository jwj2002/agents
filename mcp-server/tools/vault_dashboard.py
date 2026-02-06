"""Read DASHBOARD.md from Obsidian vault → project list."""
from __future__ import annotations

import re
from pathlib import Path

from .vault_common import get_vault_path


def vault_dashboard() -> dict:
    """Read DASHBOARD.md and return structured project overview.

    Returns:
        Dict with list of projects, their status summaries, and last activity dates.
    """
    vault = get_vault_path()
    dashboard_file = vault / "DASHBOARD.md"

    result = {
        "vault_path": str(vault),
        "projects": [],
    }

    # Try reading DASHBOARD.md first
    if dashboard_file.exists():
        content = dashboard_file.read_text(encoding="utf-8")
        result["source"] = "DASHBOARD.md"

        # Parse project entries from dashboard
        current_project = None
        for line in content.split("\n"):
            proj_match = re.match(r"^###?\s+(.+)$", line)
            if proj_match:
                current_project = proj_match.group(1).strip()
                result["projects"].append({
                    "name": current_project,
                    "status": None,
                    "details": [],
                })
                continue

            if current_project and line.strip().startswith("-"):
                text = line.strip().lstrip("- ").strip()
                if result["projects"]:
                    if result["projects"][-1]["status"] is None and text:
                        result["projects"][-1]["status"] = text
                    else:
                        result["projects"][-1]["details"].append(text)
    else:
        # Fallback: scan Projects/ directory
        result["source"] = "directory_scan"
        projects_dir = vault / "Projects"
        if projects_dir.exists():
            for proj_dir in sorted(projects_dir.iterdir()):
                if proj_dir.is_dir() and not proj_dir.name.startswith("."):
                    status_file = proj_dir / "STATUS.md"
                    status_text = None
                    if status_file.exists():
                        # Read first non-empty, non-heading line
                        for sline in status_file.read_text(encoding="utf-8").split("\n"):
                            if sline.strip() and not sline.startswith("#"):
                                status_text = sline.strip()
                                break

                    result["projects"].append({
                        "name": proj_dir.name,
                        "status": status_text,
                        "has_status_md": status_file.exists(),
                        "has_daily_logs": (proj_dir / "Log" / "Daily").exists(),
                    })

    result["total_projects"] = len(result["projects"])
    return result
