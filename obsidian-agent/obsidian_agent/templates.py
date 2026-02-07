"""Markdown templates for vault files."""
from datetime import datetime

# ---------------------------------------------------------------------------
# STATUS.md — overwritten each session (current state at a glance)
# ---------------------------------------------------------------------------
STATUS_TEMPLATE = """\
# {project_name}

> Last updated: {updated}

## Status
{status}

## Phase
{phase}

## Completed Today
{completed_section}

## Issues
{issues_table}

## Follow-up
{next_steps}

## Decisions
{decisions}

## Blockers
{blockers}

## GitHub References
{github_refs}

## Notes
{notes}
"""

# ---------------------------------------------------------------------------
# DASHBOARD.md — cross-project overview (overwritten)
# ---------------------------------------------------------------------------
DASHBOARD_TEMPLATE = """\
# Dashboard

> Auto-generated: {updated}

| Project | Status | Phase | Next Step | Last Updated |
|---------|--------|-------|-----------|--------------|
{rows}
"""

# ---------------------------------------------------------------------------
# Daily log entry — appended to Log/Daily/YYYY-MM-DD.md
# ---------------------------------------------------------------------------
DAILY_ENTRY_TEMPLATE = """\

---

### {time} — {project_name}

**Summary**: {summary}

## Completed Today
{completed_section}

## Issues
{issues_table}

## Commits
{commits_table}

## Decisions
{decisions}

## Blockers
{blockers}

## Follow-up
{next_steps}

## Notes
{notes}

**GitHub Refs**: {github_refs}

**Knowledge**:
{knowledge}
"""

# Header for a new daily log file
DAILY_HEADER_TEMPLATE = """\
# Daily Log: {date}
"""

# ---------------------------------------------------------------------------
# Weekly rollup — generated on demand
# ---------------------------------------------------------------------------
WEEKLY_TEMPLATE = """\
# Week {week}

> Generated: {generated}

## {project_name}

### Completed
{completed}

### Decisions
{decisions}

### Blockers (end of week)
{blockers}

### GitHub References
{github_refs}
"""

WEEKLY_MULTI_PROJECT_TEMPLATE = """\
# Week {week}

> Generated: {generated}

{project_sections}
"""

# ---------------------------------------------------------------------------
# Monthly rollup — generated on demand
# ---------------------------------------------------------------------------
MONTHLY_TEMPLATE = """\
# {month}

> Generated: {generated}

## {project_name}

### Completed
{completed}

### Key Decisions
{decisions}

### Unresolved Blockers
{blockers}

### GitHub References
{github_refs}
"""

MONTHLY_MULTI_PROJECT_TEMPLATE = """\
# {month}

> Generated: {generated}

{project_sections}
"""


def _bullet_list(items: list[str], empty: str = "_None_") -> str:
    """Format a list as markdown bullets. Returns empty marker if no items."""
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _checkbox_list(items: list[str], empty: str = "_None_") -> str:
    """Format a list as markdown checkboxes. Returns empty marker if no items."""
    if not items:
        return empty
    return "\n".join(f"- [ ] {item}" for item in items)


def _first_or(items: list[str], fallback: str = "—") -> str:
    """Return first item or fallback (for dashboard table)."""
    return items[0] if items else fallback


def _render_completed_section(extract) -> str:
    """Render completed items grouped by topic, or flat if no groups."""
    if extract.completed_groups:
        lines = []
        for group in extract.completed_groups:
            lines.append(f"\n### {group.heading}")
            for item in group.items:
                lines.append(f"- [x] {item}")
        return "\n".join(lines)
    elif extract.completed:
        return "\n".join(f"- [x] {item}" for item in extract.completed)
    return "_None_"


def _render_issues_table(extract) -> str:
    """Render GitHub issues as a markdown table."""
    if not extract.issues:
        return "_None_"
    lines = [
        "| Issue | Title | Effort | Status |",
        "|-------|-------|--------|--------|",
    ]
    for issue in extract.issues:
        status_icon = {"Done": "Done", "Pending": "Pending", "In Progress": "In Progress"}.get(
            issue.status, issue.status
        )
        lines.append(f"| {issue.number} | {issue.title} | {issue.effort} | {status_icon} |")
    return "\n".join(lines)


