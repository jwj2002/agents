"""Acceptance tests for issue #264 — multi-provider PRICES (fleet-usage-monitor §6)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import otel_sink as O  # noqa: E402
import token_collector as C  # noqa: E402


# gpt-5.5 resolves to its own row, not the Claude DEFAULT --------------------------------------------
def test_gpt55_price_row():
    row = O._price_for("gpt-5.5")
    assert row is O.PRICES["gpt-5.5"]
    assert row is not O.DEFAULT_PRICE


def test_gpt55_prefix_variant():
    # a family variant still matches gpt-5.5 by prefix
    assert O._price_for("gpt-5.5-turbo") is O.PRICES["gpt-5.5"]


def test_gpt55_compute_cost_matches_rate():
    cost = O.compute_cost(
        {
            "model": "gpt-5.5",
            "input": 1_000_000,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0,
        }
    )
    assert cost == pytest.approx(O.PRICES["gpt-5.5"]["input"] * 1_000_000)
    # output is dearer than input for gpt-5.5
    out = O.compute_cost({"model": "gpt-5.5", "output": 1_000_000})
    assert out > cost


# strict known/unknown behavior preserved (token_collector) -----------------------------------------
def test_known_codex_model_not_strict_error():
    # gpt-5.5 is now known → session_cost(strict) must NOT raise
    assert C.is_known_model("gpt-5.5") is True
    val = C.session_cost({"model": "gpt-5.5", "input": 1000}, strict=True)
    assert val > 0


def test_unknown_model_still_loud():
    assert C.is_known_model("gpt-99-unknown") is False
    with pytest.raises(ValueError):
        C.session_cost({"model": "gpt-99-unknown", "input": 1000}, strict=True)


# compute_cost fallback still works for unknown (non-strict path) ------------------------------------
def test_unknown_model_compute_cost_falls_back():
    # compute_cost is the lenient path (falls back to DEFAULT_PRICE); strictness lives in session_cost
    assert O.compute_cost({"model": "totally-unknown", "input": 1000}) > 0


# Opus 4.8 sanity cross-check against the §2.1 real billing figure -----------------------------------
def test_opus_rates_sanity_vs_real_session():
    # the REAL measured mix (not 954M pure input) → ~$2,159 reference (§2.1)
    real_mix = {
        "model": "claude-opus-4",
        "input": 657_029,
        "output": 4_070_961,
        "cache_read": 924_428_695,
        "cache_creation": 24_381_544,
    }
    cost = O.compute_cost(real_mix)
    assert cost == pytest.approx(2159, rel=0.05), (
        f"opus rates drifted: ${cost:,.2f} vs $2,159 ref"
    )
