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


# --- New GPT families: each resolves to its own row, not DEFAULT -------------------------------------


@pytest.mark.parametrize(
    "model,family_key",
    [
        ("gpt-5.2-codex", "gpt-5.2-codex"),
        ("gpt-5.3-codex", "gpt-5.3-codex"),
        ("gpt-5-codex", "gpt-5-codex"),
        ("gpt-5.4-mini", "gpt-5.4-mini"),
        ("gpt-5.2-mini", "gpt-5.2-mini"),
        ("gpt-5-mini", "gpt-5-mini"),
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("gpt-5.4", "gpt-5.4"),
        ("gpt-4o", "gpt-4o"),
    ],
)
def test_new_gpt_model_resolves_to_own_row(model, family_key):
    row = O._price_for(model)
    assert row is O.PRICES[family_key], f"{model!r} resolved wrong row"
    assert row is not O.DEFAULT_PRICE


# --- Numeric-guard: mini must NOT match flagship / codex row -----------------------------------------


@pytest.mark.parametrize(
    "mini,forbidden_family",
    [
        ("gpt-5.4-mini", "gpt-5.4"),
        ("gpt-5.2-mini", "gpt-5.2-codex"),  # dangerous cross-numeric case
        ("gpt-4o-mini", "gpt-4o"),
        ("gpt-5-mini", "gpt-5-codex"),
    ],
)
def test_mini_does_not_match_flagship(mini, forbidden_family):
    row = O._price_for(mini)
    assert row is not O.PRICES.get(forbidden_family), (
        f"{mini!r} must not resolve to {forbidden_family!r} price row"
    )


# --- Codex does NOT match mini -----------------------------------------------------------------------


def test_codex_does_not_match_mini():
    # gpt-5.2-codex must not accidentally resolve to a gpt-5.2-mini row
    row = O._price_for("gpt-5.2-codex")
    assert row is O.PRICES["gpt-5.2-codex"]
    assert row is not O.PRICES.get("gpt-5.2-mini")


# --- is_known_model covers new families --------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.2-codex",
        "gpt-5.3-codex",
        "gpt-5-codex",
        "gpt-5.4-mini",
        "gpt-5.2-mini",
        "gpt-5-mini",
        "gpt-4o-mini",
        "gpt-5.4",
        "gpt-4o",
    ],
)
def test_new_models_are_known(model):
    assert C.is_known_model(model) is True
    # strict=True must not raise
    cost = C.session_cost({"model": model, "input": 1_000_000}, strict=True)
    assert cost > 0


# --- Mini rates are cheaper than flagship for same base version --------------------------------------


def test_mini_cheaper_than_flagship():
    # input rate: gpt-5.4-mini < gpt-5.4
    mini_input = O.PRICES["gpt-5.4-mini"]["input"]
    flagship_input = O.PRICES["gpt-5.4"]["input"]
    assert mini_input < flagship_input, "mini input rate must be cheaper than flagship"


def test_mini_cheaper_than_codex():
    # output rate: gpt-5.2-mini < gpt-5.2-codex
    mini_out = O.PRICES["gpt-5.2-mini"]["output"]
    codex_out = O.PRICES["gpt-5.2-codex"]["output"]
    assert mini_out < codex_out, "mini output rate must be cheaper than codex"


# --- Predicate DRY: _matches_family is the canonical predicate ---------------------------------------


def test_matches_family_exported_and_consistent():
    # Confirm _matches_family exists on otel_sink and is callable
    assert callable(O._matches_family)
    # Confirm is_known_model uses the same predicate as _price_for:
    # for every real model, is_known_model == any(_matches_family(...)) over PRICES keys.
    # NOTE: we do NOT use `_price_for(m) is not DEFAULT_PRICE` as the oracle — claude-sonnet-4
    # IS the DEFAULT_PRICE row, so that identity check gives a false negative (the DEFAULT_PRICE
    # trap documented in the MAP-PLAN). Instead we compare directly against the family predicate.
    real_models = [
        "gpt-5.2-codex",
        "gpt-5.3-codex",
        "gpt-5-codex",
        "gpt-5.4",
        "gpt-5.5",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-5.4-mini",
        "gpt-5.2-mini",
        "gpt-5-mini",
        "claude-opus-4",
        "claude-sonnet-4",
        "claude-haiku-4",
    ]
    for m in real_models:
        known_via_collector = C.is_known_model(m)
        known_via_predicate = any(O._matches_family(m.lower(), fam) for fam in O.PRICES)
        assert known_via_collector == known_via_predicate, (
            f"is_known_model and _matches_family disagree for {m!r}"
        )
        # All real models must be known
        assert known_via_collector is True, f"{m!r} should be a known model"


# --- Unknown model still raises under strict (existing test_unknown_model_still_loud covers this) ---
# gpt-99-unknown test is preserved above; no additional test needed here.
