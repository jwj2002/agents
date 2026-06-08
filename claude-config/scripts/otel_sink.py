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
    # Opus 4.5–4.8 published API rate: $5 in / $25 out; 5-min cache write 1.25x = $6.25; cache read 0.1x
    # = $0.50. Was $15/$75 (the Opus 4.0/4.1 rate) — that overstated 4.6/4.7/4.8 by 3x (~$34k on the real
    # dataset; Codex review #337). _matches_family matches every "claude-opus-*" via the "opus" alpha-
    # substring, so per-version rows can't be distinguished here. Legacy Opus 4.0/4.1 ($15/$75) are
    # deprecated and absent in real data; if they recur they'd be under-priced — acceptable vs the 3x
    # over-price this removes.
    "claude-opus-4": {
        "input": 5e-6,
        "output": 25e-6,
        "cache_creation": 6.25e-6,
        "cache_read": 0.50e-6,
    },
    "claude-sonnet-4": {  # Sonnet 4.5/4.6: $3 in / $15 out / $3.75 cache write / $0.30 cache read
        "input": 3e-6,
        "output": 15e-6,
        "cache_creation": 3.75e-6,
        "cache_read": 0.30e-6,
    },
    "claude-haiku-4": {  # Haiku 4.5 published API rate: $1 / $5 / $1.25 / $0.10 (Codex review #337)
        "input": 1e-6,
        "output": 5e-6,
        "cache_creation": 1.25e-6,
        "cache_read": 0.10e-6,
    },
    # OpenAI / Codex. OpenAI bills cached input at a discount and charges no separate cache-WRITE,
    # so cache_creation = 0 for all GPT rows. Rates per OpenAI API pricing + the Codex rate card
    # (1 credit = $0.04, anchored on gpt-5.5 = 125cr = $5/MTok); confirmed in Codex review #337.
    #
    # INSERTION ORDER IS LOAD-BEARING: more-specific prefixes MUST precede any prefix they could
    # shadow (e.g. gpt-5.4-mini before gpt-5.4; gpt-5.2-codex before gpt-5-codex).
    "gpt-5.2-codex": {  # rate card: $1.75 in / $14 out / $0.175 cached (#337)
        "input": 1.75e-6,
        "output": 14e-6,
        "cache_creation": 0.0,
        "cache_read": 0.175e-6,
    },
    "gpt-5.3-codex": {  # rate card: $1.75 in / $14 out / $0.175 cached (#337)
        "input": 1.75e-6,
        "output": 14e-6,
        "cache_creation": 0.0,
        "cache_read": 0.175e-6,
    },
    "gpt-5-codex": {  # literal gpt-5-codex (prefix-match only); aligned to the codex rate card (#337)
        "input": 1.75e-6,
        "output": 14e-6,
        "cache_creation": 0.0,
        "cache_read": 0.175e-6,
    },
    "gpt-5.4-mini": {  # rate card: $0.75 in / $4.52 out / $0.075 cached (#337)
        "input": 0.75e-6,
        "output": 4.52e-6,
        "cache_creation": 0.0,
        "cache_read": 0.075e-6,
    },
    "gpt-5.2-mini": {  # mini tier — no rate-card entry; representative, VERIFY
        "input": 0.10e-6,
        "output": 0.40e-6,
        "cache_creation": 0.0,
        "cache_read": 0.025e-6,
    },
    "gpt-5-mini": {  # literal gpt-5-mini (prefix-match only) — representative, VERIFY
        "input": 0.10e-6,
        "output": 0.40e-6,
        "cache_creation": 0.0,
        "cache_read": 0.025e-6,
    },
    "gpt-4o-mini": {  # OpenAI: $0.15 in / $0.60 out / $0.075 cached
        "input": 0.15e-6,
        "output": 0.60e-6,
        "cache_creation": 0.0,
        "cache_read": 0.075e-6,
    },
    "gpt-5.4": {  # rate card: $2.50 in / $15 out / $0.25 cached (#337)
        "input": 2.50e-6,
        "output": 15e-6,
        "cache_creation": 0.0,
        "cache_read": 0.25e-6,
    },
    "gpt-5.5": {  # OpenAI API pricing: $5 in / $30 out / $0.50 cached (#337, web-verified)
        "input": 5e-6,
        "output": 30e-6,
        "cache_creation": 0.0,
        "cache_read": 0.50e-6,
    },
    "gpt-4o": {  # OpenAI: $2.50 in / $10 out / $1.25 cached
        "input": 2.50e-6,
        "output": 10e-6,
        "cache_creation": 0.0,
        "cache_read": 1.25e-6,
    },
}
DEFAULT_PRICE = PRICES[
    "claude-sonnet-4"
]  # conservative fallback for unrecognized models (compute_cost only)

# Stamped onto every usage record (cost-telemetry-v0 §D3) so cost_usd is auditable / re-priceable.
# BUMP this whenever a PRICES rate changes — test_price_table_version pins the current value so any
# silent rate edit fails CI until the version is bumped.
PRICE_TABLE_VERSION = "2026-06-08b"

EXPORTER_FRESHNESS_SLA_DEFAULT = (
    24 * 3600
)  # 24h: sink must be written within SLA or alarm (§0.1)


def _matches_family(m: str, family: str) -> bool:
    """True if lowercase model string `m` belongs to `family`.

    Claude families use alphabetic-token substring (opus/sonnet/haiku are alpha → substring fires).
    GPT families use startswith-only: the numeric guard (token.isalpha()) prevents cross-family
    matches via numeric tokens — e.g. "5.2" must NOT match gpt-5.2-mini against gpt-5.2-codex.
    """
    parts = family.split("-")
    # hyphenless family key → no alpha-substring branch (avoids IndexError)
    token = parts[1] if len(parts) > 1 else ""
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
