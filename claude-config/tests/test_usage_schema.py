"""Acceptance tests for issue #319 — D3 PRICE_TABLE_VERSION + normalized schema (cost-telemetry-v0 §D3)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import otel_sink as O  # noqa: E402
import usage_schema as S  # noqa: E402


def test_price_table_version_exists_and_pinned():
    assert isinstance(O.PRICE_TABLE_VERSION, str) and O.PRICE_TABLE_VERSION
    # PIN: a silent PRICES rate edit must bump this. If you changed rates, bump the version + this test.
    assert O.PRICE_TABLE_VERSION == "2026-06-08b"


def test_normalize_fills_all_fields_and_stamps_pricing():
    rec = {
        "provider": "claude",
        "model": "claude-opus-4",
        "input": 100,
        "output": 50,
        "cost_usd": 1.5,
        "session_id": "s",
        "ts": "t",
        "dedup_key": "s:1",
        "billing_type": "metered",
    }
    out = S.normalize(rec)
    for f in S.NORMALIZED_FIELDS:
        assert f in out, f
    assert out["price_basis"] == "published_api_rate"
    assert out["price_table_version"] == O.PRICE_TABLE_VERSION
    assert out["billing_type"] == "metered"
    assert out["cost_usd"] == 1.5


def test_billing_type_none_or_bad_becomes_unknown():
    assert S.normalize({"billing_type": None})["billing_type"] == "unknown"
    assert S.normalize({"billing_type": "console"})["billing_type"] == "unknown"


def test_unattributed_task_normalized_to_none():
    # #337 finding 5: the collector's "unattributed" sentinel must become None at the data layer so the
    # report's `task is not None` coverage check counts it as missing (it was inflating coverage to 100%).
    assert S.normalize({"task": "unattributed"})["task"] is None
    assert S.normalize({"task": "issue:42"})["task"] == "issue:42"  # real task untouched
    assert S.normalize({})["billing_type"] == "unknown"


def test_files_changed_defaults_null_and_source_none():
    out = S.normalize({})
    assert out["files_changed"] is None  # null, never 0/""
    assert out["files_changed_source"] == "none"
    assert (
        S.normalize({"files_changed_source": "bogus"})["files_changed_source"] == "none"
    )
    assert (
        S.normalize({"files_changed_source": "pr_git"})["files_changed_source"]
        == "pr_git"
    )


def test_quarantine_cost_stays_null():
    # an unknown-model (quarantined) row carries no cost — normalize must not invent one
    out = S.normalize({"model": "gpt-99-unknown", "cost_usd": None})
    assert out["cost_usd"] is None


def test_tokens_coerced_to_int():
    out = S.normalize({"input": "100", "output": None, "cache_read": 5})
    assert out["input"] == 100 and out["output"] == 0 and out["cache_read"] == 5


def test_canonical_account_precedence():
    assert (
        S.canonical_account({"account_uuid": "u", "account_id": "a", "email": "e"})
        == "u"
    )
    assert S.canonical_account({"account_id": "a", "email": "e"}) == "a"
    assert S.canonical_account({"email": "e@x.com"}) == "e@x.com"
    assert S.canonical_account({}) == "unknown"
    assert S.canonical_account(None) == "unknown"
