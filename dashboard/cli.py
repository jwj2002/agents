#!/usr/bin/env python3
"""dashboard — pure-read project status overview.

Reads filesystem YAMLs (knowledge/projects, knowledge/decisions),
per-project ACTIONS.md, and `gh issue list` per resolved repo. Organizes
by project. Never writes.

Single-machine. Cross-device is Phase 7 (see ~/agents/PLAN.md).

Update paths owned elsewhere:
- Actions:   `action` CLI (auto-commits per #121)
- Issues:    `gh issue create/close`, `/orchestrate` workflow
- Decisions: `knowledge/decisions/*.yaml` (hand-edit)
- Project frame: `/project --focus`, hand-edit YAML

Alias: `alias dashboard='python3 ~/agents/dashboard/cli.py'`
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.actions_md import (  # noqa: E402
    MarkdownParseError,
    parse_file as parse_actions_md,
    parse_files_cell,
)

HOME = Path.home()
KNOWLEDGE_DIR = HOME / "agents" / "knowledge"
PROJECTS_YAML_DIR = KNOWLEDGE_DIR / "projects"
DECISIONS_DIR = KNOWLEDGE_DIR / "decisions"
SUBSCRIPTIONS_PATH = HOME / ".claude" / "dashboard-subscriptions.json"

WINDOW_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "full": None}
DEFAULT_WINDOW = "daily"
ACTIVE_STATUSES = ("active", "paused", "blocked")
GH_TIMEOUT_SECS = 3


class DashboardError(Exception):
    """User-facing dashboard error (single-line stderr + exit 1)."""


# ---------- data ----------

@dataclass
class Project:
    name: str
    status: str
    focus: str
    next_steps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    updated_at: str = ""
    # overlays — filled in per project
    actions_open: list[dict] = field(default_factory=list)
    actions_closed: list[dict] = field(default_factory=list)
    issues_open: list[dict] = field(default_factory=list)
    issues_closed: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)


# ---------- knowledge YAML readers ----------

def load_project(name: str) -> Project | None:
    path = PROJECTS_YAML_DIR / f"{name}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    return Project(
        name=data.get("project", name),
        status=data.get("status", "unknown"),
        focus=str(data.get("focus", "") or "").strip(),
        next_steps=list(data.get("next_steps") or []),
        blockers=list(data.get("blockers") or []),
        open_questions=list(data.get("open_questions") or []),
        updated_at=str(data.get("updated_at", "") or ""),
    )


def load_all_projects() -> list[Project]:
    if not PROJECTS_YAML_DIR.exists():
        return []
    out: list[Project] = []
    for p in sorted(PROJECTS_YAML_DIR.glob("*.yaml")):
        proj = load_project(p.stem)
        if proj is not None:
            out.append(proj)
    return out


def load_decisions(project: str, since: date | None) -> list[dict]:
    if not DECISIONS_DIR.exists():
        return []
    out: list[dict] = []
    for p in sorted(DECISIONS_DIR.glob("D-*.yaml")):
        try:
            data = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError:
            continue
        if data.get("project") != project:
            continue
        d = data.get("date")
        d_iso = _coerce_date_iso(d)
        if since and d_iso and d_iso < since.isoformat():
            continue
        out.append({
            "id": data.get("id", p.stem),
            "date": d_iso or "?",
            "title": str(data.get("title", "") or "").strip(),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def _coerce_date_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        m = re.match(r"^\d{4}-\d{2}-\d{2}", value)
        return m.group(0) if m else None
    return None


# ---------- subscriptions ----------

def read_subscriptions() -> list[str]:
    """Return list of subscribed project names. Missing/empty/malformed → DashboardError."""
    if not SUBSCRIPTIONS_PATH.exists():
        raise DashboardError(
            f"{SUBSCRIPTIONS_PATH} is missing or empty.\n"
            "  Subscribe with: /project NAME --subscribe\n"
            '  Or hand-edit:   { "subscribed": ["agents", "buddy"] }'
        )
    try:
        data = json.loads(SUBSCRIPTIONS_PATH.read_text())
    except json.JSONDecodeError:
        raise DashboardError(
            f"{SUBSCRIPTIONS_PATH} is malformed (not valid JSON).\n"
            '  Restore with: { "subscribed": ["agents", "buddy"] }'
        )
    subs = data.get("subscribed") if isinstance(data, dict) else None
    if not isinstance(subs, list) or not subs:
        raise DashboardError(
            f"{SUBSCRIPTIONS_PATH} has no subscriptions.\n"
            "  Subscribe with: /project NAME --subscribe\n"
            '  Or hand-edit:   { "subscribed": ["agents", "buddy"] }'
        )
    return [str(s) for s in subs]


# ---------- ACTIONS.md overlay ----------

def project_repo_path(name: str) -> Path:
    """Convention: ~/agents for the agents project, else ~/projects/<name>."""
    if name == "agents":
        return HOME / "agents"
    return HOME / "projects" / name


def load_actions(name: str, since: date | None, owner_filter: str | None) -> tuple[list[dict], list[dict]]:
    """Return (open_rows, closed_in_window_rows). Empty if no ACTIONS.md."""
    repo = project_repo_path(name)
    actions_path = repo / "ACTIONS.md"
    if not actions_path.exists():
        return ([], [])
    try:
        model = parse_actions_md(actions_path)
    except MarkdownParseError:
        return ([], [])
    open_rows = [r for r in model.open_rows() if r]
    closed_rows = [r for r in model.closed_rows() if r]
    if owner_filter:
        of = owner_filter.lower()
        open_rows = [r for r in open_rows if (r.get("Owner") or "").lower() == of]
        closed_rows = [r for r in closed_rows if (r.get("Owner") or "").lower() == of]
    if since is not None:
        closed_rows = [
            r for r in closed_rows
            if (_coerce_date_iso(r.get("Closed")) or "") >= since.isoformat()
        ]
    return (open_rows, closed_rows)


# ---------- gh overlay ----------

def gh_slug_for_repo(repo_path: Path) -> str | None:
    if not (repo_path / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=GH_TIMEOUT_SECS,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    url = r.stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def load_issues(name: str, since: date | None) -> tuple[list[dict], list[dict]]:
    """Return (open_issues, closed_in_window_issues). Empty if no gh / not a repo."""
    repo = project_repo_path(name)
    slug = gh_slug_for_repo(repo)
    if slug is None:
        return ([], [])
    open_issues = _gh_run([
        "gh", "issue", "list", "--repo", slug, "--state", "open",
        "--limit", "100", "--json", "number,title,updatedAt",
    ])
    if since is None:
        closed_issues = _gh_run([
            "gh", "issue", "list", "--repo", slug, "--state", "closed",
            "--limit", "50", "--json", "number,title,closedAt",
        ])
    else:
        closed_issues = _gh_run([
            "gh", "issue", "list", "--repo", slug, "--state", "closed",
            "--search", f"closed:>={since.isoformat()}",
            "--limit", "50", "--json", "number,title,closedAt",
        ])
    return (open_issues, closed_issues)


def _gh_run(cmd: list[str]) -> list[dict]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=GH_TIMEOUT_SECS)
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if r.returncode != 0 or not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


# ---------- per-project assembly ----------

def populate(project: Project, since: date | None, owner_filter: str | None) -> Project:
    project.actions_open, project.actions_closed = load_actions(project.name, since, owner_filter)
    project.issues_open, project.issues_closed = load_issues(project.name, since)
    project.decisions = load_decisions(project.name, since)
    return project


def populate_parallel(projects: list[Project], since: date | None, owner_filter: str | None) -> list[Project]:
    if not projects:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(projects))) as ex:
        futures = {ex.submit(populate, p, since, owner_filter): p for p in projects}
        for fut in as_completed(futures):
            fut.result()
    return projects


# ---------- mode resolution ----------

def resolve_mode(args) -> tuple[str, str | None]:
    """Return (mode, project_name). mode ∈ {'single', 'multi'}."""
    if args.project_arg:
        return ("single", args.project_arg)
    cwd = Path.cwd().resolve()
    agents_root = HOME / "agents"
    if cwd == agents_root or agents_root in cwd.parents:
        return ("single", "agents")
    projects_root = HOME / "projects"
    try:
        rel = cwd.relative_to(projects_root)
        first = rel.parts[0] if rel.parts else None
        if first and first not in ("_archived",) and (PROJECTS_YAML_DIR / f"{first}.yaml").exists():
            return ("single", first)
    except ValueError:
        pass
    return ("multi", None)


# ---------- rendering: terminal ----------

STATUS_LABELS = {
    "active": "ACTIVE", "paused": "PAUSED", "blocked": "BLOCKED",
    "done": "DONE", "unknown": "?",
}


def _truncate(s: str, width: int) -> str:
    return s if len(s) <= width else s[: width - 1] + "…"


def _term_width() -> int:
    return shutil.get_terminal_size((100, 24)).columns


def render_terminal_single(p: Project, window: str, owner_filter: str | None) -> str:
    width = max(70, min(_term_width(), 120))
    label = STATUS_LABELS.get(p.status, p.status.upper())
    lines = []
    header = f"PROJECT: {p.name}"
    pad = max(1, width - len(header) - len(label))
    lines.append(f"{header}{' ' * pad}{label}")
    lines.append("─" * width)
    if p.focus:
        lines.append(_truncate(f"Focus:    {p.focus}", width))
    if p.blockers:
        lines.append("Blockers:")
        for b in p.blockers:
            lines.append(_truncate(f"  ⛔ {b}", width))
    if p.open_questions:
        lines.append("Open Questions:")
        for q in p.open_questions:
            lines.append(_truncate(f"  ? {q}", width))
    if p.next_steps:
        lines.append("Next Steps:")
        for i, s in enumerate(p.next_steps, 1):
            lines.append(_truncate(f"  {i}. {s}", width))
    lines.append("")
    lines.append(_actions_block(p, owner_filter, width))
    lines.append("")
    lines.append(_issues_block(p, width))
    lines.append("")
    if p.decisions:
        lines.append(f"Decisions in window ({len(p.decisions)}):")
        for d in p.decisions[:10]:
            lines.append(_truncate(f"  {d['id']}  {d['date']}  {d['title']}", width))
        lines.append("")
    lines.append(f"window: {window}")
    return "\n".join(lines).rstrip() + "\n"


def _row_with_suffix(prefix: str, body: str, suffix: str, width: int) -> str:
    """Truncate `body` so `prefix + body + suffix` fits in width without losing the suffix."""
    budget = width - len(prefix) - len(suffix)
    if budget < 5:  # not enough room for any sensible body
        return (prefix + body + suffix)[:width]
    if len(body) > budget:
        body = body[: budget - 1] + "…"
    return prefix + body + suffix


def _actions_block(p: Project, owner_filter: str | None, width: int) -> str:
    head_suffix = f" (filter: Owner={owner_filter})" if owner_filter else ""
    head = f"Actions ({len(p.actions_open)} open, {len(p.actions_closed)} closed-in-window){head_suffix}:"
    rows = []
    for r in p.actions_open:
        status = (r.get("Status") or "open").lower()
        icon = " ⚙" if status == "wip" else " ⛔" if status == "blocked" else ""
        prefix = f"  {r.get('ID', '?')}  {r.get('Owner', '?')}  "
        rows.append(_row_with_suffix(prefix, r.get("Action", ""), icon, width))
    for r in p.actions_closed:
        prefix = f"  {r.get('ID', '?')}  {r.get('Owner', '?')}  "
        suffix = f"  ✓ {r.get('Closed', '?')}"
        rows.append(_row_with_suffix(prefix, r.get("Action", ""), suffix, width))
    if not rows:
        rows.append("  (none)")
    return head + "\n" + "\n".join(rows)


def _issues_block(p: Project, width: int) -> str:
    head = f"Issues ({len(p.issues_open)} open, {len(p.issues_closed)} closed-in-window):"
    rows = []
    for issue in p.issues_open:
        prefix = f"  #{issue.get('number', '?')}  "
        rows.append(_row_with_suffix(prefix, issue.get("title", ""), "", width))
    for issue in p.issues_closed:
        closed_at = (issue.get("closedAt") or "")[:10]
        prefix = f"  #{issue.get('number', '?')}  "
        suffix = f"  ✓ {closed_at}"
        rows.append(_row_with_suffix(prefix, issue.get("title", ""), suffix, width))
    if not rows:
        rows.append("  (none)")
    return head + "\n" + "\n".join(rows)


def render_terminal_multi(projects: list[Project], window: str, owner_filter: str | None) -> str:
    out: list[str] = []
    for p in projects:
        out.append(render_terminal_single(p, window, owner_filter))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------- rendering: markdown digest ----------

def render_markdown(projects: list[Project], window: str, single: str | None,
                    owner_filter: str | None) -> str:
    today_iso = date.today().isoformat()
    target = single if single else "multi"
    lines = [f"<!-- dashboard-digest v1 {target} {window} {today_iso} -->"]
    if single:
        lines.append(f"# {single} — {window} summary ({today_iso})")
    else:
        lines.append(f"# Multi-project — {window} summary ({today_iso})")
    if owner_filter:
        lines.append(f"\n**Owner filter:** {owner_filter}")
    lines.append(f"\n**Window:** {window}")
    for p in projects:
        lines.append("")
        lines.append(f"## {p.name} ({STATUS_LABELS.get(p.status, p.status.upper())})")
        if p.focus:
            lines.append(f"**Focus:** {p.focus}")
        if p.blockers:
            lines.append("\n**Blockers:**")
            for b in p.blockers:
                lines.append(f"- {b}")
        if p.open_questions:
            lines.append("\n**Open Questions:**")
            for q in p.open_questions:
                lines.append(f"- {q}")
        if p.next_steps:
            lines.append("\n**Next Steps:**")
            for i, s in enumerate(p.next_steps, 1):
                lines.append(f"{i}. {s}")
        if p.actions_open or p.actions_closed:
            lines.append(f"\n### Actions — {len(p.actions_open)} open, {len(p.actions_closed)} closed-in-window")
            if p.actions_open:
                lines.append("| ID | Owner | Status | Opened | Action |")
                lines.append("|----|-------|--------|--------|--------|")
                for r in p.actions_open:
                    lines.append(
                        f"| {r.get('ID','?')} | {r.get('Owner','?')} | "
                        f"{r.get('Status','?')} | {r.get('Opened','-')} | "
                        f"{r.get('Action','')} |"
                    )
            if p.actions_closed:
                lines.append("\n_Closed in window:_")
                lines.append("| ID | Owner | Closed | Action |")
                lines.append("|----|-------|--------|--------|")
                for r in p.actions_closed:
                    lines.append(
                        f"| {r.get('ID','?')} | {r.get('Owner','?')} | "
                        f"{r.get('Closed','-')} | {r.get('Action','')} |"
                    )
        if p.issues_open or p.issues_closed:
            lines.append(f"\n### Issues — {len(p.issues_open)} open, {len(p.issues_closed)} closed-in-window")
            for issue in p.issues_open:
                lines.append(f"- #{issue.get('number','?')}  {issue.get('title','')}")
            for issue in p.issues_closed:
                lines.append(f"- ✓ #{issue.get('number','?')}  {issue.get('title','')}  (closed {(issue.get('closedAt') or '')[:10]})")
        if p.decisions:
            lines.append(f"\n### Decisions in window — {len(p.decisions)}")
            lines.append("| ID | Date | Title |")
            lines.append("|----|------|-------|")
            for d in p.decisions:
                lines.append(f"| {d['id']} | {d['date']} | {d['title']} |")
    return "\n".join(lines) + "\n"


# ---------- argparse ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="dashboard",
        description="Read-only project status overview. Writes belong to action/orchestrate/etc.",
    )
    p.add_argument("project_arg", nargs="?", default=None,
                   help="Project name for single-project deep view (default: cwd-detect or multi)")
    p.add_argument("--window", choices=("daily", "weekly", "monthly", "full"),
                   default=DEFAULT_WINDOW, help=f"Activity window (default: {DEFAULT_WINDOW})")
    p.add_argument("--for", dest="owner_filter", default=None,
                   help="Filter Actions to this owner (Issues/Decisions stay shared)")
    p.add_argument("--status", default=None,
                   help="Multi-project: filter projects by status (active/paused/blocked/done)")
    p.add_argument("--format", dest="fmt", choices=("terminal", "markdown"),
                   default="terminal", help="Output format (default: terminal)")
    return p.parse_args(argv)


def window_since(window: str) -> date | None:
    n = WINDOW_DAYS.get(window)
    if n is None:
        return None
    return date.today() - timedelta(days=n)


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)
        since = window_since(args.window)

        mode, name = resolve_mode(args)

        if mode == "single":
            project = load_project(name)
            if project is None:
                raise DashboardError(
                    f'project "{name}" not tracked.\n'
                    f'  Register with: /project {name} --focus "..."'
                )
            populate(project, since, args.owner_filter)
            if args.fmt == "markdown":
                sys.stdout.write(render_markdown([project], args.window, name, args.owner_filter))
            else:
                sys.stdout.write(render_terminal_single(project, args.window, args.owner_filter))
            return 0

        # multi-project
        subscribed = read_subscriptions()
        all_projects = load_all_projects()
        by_name = {p.name: p for p in all_projects}
        selected = [by_name[n] for n in subscribed if n in by_name]
        if not selected:
            stale = ", ".join(sorted(set(subscribed) - set(by_name.keys())))
            raise DashboardError(
                f"subscribed projects ({stale}) are not in the tracker.\n"
                "  Register with: /project NAME --focus \"...\"\n"
                "  Or unsubscribe: /project NAME --unsubscribe"
            )
        if args.status:
            selected = [p for p in selected if p.status == args.status]
        else:
            selected = [p for p in selected if p.status in ACTIVE_STATUSES]
        populate_parallel(selected, since, args.owner_filter)
        if args.fmt == "markdown":
            sys.stdout.write(render_markdown(selected, args.window, None, args.owner_filter))
        else:
            sys.stdout.write(render_terminal_multi(selected, args.window, args.owner_filter))
        return 0
    except DashboardError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
