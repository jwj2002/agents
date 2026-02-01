"""Write extracted information to Obsidian vault."""
import shutil
from datetime import datetime
from pathlib import Path

from config import PROJECTS_FOLDER, TEMPLATES_FOLDER
from extractor import SessionExtract


def ensure_project_folder(project_name: str) -> Path:
    """Create project folder structure if it doesn't exist."""
    project_path = PROJECTS_FOLDER / project_name
    sessions_path = project_path / "sessions"

    if not project_path.exists():
        project_path.mkdir(parents=True)
        sessions_path.mkdir()

        # Copy templates
        for template in TEMPLATES_FOLDER.glob("*.md"):
            if template.name != "session.md":
                shutil.copy(template, project_path / template.name)

    elif not sessions_path.exists():
        sessions_path.mkdir()

    return project_path


def append_to_file(file_path: Path, items: list[str], header: str = None):
    """Append items to a markdown file."""
    if not items:
        return

    content = file_path.read_text() if file_path.exists() else ""

    today = datetime.now().strftime("%Y-%m-%d")

    # Check if today's section already exists
    today_header = f"## {today}"
    if today_header not in content:
        new_section = f"\n{today_header}\n"
        for item in items:
            new_section += f"- [ ] {item}\n"
        content = content.rstrip() + "\n" + new_section
    else:
        # Append to today's section
        lines = content.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip() == today_header:
                # Find the end of this section (next ## or end of file)
                insert_idx = i + 1
                while insert_idx < len(lines):
                    if lines[insert_idx].startswith("## "):
                        break
                    insert_idx += 1
                break

        if insert_idx:
            new_items = [f"- [ ] {item}" for item in items]
            lines = lines[:insert_idx] + new_items + lines[insert_idx:]
            content = "\n".join(lines)

    file_path.write_text(content)


def append_completed(file_path: Path, items: list[str]):
    """Append completed items (with checkmarks)."""
    if not items:
        return

    content = file_path.read_text() if file_path.exists() else ""

    today = datetime.now().strftime("%Y-%m-%d")
    today_header = f"## {today}"

    if today_header not in content:
        new_section = f"\n{today_header}\n"
        for item in items:
            new_section += f"- [x] {item}\n"
        content = content.rstrip() + "\n" + new_section
    else:
        lines = content.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip() == today_header:
                insert_idx = i + 1
                while insert_idx < len(lines):
                    if lines[insert_idx].startswith("## "):
                        break
                    insert_idx += 1
                break

        if insert_idx:
            new_items = [f"- [x] {item}" for item in items]
            lines = lines[:insert_idx] + new_items + lines[insert_idx:]
            content = "\n".join(lines)

    file_path.write_text(content)


def append_decisions(file_path: Path, items: list[str]):
    """Append decisions (no checkboxes)."""
    if not items:
        return

    content = file_path.read_text() if file_path.exists() else ""

    today = datetime.now().strftime("%Y-%m-%d")
    today_header = f"## {today}"

    if today_header not in content:
        new_section = f"\n{today_header}\n"
        for item in items:
            new_section += f"- {item}\n"
        content = content.rstrip() + "\n" + new_section
    else:
        lines = content.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip() == today_header:
                insert_idx = i + 1
                while insert_idx < len(lines):
                    if lines[insert_idx].startswith("## "):
                        break
                    insert_idx += 1
                break

        if insert_idx:
            new_items = [f"- {item}" for item in items]
            lines = lines[:insert_idx] + new_items + lines[insert_idx:]
            content = "\n".join(lines)

    file_path.write_text(content)


def append_knowledge(file_path: Path, items: list[str]):
    """Append knowledge/capture items."""
    if not items:
        return

    # Create file with header if it doesn't exist
    if not file_path.exists():
        content = "# Knowledge\n\n> Concepts and reference captured with [CAPTURE] tags.\n\n---\n"
    else:
        content = file_path.read_text()

    today = datetime.now().strftime("%Y-%m-%d")
    today_header = f"## {today}"

    if today_header not in content:
        new_section = f"\n{today_header}\n\n"
        for item in items:
            # Preserve multiline content with proper indentation
            new_section += f"{item}\n\n"
        content = content.rstrip() + "\n" + new_section
    else:
        lines = content.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip() == today_header:
                insert_idx = i + 1
                # Skip empty line after header
                while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                    insert_idx += 1
                break

        if insert_idx:
            new_items = [f"{item}\n" for item in items]
            lines = lines[:insert_idx] + new_items + lines[insert_idx:]
            content = "\n".join(lines)

    file_path.write_text(content)


def write_session_log(project_path: Path, extract: SessionExtract):
    """Write a session log file."""
    today = datetime.now().strftime("%Y-%m-%d")
    session_file = project_path / "sessions" / f"{today}.md"

    # If file exists, append a separator
    if session_file.exists():
        content = session_file.read_text()
        content += "\n\n---\n\n"
    else:
        content = ""

    timestamp = datetime.now().strftime("%H:%M")
    content += f"# Session: {today} {timestamp}\n\n"

    content += f"## Summary\n{extract.summary}\n\n"

    if extract.files_touched:
        content += "## Files Touched\n"
        for f in extract.files_touched:
            content += f"- `{f}`\n"
        content += "\n"

    if extract.next_steps:
        content += "## Next Steps Identified\n"
        for item in extract.next_steps:
            content += f"- [ ] {item}\n"
        content += "\n"

    if extract.completed:
        content += "## Completed This Session\n"
        for item in extract.completed:
            content += f"- [x] {item}\n"
        content += "\n"

    if extract.decisions:
        content += "## Decisions Made\n"
        for item in extract.decisions:
            content += f"- {item}\n"
        content += "\n"

    if extract.blockers:
        content += "## Blockers\n"
        for item in extract.blockers:
            content += f"- {item}\n"
        content += "\n"

    if extract.github_refs:
        content += "## GitHub References\n"
        for ref in extract.github_refs:
            content += f"- {ref}\n"
        content += "\n"

    if extract.knowledge:
        content += "## Knowledge Captured\n"
        for item in extract.knowledge:
            content += f"{item}\n\n"

    session_file.write_text(content)


def update_vault(project_name: str, extract: SessionExtract):
    """Update all vault files for a project."""
    project_path = ensure_project_folder(project_name)

    # Update consolidated files
    append_to_file(project_path / "next-steps.md", extract.next_steps)
    append_completed(project_path / "completed.md", extract.completed)
    append_decisions(project_path / "decisions.md", extract.decisions)
    append_to_file(project_path / "blockers.md", extract.blockers)
    append_decisions(project_path / "github-refs.md", extract.github_refs)
    append_knowledge(project_path / "knowledge.md", extract.knowledge)

    # Write session log
    write_session_log(project_path, extract)

    return project_path
