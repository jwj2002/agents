"""OTEL → readable token-usage sink: reader, cache-aware cost, freshness check (§1.1, §1.2).

The "sleeper" prerequisite (telemetry-validation §5 build item 1.5): Claude Code PUSHES
`claude_code.token.usage` via OTEL — it is not sitting in a file. A collector/file-exporter lands
it in a readable JSONL sink; THIS module reads that sink, computes cache-aware COST (not raw
tokens — §1.2), and provides the exporter-freshness alarm that feeds the watchdog (§0.1).

Scope note: the live collector wiring (Claude Code OTLP -> file exporter) is a per-host DEPLOY
documented in OTEL_SINK_SETUP.md and deferred to jns-server. This module + its tests run against
simulated pushes (the AC's "simulated OTEL push") and are host-agnostic.
"""

from __future__ import annotations

import json
from pathlib import Path

TOKEN_FIELDS = ("input", "output", "cache_creation", "cache_read")

# Per-token USD prices, MULTI-PROVIDER (fleet-usage-monitor §6). Ratios are the load-bearing part
# (§1.2): cache_read ≈ 0.10x fresh input, output dearest, cache_creation ~1.25x input. Absolute
# numbers track each vendor's published per-MTok rates (/1e6) and are config — refine as pricing
# changes. `_price_for` matches by family prefix, so adding a row is the whole extension mechanism.
#
# Claude rates cross-check (fleet-usage-monitor §2.1, verified 2026-06-06): the real measured session
# mix {input 657_029, output 4_070_961, cache_read 924_428_695, cache_creation 24_381_544} at
# claude-opus-4 rates = $2,158.97 ≈ the $2,159 reference. (NOTE: the reference is the full token MIX,
# not 954M pure input — 954M is the token TOTAL across all types.) test_multiprovider_pricing enforces
# this within 5%.
PRICES = {
    "claude-opus-4": {
        "input": 15e-6,
        "output": 75e-6,
        "cache_creation": 18.75e-6,
        "cache_read": 1.5e-6,
    },
    "claude-sonnet-4": {
        "input": 3e-6,
        "output": 15e-6,
        "cache_creation": 3.75e-6,
        "cache_read": 0.30e-6,
    },
    "claude-haiku-4": {
        "input": 0.80e-6,
        "output": 4e-6,
        "cache_creation": 1.0e-6,
        "cache_read": 0.08e-6,
    },
    # OpenAI / Codex. OpenAI bills cached input at a discount and charges no separate cache-WRITE,
    # so cache_creation = 0 for all GPT rows. Rates are representative (per-MTok / 1e6) —
    # VERIFY against OpenAI published pricing before treating these as authoritative for billing.
    #
    # INSERTION ORDER IS LOAD-BEARING: more-specific prefixes MUST precede any prefix they could
    # shadow (e.g. gpt-5.4-mini before gpt-5.4; gpt-5.2-codex before gpt-5-codex).
    "gpt-5.2-codex": {  # real data: 2694 events in ~/.codex/sessions — VERIFY rates
        "input": 0.75e-6,
        "output": 6e-6,
        "cache_creation": 0.0,
        "cache_read": 0.075e-6,
    },
    "gpt-5.3-codex": {  # real data: 704 events — VERIFY rates
        "input": 1.0e-6,
        "output": 8e-6,
        "cache_creation": 0.0,
        "cache_read": 0.10e-6,
    },
    "gpt-5-codex": {  # catch-all: gpt-5-codex and older gpt-5.N-codex variants — VERIFY rates
        "input": 0.75e-6,
        "output": 6e-6,
        "cache_creation": 0.0,
        "cache_read": 0.075e-6,
    },
    "gpt-5.4-mini": {  # mini tier, cheaper than flagship — VERIFY rates
        "input": 0.10e-6,
        "output": 0.40e-6,
        "cache_creation": 0.0,
        "cache_read": 0.025e-6,
    },
    "gpt-5.2-mini": {  # mini tier — VERIFY rates
        "input": 0.10e-6,
        "output": 0.40e-6,
        "cache_creation": 0.0,
        "cache_read": 0.025e-6,
    },
    "gpt-5-mini": {  # catch-all: gpt-5-mini and gpt-5.N-mini variants — VERIFY rates
        "input": 0.10e-6,
        "output": 0.40e-6,
        "cache_creation": 0.0,
        "cache_read": 0.025e-6,
    },
    "gpt-4o-mini": {  # VERIFY rates
        "input": 0.15e-6,
        "output": 0.60e-6,
        "cache_creation": 0.0,
        "cache_read": 0.075e-6,
    },
    "gpt-5.4": {  # real data: 354 events, flagship tier — VERIFY rates
        "input": 1.25e-6,
        "output": 10e-6,
        "cache_creation": 0.0,
        "cache_read": 0.125e-6,
    },
    "gpt-5.5": {  # verified in use (Codex CLI, §2.2) — VERIFY rates
        "input": 1.25e-6,
        "output": 10e-6,
        "cache_creation": 0.0,
        "cache_read": 0.125e-6,
    },
    "gpt-4o": {  # VERIFY rates
        "input": 2.50e-6,
        "output": 10e-6,
        "cache_creation": 0.0,
        "cache_read": 1.25e-6,
    },
}
DEFAULT_PRICE = PRICES[
    "claude-sonnet-4"
]  # conservative fallback for unrecognized models (compute_cost only)

