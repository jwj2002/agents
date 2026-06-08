"""D3 normalized usage record (cost-telemetry-v0 §D3).

The single source of truth for the `usage.jsonl` row shape, so no downstream code (report,
recommender) has to guess whether `None`/`""`/`"unattributed"` mean the same thing. The collector
(`usage_collect.py`, §D1) calls `normalize()` on every record before append; the report layer renders
`project`/`task == None` as "unattributed" (the data stays honest, the rendering is cosmetic).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import otel_sink as O  # noqa: E402  (PRICE_TABLE_VERSION + PRICES)

PRICE_BASIS = "published_api_rate"

# The 20 canonical fields, in order (cost-telemetry-v0 §D3).
NORMALIZED_FIELDS = (
    "provider",
    "account",
    "billing_type",
    "price_basis",
    "price_table_version",
    "inference_host",
    "work_host",
    "project",
    "task",
    "model",
    "files_changed",
    "files_changed_source",
    "input",
    "output",
    "cache_read",
    "cache_creation",
    "cost_usd",
    "session_id",
    "ts",
    "dedup_key",
)

_BILLING = frozenset({"metered", "subscription", "unknown"})
_FCS = frozenset({"pr_git", "project_metrics", "session_shard", "none"})
_TOKEN_FIELDS = ("input", "output", "cache_read", "cache_creation")


def canonical_account(fields: dict) -> str:
    """Canonical account id (cost-telemetry-v0 §D3): Claude account_uuid → Codex account_id →
    email → 'unknown'. Email is a last resort and is kept OUT of the default report by callers."""
    if not isinstance(fields, dict):
        return "unknown"
    for k in ("account_uuid", "account_id", "email"):
        v = fields.get(k)
        if v:
            return str(v)
    return "unknown"


def normalize(rec: dict) -> dict:
    """Coerce a raw collector record to the D3 schema. Never invents cost: `cost_usd` stays None
    for quarantined (unknown-model) rows. Stamps pricing provenance. All 20 fields present."""
    out = dict(rec) if isinstance(rec, dict) else {}
    bt = out.get("billing_type")
    out["billing_type"] = bt if bt in _BILLING else "unknown"
    out["price_basis"] = PRICE_BASIS
    out["price_table_version"] = O.PRICE_TABLE_VERSION
    # Data layer uses None for "no attribution" — the collector's "unattributed" sentinel was being
    # counted as attributed by the report's `task is not None` coverage check (Codex review #337
    # finding 5: 100% vs the true ~88%). Normalize it to None; the report renders None as "unattributed".
    if out.get("task") == "unattributed":
        out["task"] = None
    out["files_changed"] = out.get("files_changed")  # null when absent (never 0/"")
    fcs = out.get("files_changed_source")
    out["files_changed_source"] = fcs if fcs in _FCS else "none"
    for t in _TOKEN_FIELDS:
        out[t] = int(out.get(t, 0) or 0)
    cost = out.get("cost_usd")
    out["cost_usd"] = float(cost) if cost is not None else None
    for f in NORMALIZED_FIELDS:
        out.setdefault(f, None)
    return out
