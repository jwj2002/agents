"""Query agent metrics from metrics.jsonl."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .vault_common import get_project_memory_dir


def agent_metrics(period: str | None = None, project: str | None = None) -> dict:
    """Query agent performance metrics.

    Args:
        period: Time period - "7d", "30d", "90d", or "all" (default: "30d")
        project: Optional project path. Uses current project if None.

    Returns:
        Dict with success rates, breakdowns by complexity/stack, trends.
    """
    period = period or "30d"
    memory_dir = get_project_memory_dir(project)
    metrics_file = memory_dir / "metrics.jsonl"

    if not metrics_file.exists():
        return {"error": "No metrics data found", "path": str(metrics_file)}

    # Parse period
    cutoff_date = None
    if period != "all":
        days = int(period.rstrip("d"))
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Load records
    records = []
    for line in metrics_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if cutoff_date and record.get("date", "") < cutoff_date:
                continue
            records.append(record)
        except json.JSONDecodeError:
            continue

    if not records:
        return {"error": "No metrics records in period", "period": period}

    # Calculate overall
    total = len(records)
    passed = sum(1 for r in records if r.get("status") == "PASS")
    blocked = total - passed

    # By complexity
    by_complexity = defaultdict(lambda: {"pass": 0, "total": 0})
    for r in records:
        c = r.get("complexity", "UNKNOWN")
        by_complexity[c]["total"] += 1
        if r.get("status") == "PASS":
            by_complexity[c]["pass"] += 1

    # By stack
    by_stack = defaultdict(lambda: {"pass": 0, "total": 0})
    for r in records:
        s = r.get("stack", "unknown")
        by_stack[s]["total"] += 1
        if r.get("status") == "PASS":
            by_stack[s]["pass"] += 1

    # Top failure causes
    cause_counts = defaultdict(int)
    for r in records:
        if r.get("root_cause"):
            cause_counts[r["root_cause"]] += 1

    top_failures = sorted(cause_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "period": period,
        "total_records": total,
        "overall": {
            "total": total,
            "passed": passed,
            "blocked": blocked,
            "success_rate": round(passed / total, 3) if total else 0,
        },
        "by_complexity": {
            k: {**v, "rate": round(v["pass"] / v["total"], 3) if v["total"] else 0}
            for k, v in sorted(by_complexity.items())
        },
        "by_stack": {
            k: {**v, "rate": round(v["pass"] / v["total"], 3) if v["total"] else 0}
            for k, v in sorted(by_stack.items())
        },
        "top_failures": [{"cause": c, "count": n} for c, n in top_failures],
    }
