"""CLI entry point: python -m obsidian_agent"""
import argparse
import sys
from datetime import datetime

from . import __version__
from .config import load_config, init_config
from .extractor import extract_with_claude
from .parser import parse_session_log, get_conversation_text
from .session_finder import (
    get_current_session_log,
    get_session_log_by_id,
    get_session_log_by_project,
    list_recent_projects,
)
from .git_helper import get_recent_commits
from .vault_writer import VaultWriter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-agent",
        description="Second Brain agent — capture Claude Code sessions as project state",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Source selection (mutually exclusive)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--session", "-s",
        help="Process a specific session by ID",
    )
    source.add_argument(
        "--project", "-p",
        help="Process most recent session for a project path",
    )
    source.add_argument(
        "--all-projects",
        action="store_true",
        help="Update all projects with recent sessions",
    )

    # Rollup generation
    parser.add_argument(
        "--weekly",
        nargs="?",
        const="",
        default=None,
        metavar="YYYY-Wnn",
        help="Generate weekly rollup (default: current week)",
    )
    parser.add_argument(
        "--monthly",
        nargs="?",
        const="",
        default=None,
        metavar="YYYY-MM",
        help="Generate monthly rollup (default: current month)",
    )

    # Actions
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create config.toml interactively",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview extraction without writing to vault",
    )

    return parser


def _print_extract(extract):
    """Pretty-print an extraction for dry-run."""
    print(f"\n  Status:      {extract.status}")
    print(f"  Phase:       {extract.phase}")
    print(f"  Summary:     {extract.summary}")
    if extract.completed_groups:
        print(f"  Completed Groups:")
        for g in extract.completed_groups:
            print(f"    {g.heading}:")
            for item in g.items:
                print(f"      - {item}")
    else:
        print(f"  Completed:   {extract.completed}")
    if extract.issues:
        print(f"  Issues:")
        for i in extract.issues:
            print(f"    {i.number} {i.title} ({i.effort}) [{i.status}]")
    if extract.commits:
        print(f"  Commits:")
        for c in extract.commits:
            print(f"    {c.hash} {c.message}")
    print(f"  Next Steps:  {extract.next_steps}")
    print(f"  Decisions:   {extract.decisions}")
    print(f"  Blockers:    {extract.blockers}")
    print(f"  GitHub Refs: {extract.github_refs}")
    print(f"  Notes:       {extract.notes}")
    print(f"  Knowledge:   {extract.knowledge}")


def _process_session(log_path, config, dry_run: bool):
    """Parse, extract, and write a single session."""
    print(f"Processing: {log_path}")

    session = parse_session_log(log_path)
    print(f"  Project:  {session.project_name}")
    print(f"  Messages: {len(session.messages)}")
    print(f"  Date:     {session.date}")

    conversation = get_conversation_text(session, config.max_conversation_chars)

    print(f"  Extracting with Claude ({config.extraction_model})...")
    extract = extract_with_claude(conversation, model=config.extraction_model)

    # Inject git commits (deterministic, no LLM)
    if session.project_path:
        today = datetime.now().strftime("%Y-%m-%d")
        commits = get_recent_commits(session.project_path, since_date=today)
        if commits:
            extract.commits = commits
            print(f"  Commits:  {len(commits)} found")

    if dry_run:
        print("\n=== DRY RUN — would write: ===")
        _print_extract(extract)
        return

    writer = VaultWriter(config)
    today = datetime.now().strftime("%Y-%m-%d")
    paths = writer.update(session.project_name, extract, date=today)
    print(f"\n  STATUS:    {paths['status']}")
    print(f"  Daily:     {paths['daily']}")
    print(f"  DASHBOARD: {paths['dashboard']}")


def main(argv: list[str] | None = None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --init: create config and exit
    if args.init:
        init_config()
        return

    config = load_config()

    # --weekly / --monthly: generate rollups
    if args.weekly is not None or args.monthly is not None:
        writer = VaultWriter(config)

        if args.weekly is not None:
            week = args.weekly  # empty string means current week
            if args.all_projects or not args.project:
                paths = writer.generate_weekly_all(week)
                for p in paths:
                    print(f"Weekly: {p}")
            else:
                project_name = args.project.rstrip("/").split("/")[-1]
                path = writer.generate_weekly(project_name, week)
                print(f"Weekly: {path}")

        if args.monthly is not None:
            month = args.monthly
            if args.all_projects or not args.project:
                paths = writer.generate_monthly_all(month)
                for p in paths:
                    print(f"Monthly: {p}")
            else:
                project_name = args.project.rstrip("/").split("/")[-1]
                path = writer.generate_monthly(project_name, month)
                print(f"Monthly: {path}")

        return

    # --all-projects: update every recent project
    if args.all_projects:
        recent = list_recent_projects(config)
        if not recent:
            print("No recent projects found.")
            return
        for name, log_path in recent:
            try:
                _process_session(log_path, config, args.dry_run)
            except Exception as e:
                print(f"  Error processing {name}: {e}", file=sys.stderr)
        return

    # Single session
    try:
        if args.session:
            log_path = get_session_log_by_id(config, args.session)
        elif args.project:
            log_path = get_session_log_by_project(config, args.project)
        else:
            log_path = get_current_session_log(config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _process_session(log_path, config, args.dry_run)


if __name__ == "__main__":
    main()
