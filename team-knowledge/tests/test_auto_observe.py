"""Acceptance tests for issue #243 — auto-observe → patterns/<area>/<dev>.yaml (§1.1/§1.2/§1.3).

A taxonomy FIXTURE is used (not the controlled areas.yaml) so the behavioral keys the required tests
exercise (MISSING_TEST / SKIP_TEST / ALWAYS_TESTS) exist for `testing` — auto_observe is taxonomy-
driven by design, and minting real keys is a governance action, not this feature's job.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

yaml = pytest.importorskip("yaml")

import auto_observe as A  # noqa: E402
import patterns as P  # noqa: E402

TAXONOMY = {
    "config": {"n_cap": 50, "consensus_floor": 0.4},
    "areas": {
        "testing": ["MISSING_TEST", "SKIP_TEST", "ALWAYS_TESTS", "SQLITE_COMPAT_TESTS"],
        "security": ["NO_SECRETS_IN_CODE"],
    },
}


def _read(patterns_dir, area, dev):
    return yaml.safe_load((Path(patterns_dir) / area / f"{dev}.yaml").read_text())


# Basic derivation: 5 MISSING_TEST guards in testing → entry with count=5, source observed -----------
def test_basic_derivation(tmp_path):
    records = [
        {"dev": "jason", "area": "testing", "guards_fired": ["MISSING_TEST"]}
        for _ in range(5)
    ]
    A.auto_observe("jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    doc = _read(tmp_path, "testing", "jason")
    entry = next(e for e in doc["patterns"] if e["pattern_key"] == "MISSING_TEST")
    assert entry["observation_count"] == 5
    assert entry["source"] == "observed"
    assert entry["dev"] == "jason" and entry["area"] == "testing"


# Confidence computed, never authored ---------------------------------------------------------------
def test_confidence_computed_not_authored(tmp_path):
    # an authored occurrence_confidence in the INPUT must NOT propagate to the OUTPUT
    records = [
        {
            "dev": "jason",
            "area": "testing",
            "guards_fired": "MISSING_TEST",
            "occurrence_confidence": 0.999,
        }
        for _ in range(3)
    ]
    A.auto_observe("jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    entry = next(
        e
        for e in _read(tmp_path, "testing", "jason")["patterns"]
        if e["pattern_key"] == "MISSING_TEST"
    )
    expected = P.compute_occurrence_confidence(3, source="observed", n_cap=50)
    assert entry["occurrence_confidence"] == expected
    assert (
        entry["occurrence_confidence"] != 0.999
    )  # the authored literal did not propagate


# UNMAPPED path: a behavior matching no key → UNMAPPED, not the closest match ------------------------
def test_unmapped_not_force_bucketed(tmp_path):
    records = [
        {"dev": "jason", "area": "security", "guards_fired": ["WEIRD_NEW_BEHAVIOR"]}
    ]
    A.auto_observe("jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    doc = _read(tmp_path, "security", "jason")
    entry = doc["patterns"][0]
    assert entry["pattern_key"] == P.UNMAPPED
    assert (
        entry["pattern_key"] != "NO_SECRETS_IN_CODE"
    )  # NOT force-bucketed to the closest key
    assert entry["raw_behavior"] == "WEIRD_NEW_BEHAVIOR"


# Declared-vs-observed delta: declared ALWAYS_TESTS but observed SKIP_TEST → conflict flagged --------
def test_declared_observed_delta(tmp_path):
    declared = [
        {
            "area": "testing",
            "pattern_key": "ALWAYS_TESTS",
            "practice": "I always write tests",
        }
    ]
    records = [
        {"dev": "jason", "area": "testing", "guards_fired": "SKIP_TEST"}
        for _ in range(3)
    ]
    out = A.auto_observe(
        "jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path, declared=declared
    )
    doc = _read(tmp_path, "testing", "jason")
    by_key = {e["pattern_key"]: e for e in doc["patterns"]}
    # declared entry retained, observed SKIP_TEST written alongside
    assert by_key["ALWAYS_TESTS"]["source"] == "declared"
    assert by_key["ALWAYS_TESTS"]["observation_count"] == 0
    assert by_key["SKIP_TEST"]["source"] == "observed"
    assert by_key["SKIP_TEST"]["observation_count"] == 3
    # the conflict is FLAGGED, not suppressed
    assert by_key["SKIP_TEST"]["conflict"] is True
    assert by_key["SKIP_TEST"]["conflicts_with_declared"] == "ALWAYS_TESTS"
    assert {
        "area": "testing",
        "declared": "ALWAYS_TESTS",
        "observed": "SKIP_TEST",
    } in out["deltas"]


# source observed+declared when a key is both declared and observed ----------------------------------
def test_source_observed_plus_declared(tmp_path):
    declared = [{"area": "testing", "pattern_key": "MISSING_TEST", "practice": "x"}]
    records = [
        {"dev": "jason", "area": "testing", "guards_fired": "MISSING_TEST"}
        for _ in range(2)
    ]
    A.auto_observe(
        "jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path, declared=declared
    )
    entry = next(
        e
        for e in _read(tmp_path, "testing", "jason")["patterns"]
        if e["pattern_key"] == "MISSING_TEST"
    )
    assert entry["source"] == "observed+declared"
    assert entry["observation_count"] == 2


# Incremental re-run: 5 then 3 → count 8, recomputed, no duplicates ---------------------------------
def test_incremental_rerun(tmp_path):
    five = [
        {"dev": "jason", "area": "testing", "guards_fired": "MISSING_TEST"}
        for _ in range(5)
    ]
    A.auto_observe("jason", five, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    three = [
        {"dev": "jason", "area": "testing", "guards_fired": "MISSING_TEST"}
        for _ in range(3)
    ]
    A.auto_observe("jason", three, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    doc = _read(tmp_path, "testing", "jason")
    missing = [e for e in doc["patterns"] if e["pattern_key"] == "MISSING_TEST"]
    assert len(missing) == 1  # no duplicate entry
    assert missing[0]["observation_count"] == 8
    assert missing[0]["occurrence_confidence"] == P.compute_occurrence_confidence(
        8, n_cap=50
    )


# Dev isolation: running as jason never writes another dev's file ------------------------------------
def test_dev_isolation(tmp_path):
    records = [
        {"dev": "jason", "area": "testing", "guards_fired": "MISSING_TEST"},
        {
            "dev": "server-a",
            "area": "testing",
            "guards_fired": "MISSING_TEST",
        },  # not ours
    ]
    A.auto_observe("jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    assert (Path(tmp_path) / "testing" / "jason.yaml").exists()
    assert not (Path(tmp_path) / "testing" / "server-a.yaml").exists()
    # and jason's file did not absorb server-a's observation
    doc = _read(tmp_path, "testing", "jason")
    assert (
        next(e for e in doc["patterns"] if e["pattern_key"] == "MISSING_TEST")[
            "observation_count"
        ]
        == 1
    )


# efficacy_confidence stays null no matter how much telemetry ----------------------------------------
def test_efficacy_stays_null(tmp_path):
    records = [
        {"dev": "jason", "area": "testing", "guards_fired": "MISSING_TEST"}
        for _ in range(40)
    ]
    A.auto_observe("jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    for e in _read(tmp_path, "testing", "jason")["patterns"]:
        assert e["efficacy_confidence"] is None


# Output validates against the §1.3 schema (computed fields required, efficacy None) ----------------
def test_output_schema_valid(tmp_path):
    records = [
        {"dev": "jason", "area": "testing", "guards_fired": "MISSING_TEST"}
        for _ in range(5)
    ]
    out = A.auto_observe("jason", records, taxonomy=TAXONOMY, patterns_dir=tmp_path)
    for e in out["entries"]:
        assert A.validate_observed_entry(e, taxonomy=TAXONOMY) == []


# extract_observations reads guards_fired + codex_overturned, filtered to the dev -------------------
def test_extract_observations():
    records = [
        {
            "dev": "jason",
            "area": "testing",
            "guards_fired": ["MISSING_TEST", "SKIP_TEST"],
        },
        {"dev": "jason", "area": "code-review", "codex_overturned": True},
        {
            "dev": "server-a",
            "area": "testing",
            "guards_fired": "MISSING_TEST",
        },  # filtered out
        {"dev": "jason"},  # no area → skipped
    ]
    obs = A.extract_observations(records, dev="jason")
    cands = sorted((o["area"], o["candidate_key"]) for o in obs)
    assert cands == [
        ("code-review", "CODEX_OVERTURNED"),
        ("testing", "MISSING_TEST"),
        ("testing", "SKIP_TEST"),
    ]
