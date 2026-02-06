#!/usr/bin/env python3
"""
Daily Standup Agent (v2)

Aggregates work across all projects from Obsidian vault:
- Yesterday's completed items
- Today's next steps
- Current blockers

Supports both v2 vault format (obsidian-agent v2: STATUS.md + Log/Daily/)
and v1 format (completed.md, next-steps.md, blockers.md) as fallback.

Usage:
    python standup.py                  # Default standup
    python standup.py --since "3 days" # Last 3 days
    python standup.py --week           # Weekly summary
    python standup.py --copy           # Copy to clipboard
"""
from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import PROJECTS_FOLDER


def get_projects() -> list[Path]:
    """Get all project directories in the vault."""
    if not PROJECTS_FOLDER.exists():
        return []

    projects = []
    for item in PROJECTS_FOLDER.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            projects.append(item)

    return sorted(projects, key=lambda p: p.name)


def is_v2_vault(project_path: Path) -> bool:
    """Check if project uses v2 vault format (STATUS.md + Log/Daily/)."""
    return (project_path / "STATUS.md").exists() or (project_path / "Log" / "Daily").exists()


# --- v2 vault readers ---

def get_next_steps_v2(project_path: Path) -> list[str]:
    """Read next steps from STATUS.md ## Next Steps section."""
    status_file = project_path / "STATUS.md"
    if not status_file.exists():
        return []

    content = status_file.read_text(encoding="utf-8")
    steps = []

    in_section = False
    for line in content.split("\n"):
        if re.match(r'^##\s+Next\s+Steps', line, re.I):
            in_section = True
            continue
        if in_section and re.match(r'^##\s+', line):
            break
        if in_section:
            item_match = re.match(r'^-\s+\[[ ]\]\s+(.+)$', line)
            if item_match:
                steps.append(item_match.group(1).strip())

    return steps


def get_blockers_v2(project_path: Path) -> list[str]:
    """Read blockers from STATUS.md ## Blockers section."""
    status_file = project_path / "STATUS.md"
    if not status_file.exists():
        return []

    content = status_file.read_text(encoding="utf-8")
    blockers = []

    in_section = False
    for line in content.split("\n"):
        if re.match(r'^##\s+Blockers?', line, re.I):
            in_section = True
            continue
        if in_section and re.match(r'^##\s+', line):
            break
        if in_section:
            item_match = re.match(r'^-\s+(.+)$', line)
            if item_match:
                text = item_match.group(1).strip()
                if text.lower() not in ("none", "(none)", "n/a"):
                    blockers.append(text)

    return blockers


def get_completed_items_v2(project_path: Path, since_date: str) -> list[str]:
    """Read completed items from Log/Daily/*.md files since a date.

    V2 daily logs have a **Completed**: section with checklist items.
    Filenames are YYYY-MM-DD.md.
    """
    daily_dir = project_path / "Log" / "Daily"
    if not daily_dir.exists():
        return []

    completed = []
    for log_file in sorted(daily_dir.glob("*.md")):
        # Extract date from filename (YYYY-MM-DD.md)
        date_str = log_file.stem
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            continue
        if date_str < since_date:
            continue

        content = log_file.read_text(encoding="utf-8")
        in_completed = False
        for line in content.split("\n"):
            if re.match(r'^\*\*Completed\*\*:', line, re.I) or re.match(r'^##\s+Completed', line, re.I):
                in_completed = True
                continue
            if in_completed and (re.match(r'^\*\*', line) or re.match(r'^##', line)):
                break
            if in_completed:
                item_match = re.match(r'^-\s+\[x\]\s+(.+)$', line)
                if item_match:
                    completed.append(item_match.group(1).strip())
                # Also match simple list items in completed section
                simple_match = re.match(r'^-\s+([^\[].+)$', line)
                if simple_match:
                    completed.append(simple_match.group(1).strip())

    return completed


# --- v1 vault readers (fallback) ---

def parse_dated_items(file_path: Path, since_date: str = None) -> dict[str, list[str]]:
    """Parse a markdown file with dated sections, return items by date."""
    if not file_path.exists():
        return {}

    content = file_path.read_text()
    items_by_date: dict[str, list[str]] = {}

    current_date = None
    for line in content.split("\n"):
        # Match date headers like "## 2026-01-31"
        date_match = re.match(r'^##\s+(\d{4}-\d{2}-\d{2})', line)
        if date_match:
            current_date = date_match.group(1)
            if current_date not in items_by_date:
                items_by_date[current_date] = []
            continue

        # Match checklist items
        item_match = re.match(r'^-\s+\[([x ])\]\s+(.+)$', line)
        if item_match and current_date:
            checked = item_match.group(1) == 'x'
            text = item_match.group(2).strip()
            prefix = "[x]" if checked else "[ ]"
            items_by_date[current_date].append(f"{prefix} {text}")
            continue

        # Match non-checkbox items (for decisions, blockers)
        simple_match = re.match(r'^-\s+(.+)$', line)
        if simple_match and current_date:
            text = simple_match.group(1).strip()
            if not text.startswith("["):
                items_by_date[current_date].append(text)

    if since_date:
        items_by_date = {
            d: items for d, items in items_by_date.items()
            if d >= since_date
        }

    return items_by_date


def get_completed_items_v1(project_path: Path, since_date: str) -> list[str]:
    """Get completed items from v1 format (completed.md)."""
    completed_file = project_path / "completed.md"
    items_by_date = parse_dated_items(completed_file, since_date)

    completed = []
    for date, items in sorted(items_by_date.items()):
        for item in items:
            if item.startswith("[x] "):
                completed.append(item[4:])
            elif item.startswith("[ ] "):
                continue
            else:
                completed.append(item)

    return completed


