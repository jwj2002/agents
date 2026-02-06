"""Read failures.jsonl and extract top patterns."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .vault_common import get_project_memory_dir


def failure_patterns(project: str | None = None) -> dict:
    """Read failures.jsonl and return top failure patterns.

    Args:
        project: Optional project path. Uses current project if None.

    Returns:
        Dict with patterns grouped by root_cause, with frequency and examples.
    """
    memory_dir = get_project_memory_dir(project)
    failures_file = memory_dir / "failures.jsonl"

    if not failures_file.exists():
        return {"error": "No failures data found", "path": str(failures_file)}

    # Load records
    records = []
    for line in failures_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        return {"error": "No failure records found", "total": 0}

    # Group by root cause
    by_cause = defaultdict(list)
    for r in records:
        cause = r.get("root_cause", "UNKNOWN")
        by_cause[cause].append(r)

    # Build patterns
    patterns = []
    for cause, failures in sorted(by_cause.items(), key=lambda x: -len(x[1])):
        # Get common files
        file_counts = defaultdict(int)
        for f in failures:
            for filepath in f.get("files", []):
                file_counts[filepath] += 1
        top_files = sorted(file_counts.items(), key=lambda x: -x[1])[:5]

        # Get most recent examples
        recent = sorted(failures, key=lambda x: x.get("date", ""), reverse=True)[:3]

        patterns.append({
            "root_cause": cause,
            "count": len(failures),
            "percentage": round(len(failures) / len(records) * 100, 1),
            "common_files": [{"file": f, "count": c} for f, c in top_files],
            "recent_examples": [
                {
                    "issue": ex.get("issue"),
                    "date": ex.get("date"),
                    "details": ex.get("details", "")[:200],
                    "prevention": ex.get("prevention", ""),
                }
                for ex in recent
            ],
        })

    return {
        "total_failures": len(records),
        "unique_causes": len(patterns),
        "patterns": patterns,
    }
