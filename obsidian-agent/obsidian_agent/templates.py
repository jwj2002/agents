"""Markdown templates for vault files."""
from datetime import datetime

# ---------------------------------------------------------------------------
# PROJECT.md — hub/identity document (slow-changing, no temporal content)
# ---------------------------------------------------------------------------
PROJECT_TEMPLATE = """\
---
type: project
status: {meta_status}
health: {meta_health}
priority: {meta_priority}
category: {meta_category}
phase: "{phase}"
top_blocker: "{top_blocker}"
---

# {project_name}

> Last updated: {updated}

## Current Phase
{phase}

## Active Blockers
{blockers}

## Active Workstreams
{next_steps}

## Key Decisions

{decisions_table}

## GitHub References
{github_refs}

## Recent Activity
{recent_activity}
"""

# ---------------------------------------------------------------------------
# DASHBOARD.md — cross-project overview (overwritten)
# ---------------------------------------------------------------------------
DASHBOARD_TEMPLATE = """\
# Dashboard

> Auto-generated: {updated}

| Project | Phase | Health | Priority | Category | Top Blocker | Last Updated |
|---------|-------|--------|----------|----------|-------------|--------------|
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
# Cross-project daily rollup — Rollups/Daily/YYYY-MM-DD.md
# ---------------------------------------------------------------------------
DAILY_ROLLUP_TEMPLATE = """\
# Daily Rollup: {date}

> Auto-generated: {generated}

## Summary

| Project | Status | Key Activity |
|---------|--------|-------------|
{summary_rows}

{project_sections}
"""

DAILY_ROLLUP_PROJECT_SECTION = """\
## {project_name}

**Status**: {status}

### Completed
{completed}

### Decisions
{decisions}

### Blockers
{blockers}

### Follow-up
{next_steps}

**GitHub Refs**: {github_refs}
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

# ---------------------------------------------------------------------------
# Shared rollup project section (used by multi-project weekly/monthly)
# ---------------------------------------------------------------------------
ROLLUP_PROJECT_SECTION = """\
## {project_name}

### Completed
{completed}

### Decisions
{decisions}

### Blockers
{blockers}

### GitHub References
{github_refs}
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


def render_project(
    project_name: str,
    extract,
    updated: str | None = None,
    recent_dates: list[str] | None = None,
) -> str:
    """Render PROJECT.md — hub document with identity info, not temporal content."""
    updated = updated or datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")

    # Build decisions table (date + decision + link to daily log)
    decisions_table = _render_decisions_table(extract.decisions, today)

    # Build recent activity links
    if recent_dates:
        recent_activity = "\n".join(f"- [[{d}]]" for d in recent_dates[:5])
    else:
        recent_activity = f"- [[{today}]]"

    # Top blocker for frontmatter
    top_blocker = extract.blockers[0] if extract.blockers else "none"

    return PROJECT_TEMPLATE.format(
        project_name=project_name,
        updated=updated,
        phase=extract.phase or "_Not specified_",
        next_steps=_checkbox_list(extract.next_steps),
        decisions_table=decisions_table,
        blockers=_bullet_list(extract.blockers),
        github_refs=_bullet_list(extract.github_refs),
        recent_activity=recent_activity,
        meta_status=extract.meta_status,
        meta_health=extract.health,
        meta_priority=extract.priority,
        meta_category=extract.category,
        top_blocker=top_blocker,
    )


def _render_decisions_table(decisions: list[str], date: str) -> str:
    """Render decisions as a table with date and daily log link."""
    if not decisions:
        return "_No decisions recorded yet_"
    lines = [
        "| Date | Decision | Daily Log |",
        "|------|----------|-----------|",
    ]
    for d in decisions:
        lines.append(f"| {date} | {d} | [[{date}]] |")
    return "\n".join(lines)


def render_dashboard_row(project_name: str, extract, updated: str) -> str:
    """Render a single row for the DASHBOARD table."""
    phase = extract.phase or "—"
    health = extract.health
    priority = extract.priority
    category = extract.category
    top_blocker = extract.blockers[0] if extract.blockers else "—"
    return f"| [[{project_name}]] | {phase} | {health} | {priority} | {category} | {top_blocker} | {updated} |"


def render_dashboard(rows: list[str], updated: str | None = None) -> str:
    """Render DASHBOARD.md content."""
    updated = updated or datetime.now().strftime("%Y-%m-%d %H:%M")
    return DASHBOARD_TEMPLATE.format(
        updated=updated,
        rows="\n".join(rows) if rows else "| _No projects yet_ | | | | | | |",
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


def render_daily_rollup(
    date: str,
    summary_rows: list[str],
    project_sections: list[str],
) -> str:
    """Render cross-project daily rollup."""
    return DAILY_ROLLUP_TEMPLATE.format(
        date=date,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        summary_rows="\n".join(summary_rows) if summary_rows else "| _No activity_ | | |",
        project_sections="\n".join(project_sections),
    )


def render_daily_rollup_project(
    project_name: str,
    status: str,
    completed: list[str],
    decisions: list[str],
    blockers: list[str],
    next_steps: list[str],
    github_refs: list[str],
) -> str:
    """Render a single project section in the daily rollup."""
    return DAILY_ROLLUP_PROJECT_SECTION.format(
        project_name=project_name,
        status=status or "—",
        completed=_bullet_list(completed),
        decisions=_bullet_list(decisions),
        blockers=_bullet_list(blockers),
        next_steps=_checkbox_list(next_steps),
        github_refs=", ".join(github_refs) if github_refs else "_None_",
    )


def render_rollup_project_section(
    project_name: str,
    completed: list[str],
    decisions: list[str],
    blockers: list[str],
    github_refs: list[str],
) -> str:
    """Render a project section for multi-project weekly/monthly rollups."""
    return ROLLUP_PROJECT_SECTION.format(
        project_name=project_name,
        completed=_bullet_list(completed),
        decisions=_bullet_list(decisions),
        blockers=_bullet_list(blockers),
        github_refs=_bullet_list(github_refs),
    )


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


def render_weekly_multi(
    week: str,
    project_sections: list[str],
) -> str:
    """Render a cross-project weekly rollup."""
    return WEEKLY_MULTI_PROJECT_TEMPLATE.format(
        week=week,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        project_sections="\n".join(project_sections),
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


def render_monthly_multi(
    month: str,
    project_sections: list[str],
) -> str:
    """Render a cross-project monthly rollup."""
    return MONTHLY_MULTI_PROJECT_TEMPLATE.format(
        month=month,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        project_sections="\n".join(project_sections),
    )
