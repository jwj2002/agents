"""Write project state to Obsidian vault.

Design:
- STATUS.md is OVERWRITTEN each session (current state at a glance)
- Daily logs are APPEND-ONLY (event history for rollups)
- DASHBOARD.md is OVERWRITTEN (cross-project overview)
- Weekly/Monthly are GENERATED on demand from daily logs
"""
import re
from datetime import datetime
from pathlib import Path

from .config import Config
from .extractor import SessionExtract
from .templates import (
    render_daily_entry,
    render_daily_header,
    render_dashboard,
    render_dashboard_row,
    render_monthly,
    render_status,
    render_weekly,
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

    # ------------------------------------------------------------------
    # Core writes
    # ------------------------------------------------------------------

    def write_status(self, project_name: str, extract: SessionExtract) -> Path:
        """Overwrite STATUS.md with current project state."""
        path = self._project_dir(project_name) / "STATUS.md"
        content = render_status(project_name, extract)
        path.write_text(content)
        return path

    def write_daily(self, project_name: str, extract: SessionExtract, date: str = "") -> Path:
        """Append a session entry to the daily log."""
        date = date or datetime.now().strftime("%Y-%m-%d")
        log_dir = self._log_dir(project_name, "Daily")
        path = log_dir / f"{date}.md"

        if not path.exists():
            path.write_text(render_daily_header(date))

        entry = render_daily_entry(project_name, extract)
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
    # Rollup generation
    # ------------------------------------------------------------------

    def generate_weekly(self, project_name: str, week: str = "") -> Path:
        """Aggregate daily logs into a weekly rollup.

        Args:
            week: ISO week string like '2026-W06'. Defaults to current week.
        """
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
        """Aggregate daily logs into a monthly rollup.

        Args:
            month: Month string like '2026-02'. Defaults to current month.
        """
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
    def _parse_status_file(path: Path) -> SessionExtract:
        """Parse a STATUS.md back into a minimal SessionExtract for the dashboard.

        This is intentionally loose — we just need status, phase, next_steps.
        """
        content = path.read_text()

        def _section(header: str) -> list[str]:
            pattern = rf"## {header}\n(.*?)(?=\n## |\Z)"
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                return []
            text = m.group(1).strip()
            if text in ("_None_", "_Unknown_", "_Not specified_"):
                return []
            return [line.lstrip("- ").strip() for line in text.splitlines() if line.strip().startswith("-")]

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
            next_steps=_section("Next Steps"),
            decisions=_section("Decisions"),
            blockers=_section("Blockers"),
            github_refs=_section("GitHub References"),
        )

    @staticmethod
    def _get_file_date(path: Path) -> str:
        """Get the last-modified date of a file as YYYY-MM-DD."""
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

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
            for line in content.splitlines():
                if line.startswith("**GitHub Refs**:"):
                    refs_text = line.split(":", 1)[1].strip()
                    if refs_text and refs_text != "_None_":
                        github_refs.extend(
                            r.strip() for r in refs_text.split(",") if r.strip()
                        )

        # Deduplicate while preserving order
        completed = _dedup(completed)
        decisions = _dedup(decisions)
        blockers = _dedup(blockers)
        github_refs = _dedup(github_refs)

        return completed, decisions, blockers, github_refs


def _extract_section_bullets(content: str, header: str) -> list[str]:
    """Extract bullet items from a **Header**: section in daily logs."""
    items = []
    pattern = rf"\*\*{header}\*\*:\n(.*?)(?=\n\*\*|\n---|\n###|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        for line in match.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- ") and line != "- _None_":
                items.append(line[2:].strip())
    return items


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate list while preserving order."""
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
