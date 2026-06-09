#!/usr/bin/env python3
"""Quality KPI module — first-pass-correct rate and gates-caught count.

Pure function module: file paths in, dict/markdown out. No side effects
except reading files passed as Path arguments. All reads are fail-open
(missing or malformed file → empty list for that source; no exception raised).

Public API:
    compute_kpis(metrics_path, prove_log_path, overrides_paths, *, weeks, now)
        → {"rows": [...], "totals": {...}}
    format_kpi_section(kpis) → str (markdown table, or "" when no data)

CLI:
    python3 quality_kpis.py --report [--weeks N]
        --metrics PATH --prove-log PATH --overrides PATH [PATH ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read and parse a JSONL file. Returns [] on any error (fail-open)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, KeyError):
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def _week_of(date_str: str) -> str | None:
    """Return 'YYYY-Www' from a date string ('YYYY-MM-DD') or ISO timestamp.

    Returns None if the string cannot be parsed.
    """
    if not date_str:
        return None
    try:
        # Try plain date first: YYYY-MM-DD
        d = date.fromisoformat(date_str[:10])
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except (ValueError, AttributeError):
        return None


def _build_weeks(now: datetime, n: int) -> list[str]:
    """Return n ISO week keys (oldest first), ending with the week containing *now*."""
    result: list[str] = []
    for i in range(n - 1, -1, -1):
        d = (now - timedelta(weeks=i)).date()
        iso = d.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        if key not in result:  # guard against duplicates at DST boundaries
            result.append(key)
    # Ensure exactly n entries; if we somehow got fewer, pad from the left
    while len(result) < n:
        result.insert(0, "n/a")
    return result[-n:]


def _fpc_rows(records: list[dict[str, Any]], week_keys: list[str]) -> dict[str, dict]:
    """Bucket metrics records by week, computing first-pass-correct data.

    Only records with a 'first_pass_correct' boolean field count toward
    the denominator; records without the field are excluded (they predate
    the schema).
    """
    buckets: dict[str, dict] = {k: {"fpc_true": 0, "fpc_false": 0} for k in week_keys}
    for rec in records:
        fpc = rec.get("first_pass_correct")
        if fpc is None:
            continue  # predates the field; excluded from rate
        date_str = rec.get("date", "")
        wk = _week_of(str(date_str)) if date_str else None
        if wk not in buckets:
            continue
        if fpc is True:
            buckets[wk]["fpc_true"] += 1
        elif fpc is False:
            buckets[wk]["fpc_false"] += 1
    return buckets


def _gate_rows(
    prove_log: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
    week_keys: list[str],
) -> dict[str, int]:
    """Bucket gate-caught events by week.

    A gate-caught event is:
    - A prove-log record with verdict == "FAIL" or "BLOCKED", OR
    - A prove-log record where any eval_results value is "fail", OR
    - An override record where gate_exit != 0.
    """
    buckets: dict[str, int] = {k: 0 for k in week_keys}

    for rec in prove_log:
        verdict = rec.get("verdict", "")
        eval_results = rec.get("eval_results") or {}
        ts = rec.get("ts", "")
        caught = verdict in ("FAIL", "BLOCKED") or any(
            v == "fail" for v in eval_results.values()
        )
        if not caught:
            continue
        wk = _week_of(str(ts)[:10]) if ts else None
        if wk in buckets:
            buckets[wk] += 1

    for rec in overrides:
        gate_exit = rec.get("gate_exit", 0)
        if gate_exit == 0:
            continue  # gate was not actually blocking
        ts = rec.get("ts", "")
        wk = _week_of(str(ts)[:10]) if ts else None
        if wk in buckets:
            buckets[wk] += 1

    return buckets


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_kpis(
    metrics_path: Path,
    prove_log_path: Path,
    overrides_paths: list[Path],
    *,
    weeks: int = 8,
    now: datetime | None = None,
) -> dict:
    """Compute quality KPIs from data files.

    Returns a dict:
        {
            "rows": [
                {
                    "week": "2026-W23",
                    "fpc_rate": 0.85,   # float or None when no qualifying records
                    "fpc_n": 12,        # denominator (records with fpc field)
                    "gates_caught": 3,
                },
                ...  # oldest week first, 'weeks' entries
            ],
            "totals": {
                "fpc_rate": float | None,
                "fpc_n": int,
                "gates_caught": int,
            }
        }

    Degrades gracefully: missing or malformed files → empty data for that source.
    Never raises.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    week_keys = _build_weeks(now, weeks)

    metrics_records = _load_jsonl(metrics_path)
    prove_records = _load_jsonl(prove_log_path)
    override_records: list[dict] = []
    for op in overrides_paths:
        override_records.extend(_load_jsonl(op))

    fpc_buckets = _fpc_rows(metrics_records, week_keys)
    gate_buckets = _gate_rows(prove_records, override_records, week_keys)

    rows = []
    total_fpc_true = 0
    total_fpc_false = 0
    total_gates = 0

    for wk in week_keys:
        fpc_data = fpc_buckets.get(wk, {"fpc_true": 0, "fpc_false": 0})
        fpc_true = fpc_data["fpc_true"]
        fpc_false = fpc_data["fpc_false"]
        fpc_n = fpc_true + fpc_false
        fpc_rate = fpc_true / fpc_n if fpc_n > 0 else None

        gates = gate_buckets.get(wk, 0)

        total_fpc_true += fpc_true
        total_fpc_false += fpc_false
        total_gates += gates

        rows.append(
            {
                "week": wk,
                "fpc_rate": fpc_rate,
                "fpc_n": fpc_n,
                "gates_caught": gates,
            }
        )

    total_fpc_n = total_fpc_true + total_fpc_false
    totals = {
        "fpc_rate": total_fpc_true / total_fpc_n if total_fpc_n > 0 else None,
        "fpc_n": total_fpc_n,
        "gates_caught": total_gates,
    }

    return {"rows": rows, "totals": totals}


