"""CLI entry point: python -m obsidian_agent"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

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

CACHE_DIR = Path.home() / ".cache" / "obsidian-agent"
LAST_RUN_FILE = CACHE_DIR / "last-run"

SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"

# Locate bundled systemd unit files
_PACKAGE_DIR = Path(__file__).parent
_SYSTEMD_SRC = _PACKAGE_DIR.parent / "systemd"


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
    parser.add_argument(
        "--daily-rollup",
        nargs="?",
        const="",
        default=None,
        metavar="YYYY-MM-DD",
        help="Generate cross-project daily rollup (default: today)",
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
    parser.add_argument(
        "--since-last-run",
        action="store_true",
        help="Only process sessions modified since last run (for timer/cron use)",
    )

    # Installation
    parser.add_argument(
        "--install-systemd",
        action="store_true",
        help="Install systemd user timer for near-real-time updates",
    )
    parser.add_argument(
        "--install-launchd",
        action="store_true",
        help="Install macOS launchd agent for near-real-time updates + rollups",
    )
    parser.add_argument(
        "--install-cron",
        action="store_true",
        help="Install cron entries for nightly/weekly/monthly rollups",
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


def _read_last_run() -> float:
    """Read the last-run timestamp. Returns 0.0 if not found."""
    try:
        return float(LAST_RUN_FILE.read_text().strip())
    except (OSError, ValueError):
        return 0.0


def _write_last_run():
    """Write the current time as the last-run timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(str(time.time()))


def _install_systemd():
    """Install systemd user timer for near-real-time session processing."""
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)

    agent_dir = _PACKAGE_DIR.parent
    python_bin = sys.executable

    # Write service unit
    service_content = f"""\
[Unit]
Description=Obsidian Agent - process recent Claude sessions

[Service]
Type=oneshot
ExecStart={python_bin} -m obsidian_agent --all-projects --since-last-run
WorkingDirectory={agent_dir}
Environment=HOME={Path.home()}
"""
    service_path = SYSTEMD_DIR / "obsidian-agent-watcher.service"
    service_path.write_text(service_content)
    print(f"  Service: {service_path}")

    # Write timer unit
    timer_content = """\
[Unit]
Description=Run Obsidian Agent every 60 seconds

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
"""
    timer_path = SYSTEMD_DIR / "obsidian-agent-watcher.timer"
    timer_path.write_text(timer_content)
    print(f"  Timer:   {timer_path}")

    # Enable and start
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=True,
    )
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "obsidian-agent-watcher.timer"],
        check=True,
    )
    print("\n  Timer enabled and started.")
    subprocess.run(["systemctl", "--user", "status", "obsidian-agent-watcher.timer"])


LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCHD_WATCHER_LABEL = "com.obsidian-agent.watcher"
LAUNCHD_ROLLUP_LABEL = "com.obsidian-agent.rollups"


def _install_launchd():
    """Install macOS launchd agents for real-time updates and scheduled rollups."""
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    python_bin = sys.executable
    agent_dir = str(_PACKAGE_DIR.parent)
    log_dir = Path.home() / "Library" / "Logs" / "obsidian-agent"
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- Watcher agent (every 60 seconds) ---
    watcher_plist = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_WATCHER_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>-m</string>
        <string>obsidian_agent</string>
        <string>--all-projects</string>
        <string>--since-last-run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{agent_dir}</string>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>StandardOutPath</key>
    <string>{log_dir}/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/watcher.err</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    watcher_path = LAUNCHD_DIR / f"{LAUNCHD_WATCHER_LABEL}.plist"
    watcher_path.write_text(watcher_plist)
    print(f"  Watcher plist: {watcher_path}")

    # --- Rollup agent (daily at 11 PM, weekly Sunday 11:30 PM, monthly last day) ---
    # launchd doesn't support "last day of month" natively, so we use a single
    # daily job at 11 PM that runs all three rollup commands. The weekly and monthly
    # commands are no-ops when there's nothing new to aggregate.
    rollup_plist = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_ROLLUP_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>{python_bin} -m obsidian_agent --daily-rollup; DOW=$(date +%u); [ "$DOW" = "7" ] &amp;&amp; {python_bin} -m obsidian_agent --weekly --all-projects; DOM=$(date -v+1d +%d); [ "$DOM" = "01" ] &amp;&amp; {python_bin} -m obsidian_agent --monthly --all-projects</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{agent_dir}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_dir}/rollups.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/rollups.err</string>
