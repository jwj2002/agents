"""Write project state to Obsidian vault.

Design:
- STATUS.md is OVERWRITTEN each session (current state at a glance)
- Daily logs are APPEND-ONLY (event history for rollups)
- DASHBOARD.md is OVERWRITTEN (cross-project overview)
- Weekly/Monthly are GENERATED on demand from daily logs
- Rollups/ contains cross-project aggregations
"""
import os
import re
from datetime import datetime
from pathlib import Path

from .config import Config
from .extractor import SessionExtract
from .templates import (
    render_daily_entry,
    render_daily_header,
    render_daily_rollup,
    render_daily_rollup_project,
    render_dashboard,
    render_dashboard_row,
    render_monthly,
    render_monthly_multi,
    render_rollup_project_section,
    render_status,
    render_weekly,
    render_weekly_multi,
)


class VaultWriter:
    """Writes extracted session data to the Obsidian vault."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.vault = config.vault_path
        self.projects = config.projects_path

    def _project_dir(self, project_name: str) -> Path:
        """Get (and create if needed) the project directory."""
        d = self.projects / project_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _log_dir(self, project_name: str, period: str) -> Path:
        """Get (and create if needed) a log subdirectory (Daily/Weekly/Monthly)."""
        d = self._project_dir(project_name) / "Log" / period
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _rollup_dir(self, period: str) -> Path:
        """Get (and create if needed) a cross-project rollup directory."""
        d = self.vault / "Rollups" / period
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Core writes
    # ------------------------------------------------------------------

    def write_status(self, project_name: str, extract: SessionExtract) -> Path:
        """Overwrite STATUS.md with current project state.

        Preserves user-edited frontmatter (health, priority, category) from
        the existing STATUS.md before overwriting.
        """
        path = self._project_dir(project_name) / "STATUS.md"

        # Preserve existing frontmatter metadata
        if path.exists():
            existing_meta = self._parse_frontmatter(path)
            if existing_meta.get("status"):
                extract.meta_status = existing_meta["status"]
            if existing_meta.get("health"):
                extract.health = existing_meta["health"]
            if existing_meta.get("priority"):
                extract.priority = existing_meta["priority"]
            if existing_meta.get("category"):
                extract.category = existing_meta["category"]

        content = render_status(project_name, extract)
        path.write_text(content)
        return path

    def write_daily(self, project_name: str, extract: SessionExtract, date: str = "") -> Path:
        """Append a session entry to the daily log.

        If an entry for this project already exists for today, consolidates
        by replacing the existing section with merged data.
        """
        date = date or datetime.now().strftime("%Y-%m-%d")
        log_dir = self._log_dir(project_name, "Daily")
        path = log_dir / f"{date}.md"

        if not path.exists():
            path.write_text(render_daily_header(date))

        entry = render_daily_entry(project_name, extract)

        # Check for existing entry for this project today
        existing = path.read_text()
        project_header = f"— {project_name}"
        summary_line = f"**Summary**: {extract.summary or '_No summary_'}"

        # Exact duplicate check (same project + same summary = skip)
        if project_header in existing and summary_line in existing:
            return path

        # Consolidation: if project already has an entry today, replace it
        if project_header in existing:
            consolidated = self._consolidate_daily_entry(existing, project_name, extract)
            # Atomic write: write to temp then replace
            tmp = path.with_suffix(".tmp")
            tmp.write_text(consolidated)
            os.replace(tmp, path)
            return path

        # No existing entry — append
        with open(path, "a") as f:
            f.write(entry)

        return path

    def write_dashboard(self) -> Path:
        """Overwrite DASHBOARD.md by reading all STATUS.md files."""
        rows = []

        if not self.projects.exists():
            dashboard = self.vault / "DASHBOARD.md"
            dashboard.write_text(render_dashboard([]))
            return dashboard

        for project_dir in sorted(self.projects.iterdir()):
            if not project_dir.is_dir():
                continue
            status_file = project_dir / "STATUS.md"
            if not status_file.exists():
                continue

            project_name = project_dir.name
            extract = self._parse_status_file(status_file)
            updated = self._get_file_date(status_file)
            rows.append(render_dashboard_row(project_name, extract, updated))

        dashboard = self.vault / "DASHBOARD.md"
        dashboard.write_text(render_dashboard(rows))
        return dashboard

    # ------------------------------------------------------------------
    # Rollup generation (per-project)
    # ------------------------------------------------------------------

    def generate_weekly(self, project_name: str, week: str = "") -> Path:
        """Aggregate daily logs into a weekly rollup for one project."""
        if not week:
            now = datetime.now()
            week = f"{now.year}-W{now.isocalendar()[1]:02d}"

        daily_dir = self._log_dir(project_name, "Daily")
        completed, decisions, blockers, github_refs = self._aggregate_dailies(
            daily_dir, week=week
        )

        weekly_dir = self._log_dir(project_name, "Weekly")
        path = weekly_dir / f"{week}.md"
        content = render_weekly(week, project_name, completed, decisions, blockers, github_refs)
        path.write_text(content)
        return path

    def generate_monthly(self, project_name: str, month: str = "") -> Path:
        """Aggregate daily logs into a monthly rollup for one project."""
        if not month:
            month = datetime.now().strftime("%Y-%m")

        daily_dir = self._log_dir(project_name, "Daily")
        completed, decisions, blockers, github_refs = self._aggregate_dailies(
            daily_dir, month=month
        )

        monthly_dir = self._log_dir(project_name, "Monthly")
        path = monthly_dir / f"{month}.md"
        content = render_monthly(month, project_name, completed, decisions, blockers, github_refs)
        path.write_text(content)
        return path

    def generate_weekly_all(self, week: str = "") -> list[Path]:
        """Generate weekly rollups for all projects."""
        paths = []
        if not self.projects.exists():
            return paths
        for project_dir in sorted(self.projects.iterdir()):
            if project_dir.is_dir() and (project_dir / "Log" / "Daily").exists():
                paths.append(self.generate_weekly(project_dir.name, week))
        return paths

    def generate_monthly_all(self, month: str = "") -> list[Path]:
        """Generate monthly rollups for all projects."""
        paths = []
        if not self.projects.exists():
            return paths
        for project_dir in sorted(self.projects.iterdir()):
            if project_dir.is_dir() and (project_dir / "Log" / "Daily").exists():
                paths.append(self.generate_monthly(project_dir.name, month))
        return paths

    # ------------------------------------------------------------------
    # Cross-project rollups (NEW)
    # ------------------------------------------------------------------

    def generate_daily_rollup(self, date: str = "") -> Path:
        """Generate a cross-project daily rollup aggregating all projects."""
        date = date or datetime.now().strftime("%Y-%m-%d")
        rollup_dir = self._rollup_dir("Daily")
        path = rollup_dir / f"{date}.md"

        summary_rows = []
        project_sections = []

        if self.projects.exists():
            for project_dir in sorted(self.projects.iterdir()):
                if not project_dir.is_dir():
                    continue

                daily_file = project_dir / "Log" / "Daily" / f"{date}.md"
                status_file = project_dir / "STATUS.md"
                if not daily_file.exists():
                    continue

                project_name = project_dir.name
                content = daily_file.read_text()

                # Get status from STATUS.md
                status_text = "—"
                if status_file.exists():
                    status_extract = self._parse_status_file(status_file)
                    status_text = status_extract.status or "—"

                # Extract data from daily log
                completed = _extract_section_bullets(content, "Completed")
                decisions = _extract_section_bullets(content, "Decisions")
                blockers = _extract_section_bullets(content, "Blockers")
                next_steps = _extract_section_items(content, "Follow-up")
                github_refs = _extract_github_refs(content)

                # Summary row: first completed item as key activity
                key_activity = completed[0] if completed else "—"
                summary_rows.append(
                    f"| {project_name} | {status_text} | {key_activity} |"
                )

                project_sections.append(render_daily_rollup_project(
                    project_name=project_name,
                    status=status_text,
                    completed=_dedup(completed),
                    decisions=_dedup(decisions),
                    blockers=_dedup(blockers),
                    next_steps=_dedup(next_steps),
                    github_refs=_dedup(github_refs),
                ))

        content = render_daily_rollup(date, summary_rows, project_sections)
        path.write_text(content)
        return path

    def generate_weekly_rollup(self, week: str = "") -> Path:
        """Generate a cross-project weekly rollup."""
        if not week:
            now = datetime.now()
            week = f"{now.year}-W{now.isocalendar()[1]:02d}"

        rollup_dir = self._rollup_dir("Weekly")
        path = rollup_dir / f"{week}.md"

        project_sections = []
        if self.projects.exists():
            for project_dir in sorted(self.projects.iterdir()):
                if not project_dir.is_dir():
                    continue
                daily_dir = project_dir / "Log" / "Daily"
                if not daily_dir.exists():
                    continue

                completed, decisions, blockers, github_refs = self._aggregate_dailies(
                    daily_dir, week=week
                )
                # Skip projects with no activity this week
                if not any([completed, decisions, blockers, github_refs]):
                    continue

                project_sections.append(render_rollup_project_section(
                    project_name=project_dir.name,
                    completed=completed,
                    decisions=decisions,
                    blockers=blockers,
                    github_refs=github_refs,
                ))

        content = render_weekly_multi(week, project_sections)
        path.write_text(content)
        return path

    def generate_monthly_rollup(self, month: str = "") -> Path:
        """Generate a cross-project monthly rollup."""
        if not month:
            month = datetime.now().strftime("%Y-%m")

        rollup_dir = self._rollup_dir("Monthly")
        path = rollup_dir / f"{month}.md"

        project_sections = []
        if self.projects.exists():
            for project_dir in sorted(self.projects.iterdir()):
                if not project_dir.is_dir():
                    continue
                daily_dir = project_dir / "Log" / "Daily"
                if not daily_dir.exists():
                    continue

                completed, decisions, blockers, github_refs = self._aggregate_dailies(
                    daily_dir, month=month
                )
                if not any([completed, decisions, blockers, github_refs]):
                    continue

                project_sections.append(render_rollup_project_section(
                    project_name=project_dir.name,
                    completed=completed,
                    decisions=decisions,
                    blockers=blockers,
                    github_refs=github_refs,
                ))

        content = render_monthly_multi(month, project_sections)
        path.write_text(content)
        return path

    # ------------------------------------------------------------------
    # Convenience: full update
    # ------------------------------------------------------------------

    def update(self, project_name: str, extract: SessionExtract, date: str = "") -> dict[str, Path]:
        """Full update: STATUS + Daily + DASHBOARD."""
        status_path = self.write_status(project_name, extract)
        daily_path = self.write_daily(project_name, extract, date)
        dashboard_path = self.write_dashboard()
        return {
            "status": status_path,
            "daily": daily_path,
            "dashboard": dashboard_path,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(path: Path) -> dict[str, str]:
        """Parse YAML frontmatter from a markdown file."""
        try:
            content = path.read_text()
        except OSError:
            return {}

        if not content.startswith("---"):
            return {}

        end = content.find("---", 3)
        if end < 0:
            return {}

        frontmatter = {}
        for line in content[3:end].strip().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()
        return frontmatter

    @staticmethod
    def _parse_status_file(path: Path) -> SessionExtract:
        """Parse a STATUS.md back into a minimal SessionExtract for the dashboard."""
        content = path.read_text()

        # Parse frontmatter for metadata
        meta = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                for line in content[3:end].strip().splitlines():
                    if ":" in line:
                        key, _, value = line.partition(":")
                        meta[key.strip()] = value.strip()

        def _section(header: str) -> list[str]:
            pattern = rf"## {header}\n(.*?)(?=\n## |\Z)"
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                return []
            text = m.group(1).strip()
            if text in ("_None_", "_Unknown_", "_Not specified_"):
                return []
            items = []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("- [ ] "):
                    items.append(line[6:].strip())
                elif line.startswith("- [x] "):
                    items.append(line[6:].strip())
                elif line.startswith("- "):
                    items.append(line[2:].strip())
            return items

        def _section_text(header: str) -> str:
            pattern = rf"## {header}\n(.*?)(?=\n## |\Z)"
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                return ""
            text = m.group(1).strip()
            return "" if text.startswith("_") else text

        return SessionExtract(
            status=_section_text("Status"),
            phase=_section_text("Phase"),
            summary="",
            next_steps=_section("Follow-up") or _section("Next Steps"),
            decisions=_section("Decisions"),
            blockers=_section("Blockers"),
            github_refs=_section("GitHub References"),
            meta_status=meta.get("status", "active"),
            health=meta.get("health", "on-track"),
            priority=meta.get("priority", "P2"),
            category=meta.get("category", "work"),
        )

    @staticmethod
    def _get_file_date(path: Path) -> str:
        """Get the last-modified date of a file as YYYY-MM-DD."""
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    @staticmethod
    def _consolidate_daily_entry(
        existing_content: str, project_name: str, new_extract: SessionExtract
    ) -> str:
        """Replace existing project section in daily log with consolidated data.

        Merges completed items, decisions, blockers etc. from the existing
        section with the new extract, then replaces the section in place.
        """
        # Split on section dividers
        sections = re.split(r"\n---\n", existing_content)

        new_sections = []
        replaced = False

        for section in sections:
            if f"— {project_name}" in section and not replaced:
                # This is the section to replace — render fresh with new extract
                new_entry = render_daily_entry(project_name, new_extract)
                # Strip leading newlines since we re-join with \n---\n
                new_entry = new_entry.lstrip("\n")
                new_sections.append(new_entry)
                replaced = True
            else:
                new_sections.append(section)

        return "\n---\n".join(new_sections)

    @staticmethod
    def _aggregate_dailies(
        daily_dir: Path,
        week: str = "",
        month: str = "",
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """Aggregate bullet items from daily log files for a time period.

        Returns (completed, decisions, blockers, github_refs).
        """
        completed: list[str] = []
        decisions: list[str] = []
        blockers: list[str] = []
        github_refs: list[str] = []

        if not daily_dir.exists():
            return completed, decisions, blockers, github_refs

        for daily_file in sorted(daily_dir.glob("*.md")):
            file_date = daily_file.stem  # YYYY-MM-DD

            # Filter by period
            if week:
                try:
                    dt = datetime.strptime(file_date, "%Y-%m-%d")
                    file_week = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
                    if file_week != week:
                        continue
                except ValueError:
                    continue
            elif month:
                if not file_date.startswith(month):
                    continue

            content = daily_file.read_text()

            # Extract bullet items from each section
            completed.extend(_extract_section_bullets(content, "Completed"))
            decisions.extend(_extract_section_bullets(content, "Decisions"))
            blockers.extend(_extract_section_bullets(content, "Blockers"))

            # GitHub refs are comma-separated inline, not bullets
            github_refs.extend(_extract_github_refs(content))

        # Deduplicate while preserving order
        completed = _dedup(completed)
        decisions = _dedup(decisions)
        blockers = _dedup(blockers)
        github_refs = _dedup(github_refs)

        return completed, decisions, blockers, github_refs


def _extract_section_bullets(content: str, header: str) -> list[str]:
    """Extract bullet items from a **Header**: or ## Header section in daily logs."""
    items = []

    # Try **Header**: format first (daily entry style)
    pattern = rf"\*\*{header}\*\*:\n(.*?)(?=\n\*\*|\n---|\n###|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        for line in match.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- ") and line != "- _None_":
                items.append(line[2:].strip())
        return items

    # Try ## Header format (daily entry sections)
    # Don't stop at ### since completed items may be under ### sub-headings
    pattern = rf"## {header}[^\n]*\n(.*?)(?=\n## [^#]|\n---|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        for line in match.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- _None_"):
                continue
            if line.startswith("- [x] "):
                items.append(line[6:].strip())
            elif line.startswith("- [ ] "):
                items.append(line[6:].strip())
            elif line.startswith("- "):
                items.append(line[2:].strip())

    return items


def _extract_section_items(content: str, header: str) -> list[str]:
    """Extract items from a ## Header section, handling checkboxes."""
    items = []
    pattern = rf"## {header}[^\n]*\n(.*?)(?=\n## |\n---|\n###|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        for line in match.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- _None_"):
                continue
            if line.startswith("- [ ] "):
                items.append(line[6:].strip())
            elif line.startswith("- [x] "):
                items.append(line[6:].strip())
            elif line.startswith("- "):
                items.append(line[2:].strip())
    return items


def _extract_github_refs(content: str) -> list[str]:
    """Extract GitHub refs from **GitHub Refs**: lines."""
    refs = []
    for line in content.splitlines():
        if line.startswith("**GitHub Refs**:"):
            refs_text = line.split(":", 1)[1].strip()
            if refs_text and refs_text != "_None_":
                refs.extend(r.strip() for r in refs_text.split(",") if r.strip())
    return refs


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate list while preserving order."""
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
