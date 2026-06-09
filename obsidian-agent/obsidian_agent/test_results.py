"""Extract UI test results from project test plans.

Scans project directories for test plan files (ui-test-plan.md) and extracts
pass/fail/skip counts for inclusion in vault daily logs and STATUS.md.
"""
from __future__ import annotations

import re
from pathlib import Path


def find_test_plans(project_path: str) -> list[Path]:
    """Find test plan files in a project directory."""
    root = Path(project_path)
    if not root.exists():
        return []

    candidates = [
        root / "frontend" / "e2e" / "results" / "ui-test-plan.md",
        root / "e2e" / "results" / "ui-test-plan.md",
        root / "tests" / "ui" / "ui-test-plan.md",
    ]
    return [p for p in candidates if p.exists()]


def parse_test_plan(path: Path) -> dict:
    """Parse a ui-test-plan.md file and extract test statistics.

    Returns:
        Dict with total, pass, fail, skip, auto counts,
        per-priority breakdown, issues found, and recent run info.
    """
    content = path.read_text()

    # Extract summary table
    summary = _parse_summary_table(content)

    # Count individual test statuses
    statuses = _count_statuses(content)

    # Extract issues
    issues = _extract_issues(content)

    # Extract run history
    runs = _extract_run_history(content)

    return {
        "plan_file": str(path),
        "summary": summary,
        "statuses": statuses,
        "issues": issues,
        "recent_runs": runs,
    }


def render_test_summary(results: dict) -> str:
    """Render test results as a markdown section for vault daily log."""
    s = results["statuses"]
    total = s.get("total", 0)
    passed = s.get("pass", 0)
    failed = s.get("fail", 0)
    skipped = s.get("skip", 0)
    pending = s.get("pending", 0)
    auto = s.get("auto", 0)

    if total == 0:
        return ""

    # Progress bar
    pct = round(passed / total * 100) if total > 0 else 0
    bar_filled = round(pct / 5)
    bar_empty = 20 - bar_filled
    progress = f"[{'█' * bar_filled}{'░' * bar_empty}] {pct}%"

    lines = [
        "## UI Test Results",
        "",
        f"**Progress**: {progress} ({passed}/{total} passing)",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total | {total} |",
        f"| Pass | {passed} |",
        f"| Fail | {failed} |",
        f"| Skip | {skipped} |",
        f"| Pending | {pending} |",
        f"| Automated | {auto} |",
    ]

    # Per-priority breakdown from summary table
    if results.get("summary"):
        lines.append("")
        lines.append("**By Priority:**")
        for row in results["summary"]:
            p = row.get("priority", "?")
            area = row.get("area", "?")
            t = row.get("total", 0)
            ps = row.get("pass", 0)
            f = row.get("fail", 0)
            if t > 0:
                lines.append(f"- {p} {area}: {ps}/{t} pass{' (' + str(f) + ' fail)' if f > 0 else ''}")

    # Issues found
    if results.get("issues"):
        lines.append("")
        lines.append("**Issues Found:**")
        for issue in results["issues"]:
            lines.append(f"- {issue}")

    return "\n".join(lines)


def render_test_status_line(results: dict) -> str:
    """Render a one-line test status for STATUS.md or dashboard."""
    s = results["statuses"]
    total = s.get("total", 0)
    passed = s.get("pass", 0)
    failed = s.get("fail", 0)

    if total == 0:
        return "No tests"

    pct = round(passed / total * 100)
    status = f"Tests: {passed}/{total} ({pct}%)"
    if failed > 0:
        status += f" — {failed} FAILING"
    return status


def _parse_summary_table(content: str) -> list[dict]:
    """Parse the Test Summary markdown table."""
    rows = []
    in_table = False

    for line in content.splitlines():
        if "| Priority | Area |" in line:
            in_table = True
            continue
        if in_table and line.startswith("|--"):
            continue
        if in_table and line.startswith("|"):
            if "**Total**" in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 7:
                try:
                    rows.append({
                        "priority": parts[0],
                        "area": parts[1],
                        "total": int(parts[2]),
                        "pass": int(parts[3]),
                        "fail": int(parts[4]),
                        "skip": int(parts[5]),
                        "auto": int(parts[6]),
                    })
                except (ValueError, IndexError):
                    pass
        elif in_table and not line.startswith("|"):
            break

    return rows


def _count_statuses(content: str) -> dict:
    """Count test case statuses from individual entries."""
    counts = {"pass": 0, "fail": 0, "skip": 0, "pending": 0, "total": 0, "auto": 0}

    for match in re.finditer(r"\*\*Status\*\*:\s*`(\w+)`", content):
        status = match.group(1).lower()
        if status in counts:
            counts[status] += 1
        counts["total"] += 1

    # Count automated tests
    for match in re.finditer(r"\*\*Automated\*\*:\s*`(yes|no)`", content):
        if match.group(1) == "yes":
            counts["auto"] += 1

    return counts


def _extract_issues(content: str) -> list[str]:
    """Extract issue references from test cases."""
    issues = []
    for match in re.finditer(r"\*\*Issues\*\*:\s*(.+)", content):
        text = match.group(1).strip()
        if text and text != "—":
            issues.append(text)
    return issues


def _extract_run_history(content: str) -> list[dict]:
    """Extract run history entries."""
    runs = []
    in_history = False

    for line in content.splitlines():
        if "## Run History" in line:
            in_history = True
            continue
        if in_history and line.startswith("|--"):
            continue
        if in_history and line.startswith("| ") and not line.startswith("| Date"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 5 and parts[0]:
                runs.append({
                    "date": parts[0],
                    "runner": parts[1],
                    "tests_run": parts[2],
                    "pass": parts[3],
                    "fail": parts[4],
                })
        elif in_history and not line.startswith("|") and line.strip():
            break

    return runs