</dict>
</plist>
"""
    rollup_path = LAUNCHD_DIR / f"{LAUNCHD_ROLLUP_LABEL}.plist"
    rollup_path.write_text(rollup_plist)
    print(f"  Rollup plist:  {rollup_path}")

    # Unload existing (ignore errors if not loaded)
    for label in [LAUNCHD_WATCHER_LABEL, LAUNCHD_ROLLUP_LABEL]:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", f"{LAUNCHD_DIR}/{label}.plist"],
            capture_output=True,
        )

    # Load agents
    for label, plist in [
        (LAUNCHD_WATCHER_LABEL, watcher_path),
        (LAUNCHD_ROLLUP_LABEL, rollup_path),
    ]:
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  Loaded: {label}")
        else:
            # Fallback to legacy load for older macOS
            result2 = subprocess.run(
                ["launchctl", "load", str(plist)],
                capture_output=True,
                text=True,
            )
            if result2.returncode == 0:
                print(f"  Loaded (legacy): {label}")
            else:
                print(f"  Warning: could not load {label}: {result.stderr.strip()}", file=sys.stderr)

    print(f"\n  Logs: {log_dir}/")
    print("  Check status: launchctl list | grep obsidian-agent")


def _install_cron():
    """Install cron entries for nightly/weekly/monthly rollups."""
    python_bin = sys.executable
    agent_dir = _PACKAGE_DIR.parent

    marker = "# obsidian-agent managed entries"
    entries = f"""{marker}
# Nightly: cross-project daily rollup (11:00 PM)
0 23 * * * cd {agent_dir} && {python_bin} -m obsidian_agent --daily-rollup >> /tmp/obsidian-agent-cron.log 2>&1
# Sunday: weekly rollup (11:30 PM)
30 23 * * 0 cd {agent_dir} && {python_bin} -m obsidian_agent --weekly --all-projects >> /tmp/obsidian-agent-cron.log 2>&1
# Last day of month: monthly rollup (11:30 PM)
30 23 28-31 * * [ "$$(date -d tomorrow +\\%d)" = "01" ] && cd {agent_dir} && {python_bin} -m obsidian_agent --monthly --all-projects >> /tmp/obsidian-agent-cron.log 2>&1
{marker} END
"""

    # Read existing crontab
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    existing = result.stdout if result.returncode == 0 else ""

    # Check if already installed
    if marker in existing:
        # Replace existing block
        import re
        pattern = re.escape(marker) + r".*?" + re.escape(marker) + r" END\n?"
        new_crontab = re.sub(pattern, entries, existing, flags=re.DOTALL)
        print("  Updating existing cron entries...")
    else:
        new_crontab = existing.rstrip("\n") + "\n\n" + entries if existing.strip() else entries
        print("  Adding cron entries...")

    subprocess.run(
        ["crontab", "-"],
        input=new_crontab,
        text=True,
        check=True,
    )
    print("  Cron entries installed:")
    print("    - Nightly daily rollup at 11:00 PM")
    print("    - Weekly rollup Sunday at 11:30 PM")
    print("    - Monthly rollup last day of month at 11:30 PM")


def main(argv: list[str] | None = None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --init: create config and exit
    if args.init:
        init_config()
        return

    # --install-systemd
    if args.install_systemd:
        print("Installing systemd user timer...")
        _install_systemd()
        return

    # --install-launchd
    if args.install_launchd:
        print("Installing macOS launchd agents...")
        _install_launchd()
        return

    # --install-cron
    if args.install_cron:
        print("Installing cron entries...")
        _install_cron()
        return

    config = load_config()

    # --daily-rollup: generate cross-project daily rollup
    if args.daily_rollup is not None:
        writer = VaultWriter(config)
        date = args.daily_rollup or datetime.now().strftime("%Y-%m-%d")
        path = writer.generate_daily_rollup(date)
        print(f"Daily rollup: {path}")
        return

    # --weekly / --monthly: generate rollups
    if args.weekly is not None or args.monthly is not None:
        writer = VaultWriter(config)

        if args.weekly is not None:
            week = args.weekly  # empty string means current week
            if args.all_projects or not args.project:
                # Per-project rollups
                paths = writer.generate_weekly_all(week)
                for p in paths:
                    print(f"Weekly (project): {p}")
                # Cross-project rollup
                rollup_path = writer.generate_weekly_rollup(week)
                print(f"Weekly (rollup):  {rollup_path}")
            else:
                project_name = args.project.rstrip("/").split("/")[-1]
                path = writer.generate_weekly(project_name, week)
                print(f"Weekly: {path}")

        if args.monthly is not None:
            month = args.monthly
            if args.all_projects or not args.project:
                paths = writer.generate_monthly_all(month)
                for p in paths:
                    print(f"Monthly (project): {p}")
                rollup_path = writer.generate_monthly_rollup(month)
                print(f"Monthly (rollup):  {rollup_path}")
            else:
                project_name = args.project.rstrip("/").split("/")[-1]
                path = writer.generate_monthly(project_name, month)
                print(f"Monthly: {path}")

        return

    # --all-projects: update every recent project
    if args.all_projects:
        since = _read_last_run() if args.since_last_run else 0.0
        recent = list_recent_projects(config, since_timestamp=since)
        if not recent:
            if args.since_last_run:
                # No new sessions — silent exit for timer
                _write_last_run()
                return
            print("No recent projects found.")
            return
        for name, log_path in recent:
            try:
                _process_session(log_path, config, args.dry_run)
            except Exception as e:
                print(f"  Error processing {name}: {e}", file=sys.stderr)

        if args.since_last_run:
            _write_last_run()
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