def get_next_steps_v1(project_path: Path) -> list[str]:
    """Get next steps from v1 format (next-steps.md)."""
    next_steps_file = project_path / "next-steps.md"
    items_by_date = parse_dated_items(next_steps_file)

    steps = []
    for date, items in sorted(items_by_date.items(), reverse=True):
        for item in items:
            if item.startswith("[ ] "):
                steps.append(item[4:])

    return steps


def get_blockers_v1(project_path: Path) -> list[str]:
    """Get blockers from v1 format (blockers.md)."""
    blockers_file = project_path / "blockers.md"
    items_by_date = parse_dated_items(blockers_file)

    blockers = []
    for date in sorted(items_by_date.keys(), reverse=True)[:3]:
        for item in items_by_date[date]:
            if item.startswith("[ ] "):
                blockers.append(item[4:])
            elif not item.startswith("[x] "):
                blockers.append(item)

    return blockers


# --- Unified interface ---

def get_completed_items(project_path: Path, since_date: str) -> list[str]:
    """Get completed items, auto-detecting v1/v2 vault format."""
    if is_v2_vault(project_path):
        return get_completed_items_v2(project_path, since_date)
    return get_completed_items_v1(project_path, since_date)


def get_next_steps(project_path: Path) -> list[str]:
    """Get next steps, auto-detecting v1/v2 vault format."""
    if is_v2_vault(project_path):
        return get_next_steps_v2(project_path)
    return get_next_steps_v1(project_path)


def get_blockers(project_path: Path) -> list[str]:
    """Get blockers, auto-detecting v1/v2 vault format."""
    if is_v2_vault(project_path):
        return get_blockers_v2(project_path)
    return get_blockers_v1(project_path)


def format_standup(
    completed_by_project: dict[str, list[str]],
    next_by_project: dict[str, list[str]],
    blockers_by_project: dict[str, list[str]],
    since_label: str
) -> str:
    """Format the standup report."""
    lines = []
    today = datetime.now().strftime("%Y-%m-%d")

    lines.append(f"# Daily Standup - {today}")
    lines.append("")

    # Completed section
    has_completed = any(items for items in completed_by_project.values())
    if has_completed:
        lines.append(f"## {since_label}")
        lines.append("")
        for project, items in sorted(completed_by_project.items()):
            if items:
                lines.append(f"### {project}")
                for item in items[:10]:
                    lines.append(f"- [x] {item}")
                lines.append("")

    # Next steps section
    has_next = any(items for items in next_by_project.values())
    if has_next:
        lines.append("## Today's Focus")
        lines.append("")
        for project, items in sorted(next_by_project.items()):
            if items:
                lines.append(f"### {project}")
                for item in items[:5]:
                    lines.append(f"- [ ] {item}")
                lines.append("")

    # Blockers section
    all_blockers = []
    for project, items in blockers_by_project.items():
        for item in items:
            all_blockers.append(f"{project}: {item}")

    lines.append("## Blockers")
    lines.append("")
    if all_blockers:
        for blocker in all_blockers[:5]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- (none)")
    lines.append("")

    return "\n".join(lines)


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard (cross-platform)."""
    system = platform.system()
    try:
        if system == "Darwin":
            cmd = ["pbcopy"]
        elif system == "Linux":
            # Try xclip first, then xsel
            cmd = ["xclip", "-selection", "clipboard"]
        else:
            return False

        subprocess.run(cmd, input=text.encode(), check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        if system == "Linux":
            try:
                subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text.encode(),
                    check=True
                )
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate daily standup from Obsidian vault")
    parser.add_argument("--since", default="1 day", help="Time range for completed items")
    parser.add_argument("--week", action="store_true", help="Weekly summary (last 7 days)")
    parser.add_argument("--copy", "-c", action="store_true", help="Copy to clipboard")
    parser.add_argument("--project", "-p", help="Single project only")

    args = parser.parse_args()

    # Calculate since date
    if args.week:
        days = 7
        since_label = "This Week"
    else:
        match = re.match(r"(\d+)\s*days?", args.since)
        days = int(match.group(1)) if match else 1
        since_label = "Yesterday" if days == 1 else f"Last {days} Days"

    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Get projects
    projects = get_projects()
    if not projects:
        print(f"No projects found in {PROJECTS_FOLDER}")
        print(f"Set OBSIDIAN_VAULT_PATH env var to your vault location.")
        sys.exit(1)

    if args.project:
        projects = [p for p in projects if p.name == args.project]
        if not projects:
            print(f"Project '{args.project}' not found")
            sys.exit(1)

    # Gather data
    completed_by_project = {}
    next_by_project = {}
    blockers_by_project = {}

    for project in projects:
        name = project.name
        vault_ver = "v2" if is_v2_vault(project) else "v1"
        completed_by_project[name] = get_completed_items(project, since_date)
        next_by_project[name] = get_next_steps(project)
        blockers_by_project[name] = get_blockers(project)

    # Format output
    standup = format_standup(
        completed_by_project,
        next_by_project,
        blockers_by_project,
        since_label
    )

    print(standup)

    if args.copy:
        if copy_to_clipboard(standup):
            print("---")
            print("(Copied to clipboard)")
        else:
            print("---")
            print("(Could not copy to clipboard. Install xclip or xsel on Linux.)")


if __name__ == "__main__":
    main()
