#!/usr/bin/env python3
"""
Obsidian Vault Update Agent

Parses Claude Code conversation logs and updates Obsidian vault with:
- Next steps
- Completed items
- Decisions
- Blockers
- GitHub references
- Session logs

Usage:
    python update_vault.py                    # Update from current session
    python update_vault.py --session <id>     # Update from specific session
    python update_vault.py --project <path>   # Update from specific project path
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add the script directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import CLAUDE_PROJECTS_PATH
from parser import parse_session_log, get_conversation_text
from extractor import extract_with_claude
from vault_writer import update_vault


def get_current_session_log() -> Path:
    """Find the current session's log file based on CWD."""
    cwd = os.getcwd()

    # Convert path to Claude's folder naming convention
    folder_name = cwd.replace("/", "-")
    if folder_name.startswith("-"):
        folder_name = folder_name  # Keep leading dash

    project_folder = CLAUDE_PROJECTS_PATH / folder_name

    if not project_folder.exists():
        # Try without leading dash
        folder_name = cwd.replace("/", "-").lstrip("-")
        project_folder = CLAUDE_PROJECTS_PATH / f"-{folder_name}"

    if not project_folder.exists():
        raise FileNotFoundError(
            f"No Claude project folder found for {cwd}\n"
            f"Looked in: {CLAUDE_PROJECTS_PATH}"
        )

    # Find the most recent session log
    sessions_index = project_folder / "sessions-index.json"
    if sessions_index.exists():
        with open(sessions_index) as f:
            index = json.load(f)
            entries = index.get("entries", [])
            if entries:
                # Get most recent by modification time
                latest = max(entries, key=lambda e: e.get("modified", ""))
                return Path(latest["fullPath"])

    # Fallback: find most recent .jsonl file
    jsonl_files = list(project_folder.glob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"No session logs found in {project_folder}")

    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def get_session_log_by_id(session_id: str) -> Path:
    """Find a session log by its ID."""
    for project_folder in CLAUDE_PROJECTS_PATH.iterdir():
        if not project_folder.is_dir():
            continue
        log_file = project_folder / f"{session_id}.jsonl"
        if log_file.exists():
            return log_file

    raise FileNotFoundError(f"Session {session_id} not found")


def get_session_log_by_project(project_path: str) -> Path:
    """Find the most recent session log for a project path."""
    folder_name = project_path.replace("/", "-")
    if not folder_name.startswith("-"):
        folder_name = "-" + folder_name

    project_folder = CLAUDE_PROJECTS_PATH / folder_name

    if not project_folder.exists():
        raise FileNotFoundError(f"No Claude project folder found for {project_path}")

    # Find most recent session
    sessions_index = project_folder / "sessions-index.json"
    if sessions_index.exists():
        with open(sessions_index) as f:
            index = json.load(f)
            entries = index.get("entries", [])
            if entries:
                latest = max(entries, key=lambda e: e.get("modified", ""))
                return Path(latest["fullPath"])

    jsonl_files = list(project_folder.glob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"No session logs found in {project_folder}")

    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(
        description="Update Obsidian vault from Claude Code session"
    )
    parser.add_argument(
        "--session", "-s",
        help="Session ID to process"
    )
    parser.add_argument(
        "--project", "-p",
        help="Project path to process"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be extracted without writing"
    )

    args = parser.parse_args()

    # Find the session log
    try:
        if args.session:
            log_path = get_session_log_by_id(args.session)
        elif args.project:
            log_path = get_session_log_by_project(args.project)
        else:
            log_path = get_current_session_log()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Processing: {log_path}")

    # Parse the session
    session = parse_session_log(log_path)
    print(f"Project: {session.project_name}")
    print(f"Messages: {len(session.messages)}")

    # Get conversation text
    conversation = get_conversation_text(session)

    # Extract information using Claude
    print("Extracting information with Claude...")
    extract = extract_with_claude(conversation)

    if args.dry_run:
        print("\n=== DRY RUN - Would extract: ===")
        print(f"\nSummary: {extract.summary}")
        print(f"\nNext Steps: {extract.next_steps}")
        print(f"\nCompleted: {extract.completed}")
        print(f"\nDecisions: {extract.decisions}")
        print(f"\nBlockers: {extract.blockers}")
        print(f"\nGitHub Refs: {extract.github_refs}")
        print(f"\nFiles: {extract.files_touched}")
        print(f"\nKnowledge: {extract.knowledge}")
        return

    # Update the vault
    project_path = update_vault(session.project_name, extract)
    print(f"\nVault updated: {project_path}")
    print(f"  - Next steps: {len(extract.next_steps)} items")
    print(f"  - Completed: {len(extract.completed)} items")
    print(f"  - Decisions: {len(extract.decisions)} items")
    print(f"  - Blockers: {len(extract.blockers)} items")
    print(f"  - GitHub refs: {len(extract.github_refs)} items")
    print(f"  - Knowledge: {len(extract.knowledge)} items")


if __name__ == "__main__":
    main()