def format_kpi_section(kpis: dict) -> str:
    """Render the KPI data as a markdown section.

    Returns a markdown string containing the 8-week quality KPI table.
    Returns empty string only when kpis is empty or has no rows — always
    renders for well-formed (even all-zero) data.
    """
    rows = kpis.get("rows")
    if not rows:
        return ""

    totals = kpis.get("totals", {})

    lines = [
        "## Quality KPIs (8-week trend)",
        "",
        "_Data sparse while first_pass_correct field matures; "
        "n/a = no qualifying records that week._",
        "",
        "| Week | First-pass rate | n | Gates caught |",
        "| ---- | --------------- | - | ------------ |",
    ]

    for row in rows:
        fpc_rate = row.get("fpc_rate")
        fpc_n = row.get("fpc_n", 0)
        gates = row.get("gates_caught", 0)
        week = row.get("week", "?")

        if fpc_rate is None:
            rate_str = "n/a"
        else:
            rate_str = f"{fpc_rate:.0%}"

        lines.append(f"| {week} | {rate_str} | {fpc_n} | {gates} |")

    # Totals row
    total_rate = totals.get("fpc_rate")
    total_n = totals.get("fpc_n", 0)
    total_gates = totals.get("gates_caught", 0)
    total_rate_str = f"{total_rate:.0%}" if total_rate is not None else "n/a"
    lines.append(f"| **Total** | **{total_rate_str}** | **{total_n}** | **{total_gates}** |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_METRICS = Path.home() / ".claude" / "memory" / "metrics.jsonl"
DEFAULT_PROVE_LOG = Path.home() / ".claude" / "memory" / "prove-log.jsonl"
DEFAULT_OVERRIDES = [Path.home() / ".agents" / "outputs" / "prove-overrides.jsonl"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compute and display quality KPIs (first-pass rate + gates-caught)."
    )
    ap.add_argument(
        "--report",
        action="store_true",
        help="Print the rendered markdown table (default when no other flag given)",
    )
    ap.add_argument(
        "--weeks",
        type=int,
        default=8,
        help="Number of ISO weeks to include (default: 8)",
    )
    ap.add_argument(
        "--metrics",
        type=Path,
        default=DEFAULT_METRICS,
        help="Path to metrics.jsonl",
    )
    ap.add_argument(
        "--prove-log",
        type=Path,
        default=DEFAULT_PROVE_LOG,
        help="Path to prove-log.jsonl",
    )
    ap.add_argument(
        "--overrides",
        type=Path,
        nargs="*",
        default=DEFAULT_OVERRIDES,
        help="Path(s) to prove-overrides.jsonl (may specify multiple)",
    )

    args = ap.parse_args(argv)
    overrides = args.overrides or []

    kpis = compute_kpis(
        metrics_path=args.metrics,
        prove_log_path=args.prove_log,
        overrides_paths=overrides,
        weeks=args.weeks,
    )
    section = format_kpi_section(kpis)
    if section:
        print(section)
    else:
        print("(no KPI data)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
