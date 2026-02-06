"""Read project STATUS.md from Obsidian vault → structured JSON."""
from __future__ import annotations

import re
from pathlib import Path

from .vault_common import get_vault_path


def vault_status(project: str) -> dict:
    """Read STATUS.md for a project and return structured data.

    Args:
        project: Project name (folder name under vault/Projects/)

    Returns:
        Dict with status, next_steps, blockers, recent_activity
    """
    vault = get_vault_path()
    status_file = vault / "Projects" / project / "STATUS.md"

    if not status_file.exists():
        return {"error": f"STATUS.md not found for project '{project}'", "path": str(status_file)}

    content = status_file.read_text(encoding="utf-8")
    result = {
        "project": project,
        "path": str(status_file),
        "status": None,
        "next_steps": [],
        "blockers": [],
        "recent_activity": [],
    }

    current_section = None
    for line in content.split("\n"):
        # Detect sections
        if re.match(r"^##\s+Status", line, re.I):
            current_section = "status"
            continue
        elif re.match(r"^##\s+Next\s+Steps", line, re.I):
            current_section = "next_steps"
            continue
        elif re.match(r"^##\s+Blockers?", line, re.I):
            current_section = "blockers"
            continue
        elif re.match(r"^##\s+Recent\s+Activity", line, re.I):
            current_section = "recent_activity"
            continue
        elif re.match(r"^##\s+", line):
            current_section = None
            continue

        # Parse content
        if current_section == "status" and line.strip():
            if result["status"] is None:
                result["status"] = line.strip()
        elif current_section == "next_steps":
            m = re.match(r"^-\s+\[([x ])\]\s+(.+)$", line)
            if m:
                result["next_steps"].append({
                    "done": m.group(1) == "x",
                    "text": m.group(2).strip(),
                })
        elif current_section == "blockers":
            m = re.match(r"^-\s+(.+)$", line)
            if m:
                text = m.group(1).strip()
                if text.lower() not in ("none", "(none)", "n/a"):
                    result["blockers"].append(text)
        elif current_section == "recent_activity":
            m = re.match(r"^-\s+(.+)$", line)
            if m:
                result["recent_activity"].append(m.group(1).strip())

    return result
