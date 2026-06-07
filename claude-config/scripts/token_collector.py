"""Cache-aware token COST collector (telemetry-validation §1.1-§1.5, build item 2).

Reads the OTEL sink (#230, `otel_sink`) and produces price-weighted USD cost per session, then per
task where sessions share an attribution link. Raw token counts are diagnostics; cost is the valid
efficiency sensor (§1.2). Cost-per-outcome / waste-share stay TARGET-GATED (§0.5) — emitted here
only as `diagnostic_only`.

server-a's lane; built host-agnostic by scratch against simulated sink data (live data lands once
the #252 collector deploy runs on jns-server). Pure logic, no side effects.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import otel_sink as O  # noqa: E402

# Work types with no valid code-quality measurement — cost-tracked but EXCLUDED from targets (§2.5).
EXCLUDED_WORK_TYPES = frozenset({"deliberative", "ops"})
RECONCILE_TOLERANCE_DEFAULT = 0.01  # 1% — per-task sum must reconcile vs global OTEL (§2.5 watchdog)


def is_known_model(model: str) -> bool:
    """True if the model maps to a real price row. Uses O._matches_family — the single
    source of truth for family matching — so this never drifts from _price_for."""
    if not model:
        return False
    m = str(model).lower()
    return any(O._matches_family(m, fam) for fam in O.PRICES)


def session_cost(record: dict, *, strict: bool = True) -> float:
    """USD cost of one usage record. STRICT (default): an unknown model is an ERROR with the model
    name — never a silent zero-cost (that would hide spend, the #231 edge case). otel_sink.compute_cost
    alone would fall back to a default price; the collector refuses to guess silently."""
    model = record.get("model", "")
    if strict and not is_known_model(model):
        raise ValueError(
            f"unknown model {model!r} not in price table — refusing silent zero/guessed cost; "
            f"add it to otel_sink.PRICES"
        )
    return O.compute_cost(record)


def _task_link(meta: dict) -> str | None:
    """A task link ties sessions into one logical task: prefer issue, then branch, then task_id.
    None => unattributed (the session IS the unit, but its cost can't roll into a task)."""
    for k in ("issue", "branch", "task_id"):
        v = meta.get(k)
        if v:
            return f"{k}:{v}"
    return None


def collect_sessions(sink_records: list, session_meta: dict | None = None, *, strict: bool = True) -> list:
    """Per-session cost records (the primary unit, §1.3). `session_meta` joins capture metadata
    (work_type / issue / branch from #229) onto the OTEL token records by session_id."""
    session_meta = session_meta or {}
    out = []
    for r in sink_records:
        sid = r.get("session_id")
        meta = session_meta.get(sid, {})
        work_type = meta.get("work_type") or r.get("work_type")
        out.append({
            "session_id": sid,
            "model": r.get("model"),
            "work_type": work_type,
            "tokens": {f: int(r.get(f, 0) or 0) for f in O.TOKEN_FIELDS},
            "cost_usd": session_cost(r, strict=strict),
            "task_link": _task_link({**meta, **r}),
            "excluded": work_type in EXCLUDED_WORK_TYPES,
        })
    return out


def aggregate(session_costs: list) -> dict:
    """Roll per-session costs into per-task records + the separate excluded/unattributed buckets
    (§0.5 attribution-coverage inputs). Excluded sessions never enter task rollups or targets."""
    tasks: dict = {}
    excluded = 0.0
    unattributed = 0.0
    attributed = 0.0
    for s in session_costs:
        cost = s["cost_usd"]
        if s.get("excluded"):
            excluded += cost
            continue
        link = s.get("task_link")
        if link is None:
            unattributed += cost
            continue
        attributed += cost
        t = tasks.setdefault(link, {"task_link": link, "cost_usd": 0.0, "sessions": []})
        t["cost_usd"] = round(t["cost_usd"] + cost, 10)
        t["sessions"].append(s["session_id"])
    total = attributed + unattributed + excluded
    coverage = (attributed / total) if total > 0 else 0.0
    return {
        "tasks": list(tasks.values()),
        "attributed_cost_usd": round(attributed, 10),
        "unattributed_cost_usd": round(unattributed, 10),
        "excluded_cost_usd": round(excluded, 10),
        "attribution_coverage": round(coverage, 4),  # feeds the §0.5 target-promotion gate
    }


def reconcile(attributed_total: float, otel_global_total: float, tolerance: float = RECONCILE_TOLERANCE_DEFAULT) -> dict:
    """Token-coverage reconciliation (§2.5 watchdog): per-task attributed cost must track the global
    OTEL total within tolerance, else attribution gaps are hiding spend → alarm."""
    if otel_global_total <= 0:
        return {"alarm": attributed_total > 0, "reason": "no_global_total", "deviation": None}
    deviation = abs(attributed_total - otel_global_total) / otel_global_total
    return {
        "alarm": deviation > tolerance,
        "deviation": round(deviation, 6),
        "reason": "reconciliation_drift" if deviation > tolerance else "ok",
    }


def build_report(sink_records: list, session_meta: dict | None = None, *,
                 otel_global_total: float | None = None, strict: bool = True) -> dict:
    """The collector's emitted record. Per-session cost + per-task rollup are diagnostics. Cost-per-
    outcome / waste-share are TARGET-GATED (§0.5) so they are explicitly labeled diagnostic_only."""
    sessions = collect_sessions(sink_records, session_meta, strict=strict)
    agg = aggregate(sessions)
    report = {
        "schema_version": 1,
        "sessions": sessions,            # diagnostic: raw per-session cost
        **agg,
        "diagnostic_only": {
            # not targets until the §0.5 gate clears (source+coverage+proxy-validated+companions)
            "waste_token_share": None,
            "cost_per_no_observed_defect": None,
            "_note": "TARGET-GATED (§0.5) — diagnostics only until the promotion gate clears",
        },
    }
    if otel_global_total is not None:
        report["reconciliation"] = reconcile(agg["attributed_cost_usd"], otel_global_total)
    return report