EXPORTER_FRESHNESS_SLA_DEFAULT = (
    24 * 3600
)  # 24h: sink must be written within SLA or alarm (§0.1)


def _matches_family(m: str, family: str) -> bool:
    """True if lowercase model string `m` belongs to `family`.

    Claude families use alphabetic-token substring (opus/sonnet/haiku are alpha → substring fires).
    GPT families use startswith-only: the numeric guard (token.isalpha()) prevents cross-family
    matches via numeric tokens — e.g. "5.2" must NOT match gpt-5.2-mini against gpt-5.2-codex.
    """
    token = family.split("-")[1]
    return m.startswith(family) or (token.isalpha() and token in m)


def _price_for(model: str) -> dict:
    """Pick a price row by model-family prefix; fall back to DEFAULT_PRICE for unknown models."""
    if not model:
        return DEFAULT_PRICE
    m = str(model).lower()
    for family, row in PRICES.items():
        if _matches_family(m, family):
            return row
    return DEFAULT_PRICE


def compute_cost(record: dict, prices: dict | None = None) -> float:
    """Cache-aware USD cost of a usage record `{input, output, cache_creation, cache_read, model}`.
    Raw token COUNT is not a valid cost measure (§1.2) — this price-weights each token type."""
    row = (prices or {}).get(record.get("model")) if prices else None
    row = row or _price_for(record.get("model", ""))
    return round(sum(int(record.get(f, 0) or 0) * row[f] for f in TOKEN_FIELDS), 10)


def normalize_from_datapoints(datapoints: list) -> dict:
    """Aggregate raw OTEL `claude_code.token.usage` datapoints into a normalized usage record.

    Each datapoint looks like `{"value": N, "attributes": {"type": "input"|"output"|
    "cache_creation"|"cache_read"|"cacheRead"..., "model": "..."}}`. Type names are normalized
    (camelCase/aliases accepted). This is the OTLP -> readable mapping the file-exporter performs;
    kept here so the mapping is tested even before the live collector lands.
    """
    out = {f: 0 for f in TOKEN_FIELDS}
    model = ""
    alias = {
        "input": "input",
        "output": "output",
        "cache_creation": "cache_creation",
        "cachecreation": "cache_creation",
        "cache_creation_input_tokens": "cache_creation",
        "ephemeral_5m_input_tokens": "cache_creation",
        "cache_read": "cache_read",
        "cacheread": "cache_read",
        "cache_read_input_tokens": "cache_read",
    }
    for dp in datapoints or []:
        attrs = dp.get("attributes", {}) or {}
        ttype = str(attrs.get("type", "")).replace("-", "_").lower()
        field = alias.get(ttype)
        if field:
            out[field] += int(dp.get("value", 0) or 0)
        if attrs.get("model"):
            model = attrs["model"]
    out["model"] = model
    return out


def append_sink_record(path, record: dict) -> None:
    """Append-safe write of one normalized record as a JSONL line (back-to-back sessions safe)."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(line)


def read_sink(path) -> list:
    """Read all normalized usage records from the sink JSONL.

    A MISSING sink path is an actionable error, never a silent empty read (§0.3 / AC edge case):
    raises FileNotFoundError with a message pointing at OTEL_SINK_SETUP.md. Malformed lines are
    skipped (the exporter may write partial lines under crash), not fatal.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(
            f"OTEL sink not found at {p}. The exporter is not running or misconfigured — "
            f"see claude-config/telemetry/OTEL_SINK_SETUP.md to set up the OTLP file exporter."
        )
    records = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a partial/corrupt line; never abort the whole read
    return records


def sink_last_write_ts(path):
    """mtime of the sink (epoch seconds), or None if missing."""
    p = Path(path).expanduser()
    return p.stat().st_mtime if p.exists() else None


def is_stale(
    last_write_ts, now_ts: float, sla_seconds: float = EXPORTER_FRESHNESS_SLA_DEFAULT
) -> bool:
    """Pure freshness predicate: stale if never written or last write older than the SLA."""
    if last_write_ts is None:
        return True
    return (now_ts - last_write_ts) > sla_seconds


def check_exporter_freshness(
    path, now_ts: float, sla_seconds: float = EXPORTER_FRESHNESS_SLA_DEFAULT
) -> dict:
    """Exporter-freshness alarm (§0.1 stale-exporter state). Returns
    `{"alarm": bool, "reason": str, "age_seconds": float|None}` — feeds the #231/#232 watchdog."""
    last = sink_last_write_ts(path)
    if last is None:
        return {"alarm": True, "reason": "sink_missing", "age_seconds": None}
    age = now_ts - last
    if age > sla_seconds:
        return {"alarm": True, "reason": "stale_exporter", "age_seconds": round(age, 3)}
    return {"alarm": False, "reason": "fresh", "age_seconds": round(age, 3)}
