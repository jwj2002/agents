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

## Next Steps
{next_steps}

## Decisions
{decisions}

## Blockers
{blockers}

## GitHub References
{github_refs}
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

**Completed**:
{completed}

**Decisions**:
{decisions}

**Blockers**:
{blockers}

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


def _first_or(items: list[str], fallback: str = "—") -> str:
    """Return first item or fallback (for dashboard table)."""
    return items[0] if items else fallback


def render_status(project_name: str, extract, updated: str | None = None) -> str:
    """Render STATUS.md content from a SessionExtract."""
    updated = updated or datetime.now().strftime("%Y-%m-%d %H:%M")
    return STATUS_TEMPLATE.format(
        project_name=project_name,
        updated=updated,
        status=extract.status or "_Unknown_",
        phase=extract.phase or "_Not specified_",
        next_steps=_bullet_list(extract.next_steps),
        decisions=_bullet_list(extract.decisions),
        blockers=_bullet_list(extract.blockers),
        github_refs=_bullet_list(extract.github_refs),
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
        completed=_bullet_list(extract.completed),
        decisions=_bullet_list(extract.decisions),
        blockers=_bullet_list(extract.blockers),
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