def _render_commits_table(extract) -> str:
    """Render git commits as a markdown table."""
    if not extract.commits:
        return "_None_"
    lines = [
        "| Commit | Description |",
        "|--------|-------------|",
    ]
    for commit in extract.commits:
        lines.append(f"| {commit.hash} | {commit.message} |")
    return "\n".join(lines)


def render_status(project_name: str, extract, updated: str | None = None) -> str:
    """Render STATUS.md content from a SessionExtract."""
    updated = updated or datetime.now().strftime("%Y-%m-%d %H:%M")
    return STATUS_TEMPLATE.format(
        project_name=project_name,
        updated=updated,
        status=extract.status or "_Unknown_",
        phase=extract.phase or "_Not specified_",
        completed_section=_render_completed_section(extract),
        issues_table=_render_issues_table(extract),
        next_steps=_checkbox_list(extract.next_steps),
        decisions=_bullet_list(extract.decisions),
        blockers=_bullet_list(extract.blockers),
        github_refs=_bullet_list(extract.github_refs),
        notes=_bullet_list(extract.notes),
    )


def render_dashboard_row(project_name: str, extract, updated: str) -> str:
    """Render a single row for the DASHBOARD table."""
    status = extract.status or "—"
    phase = extract.phase or "—"
    next_step = _first_or(extract.next_steps)
    return f"| {project_name} | {status} | {phase} | {next_step} | {updated} |"


def render_dashboard(rows: list[str], updated: str | None = None) -> str:
    """Render DASHBOARD.md content."""
    updated = updated or datetime.now().strftime("%Y-%m-%d %H:%M")
    return DASHBOARD_TEMPLATE.format(
        updated=updated,
        rows="\n".join(rows) if rows else "| _No projects yet_ | | | | |",
    )


def render_daily_entry(project_name: str, extract, time: str | None = None) -> str:
    """Render a single daily log entry."""
    time = time or datetime.now().strftime("%H:%M")
    return DAILY_ENTRY_TEMPLATE.format(
        time=time,
        project_name=project_name,
        summary=extract.summary or "_No summary_",
        completed_section=_render_completed_section(extract),
        issues_table=_render_issues_table(extract),
        commits_table=_render_commits_table(extract),
        decisions=_bullet_list(extract.decisions),
        blockers=_bullet_list(extract.blockers),
        next_steps=_checkbox_list(extract.next_steps),
        notes=_bullet_list(extract.notes),
        github_refs=", ".join(extract.github_refs) if extract.github_refs else "_None_",
        knowledge=_bullet_list(extract.knowledge),
    )


def render_daily_header(date: str) -> str:
    """Render the header for a new daily log file."""
    return DAILY_HEADER_TEMPLATE.format(date=date)


def render_weekly(
    week: str,
    project_name: str,
    completed: list[str],
    decisions: list[str],
    blockers: list[str],
    github_refs: list[str],
) -> str:
    """Render a weekly rollup for one project."""
    return WEEKLY_TEMPLATE.format(
        week=week,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        project_name=project_name,
        completed=_bullet_list(completed),
        decisions=_bullet_list(decisions),
        blockers=_bullet_list(blockers),
        github_refs=_bullet_list(github_refs),
    )


def render_monthly(
    month: str,
    project_name: str,
    completed: list[str],
    decisions: list[str],
    blockers: list[str],
    github_refs: list[str],
) -> str:
    """Render a monthly rollup for one project."""
    return MONTHLY_TEMPLATE.format(
        month=month,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        project_name=project_name,
        completed=_bullet_list(completed),
        decisions=_bullet_list(decisions),
        blockers=_bullet_list(blockers),
        github_refs=_bullet_list(github_refs),
    )
