"""Acceptance tests for issue #239 — taxonomy + pattern schema + confidence (§1.3, §1.5)."""
import sys
from pathlib import Path

import pytest

_TK = Path(__file__).resolve().parents[1]
_AGENTS = _TK.parent
sys.path.insert(0, str(_TK / "scripts"))

import patterns as P  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

AREAS_PATH = _TK / "taxonomy" / "areas.yaml"
KNOWLEDGE_PATTERNS = _AGENTS / "knowledge" / "patterns"


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return yaml.safe_load(AREAS_PATH.read_text(encoding="utf-8"))


# 1. occurrence confidence arithmetic --------------------------------------------------------
def test_occurrence_confidence_arithmetic():
    assert P.compute_occurrence_confidence(0, source="observed") == 0.0
    # 1 observation, no bonus, N_cap=50 -> well below the 0.4 floor (conservative cap)
    one = P.compute_occurrence_confidence(1, source="observed", n_cap=50)
    assert 0.0 < one < 0.4, one
    # saturates at N_cap
    assert P.compute_occurrence_confidence(50, source="observed", n_cap=50) == 1.0


# 2. declared-only penalty -------------------------------------------------------------------
def test_declared_only_is_penalized():
    obs = P.compute_occurrence_confidence(20, source="observed")
    dec = P.compute_occurrence_confidence(20, source="declared")
    assert dec < obs, (dec, obs)


# 3. purely-declared quorum guard ------------------------------------------------------------
def test_declared_only_excluded_from_consensus_even_above_floor():
    # declared-only at a high observation count clears the numeric floor...
    conf = P.compute_occurrence_confidence(50, source="declared")
    assert conf >= P.DEFAULT_CONSENSUS_FLOOR, conf  # 1.0 * 0.5 = 0.5 >= 0.4
    # ...yet it is STILL excluded from CONSENSUS because `source` lacks 'observed'
    assert P.is_consensus_eligible(conf, "declared") is False
    # an observed pattern at the same confidence IS eligible
    assert P.is_consensus_eligible(conf, "observed") is True


# 4. bootstrap zero-start (the fake-consensus guard) -----------------------------------------
def test_bootstrap_is_vocabulary_only_zero_observations():
    vocab = P.bootstrap_vocabulary(KNOWLEDGE_PATTERNS)
    assert vocab, "expected some bootstrapped areas"
    assert "auth" in vocab  # auth-*.yaml carry category: auth
    seeded = P.seed_observation_counts(vocab, devs=["jason", "server-a", "laptop-wsl", "agent-b"])
    # EVERY (dev, area, key) starts at 0 — validated_count from the corpus is NOT mapped in
    assert seeded, "expected seeded counts"
    assert set(seeded.values()) == {0}, "observation_count must start at 0 for all seeds"
    # the bootstrap output carries no validation/status field that could leak into a count
    assert all(isinstance(k, tuple) and v == 0 for k, v in seeded.items())


# 5. low-confidence contradiction stays visible in CONFLICT/GAP ------------------------------
def test_low_confidence_contradiction_visible_but_not_in_consensus():
    patterns = [
        {"pattern_key": "A", "occurrence_confidence": 0.8, "source": "observed"},
        {"pattern_key": "A", "occurrence_confidence": 0.7, "source": "observed"},
        {"pattern_key": "A", "occurrence_confidence": 0.6, "source": "observed"},
        {"pattern_key": "B", "occurrence_confidence": 0.2, "source": "observed"},  # low-conf, contradicts A
    ]
    consensus = P.consensus_candidates(patterns)
    conflict = P.conflict_gap_candidates(patterns)
    low = patterns[-1]
    assert low not in consensus, "low-confidence pattern must be excluded from CONSENSUS"
    assert low in conflict, "low-confidence contradiction must stay visible in CONFLICT/GAP"


# 6. UNMAPPED surfacing ----------------------------------------------------------------------
def test_unmapped_never_force_bucketed(taxonomy):
    keys = [k for area in taxonomy["areas"].values() for k in area]
    assert P.resolve_pattern_key("JWT_WITH_REFRESH", keys) == "JWT_WITH_REFRESH"
    # a key that matches nothing -> UNMAPPED, never the closest existing key
    assert P.resolve_pattern_key("SOMETHING_TOTALLY_NEW", keys) == P.UNMAPPED
    assert P.is_taxonomy_gap(P.UNMAPPED) is True
    assert P.is_taxonomy_gap("JWT_WITH_REFRESH") is False


# 7. schema rejects authored confidence ------------------------------------------------------
def test_schema_rejects_authored_confidence(taxonomy):
    base = {
        "id": "PRAC-jason-error-handling-001", "dev": "jason", "area": "error-handling",
        "pattern_key": "CUSTOM_EXC_PER_MODULE", "practice": "custom exc per module",
        "source": "observed",
    }
    assert P.validate_authored_pattern(base, taxonomy) == []  # clean authored pattern is valid
    bad = dict(base, occurrence_confidence=0.99)              # hand-authored confidence
    errs = P.validate_authored_pattern(bad, taxonomy)
    assert any("occurrence_confidence" in e for e in errs), errs
    # an uncontrolled pattern_key for the area is rejected (use UNMAPPED instead)
    bad_key = dict(base, pattern_key="NOT_A_REAL_KEY")
    assert any("not in taxonomy" in e for e in P.validate_authored_pattern(bad_key, taxonomy))
