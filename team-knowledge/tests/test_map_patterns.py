"""Acceptance tests for issue #244 — map_patterns divergence assembler (§1.0/§1.4/§1.6)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

yaml = pytest.importorskip("yaml")

import map_patterns as M  # noqa: E402
import patterns as P  # noqa: E402

TEAM = ["jason", "server-a", "laptop-wsl", "agent-b"]


def _e(dev, area, key, *, conf=0.5, source="observed", count=5, raw=None):
    e = {
        "id": f"{dev}:{area}:{key}",
        "dev": dev,
        "area": area,
        "pattern_key": key,
        "practice": "p",
        "source": source,
        "observation_count": count,
        "occurrence_confidence": conf,
        "efficacy_confidence": None,
    }
    if raw is not None:
        e["raw_behavior"] = raw
    return e


def _write(patterns_dir, area, dev, entries):
    d = Path(patterns_dir) / area
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{dev}.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": 1, "dev": dev, "area": area, "patterns": entries}
        )
    )


# CONSENSUS detection: 3/4 share a key, eligible -----------------------------------------------------
def test_consensus_detection(tmp_path):
    for dev in ("jason", "server-a", "laptop-wsl"):
        _write(
            tmp_path,
            "error-handling",
            dev,
            [_e(dev, "error-handling", "CUSTOM_EXC_PER_MODULE")],
        )
    res = M.assemble(tmp_path, team_devs=TEAM)
    row = res["areas"]["error-handling"]
    assert row["outcome"] == M.CONSENSUS
    assert row["consensus_key"] == "CUSTOM_EXC_PER_MODULE"
    assert row["state"] == M.STATE_NOT_DISCONFIRMED


# Purely-declared quorum block: 3/4 same key but all declared → NOT consensus -------------------------
def test_purely_declared_blocked_from_quorum(tmp_path):
    for dev in ("jason", "server-a", "laptop-wsl"):
        _write(
            tmp_path,
            "error-handling",
            dev,
            [
                _e(
                    dev,
                    "error-handling",
                    "CUSTOM_EXC_PER_MODULE",
                    source="declared",
                    count=0,
                    conf=0.0,
                )
            ],
        )
    row = M.assemble(tmp_path, team_devs=TEAM)["areas"]["error-handling"]
    assert row["outcome"] != M.CONSENSUS
    assert row["outcome"] in (M.GAP, M.DIVERGENCE)
    assert row.get("note") == "quorum_blocked_purely_declared"


# Disconfirm gate — blocked-contradicted ------------------------------------------------------------
def test_disconfirm_blocked_contradicted(tmp_path):
    for dev in ("jason", "server-a", "laptop-wsl"):
        _write(
            tmp_path,
            "error-handling",
            dev,
            [_e(dev, "error-handling", "CUSTOM_EXC_PER_MODULE")],
        )
    res = M.assemble(
        tmp_path,
        team_devs=TEAM,
        is_disconfirmed=lambda a, k: (
            (a, k) == ("error-handling", "CUSTOM_EXC_PER_MODULE")
        ),
    )
    row = res["areas"]["error-handling"]
    assert row["state"] == M.STATE_BLOCKED
    assert row["arbiter"] == "jason"
    assert row.get("state") != M.STATE_NOT_DISCONFIRMED


# Disconfirm gate — not-disconfirmed, never "validated" ----------------------------------------------
def test_not_disconfirmed_never_validated(tmp_path):
    for dev in ("jason", "server-a", "laptop-wsl"):
        _write(
            tmp_path,
            "error-handling",
            dev,
            [_e(dev, "error-handling", "CUSTOM_EXC_PER_MODULE")],
        )
    res = M.assemble(tmp_path, team_devs=TEAM)  # no disconfirmation
    row = res["areas"]["error-handling"]
    assert row["state"] == "not-disconfirmed"
    # the string "validated" must NOT appear anywhere in the assembler output (§1.6 step-2 name)
    assert "validated" not in json.dumps(res)
    assert "validated" not in M.render_map(res)


# CONFLICT routing: mutually-exclusive keys → arbiter jason, no auto-promotion -----------------------
def test_conflict_routing(tmp_path):
    for dev in ("jason", "server-a"):
        _write(
            tmp_path, "error-handling", dev, [_e(dev, "error-handling", "BARE_EXCEPT")]
        )
    for dev in ("laptop-wsl", "agent-b"):
        _write(
            tmp_path,
            "error-handling",
            dev,
            [_e(dev, "error-handling", "CUSTOM_EXC_PER_MODULE")],
        )
    contradictions = {"error-handling": [["BARE_EXCEPT", "CUSTOM_EXC_PER_MODULE"]]}
    row = M.assemble(tmp_path, team_devs=TEAM, contradictions=contradictions)["areas"][
        "error-handling"
    ]
    assert row["outcome"] == M.CONFLICT
    assert row["arbiter"] == "jason"
    assert sorted(row["conflict_keys"]) == ["BARE_EXCEPT", "CUSTOM_EXC_PER_MODULE"]
    assert "state" not in row  # never auto-promoted


# GAP detection: 2/4 devs have no entry for an area ------------------------------------------------
def test_gap_detection(tmp_path):
    for dev in ("jason", "server-a"):
        _write(
            tmp_path,
            "concurrency",
            dev,
            [_e(dev, "concurrency", "NO_BLOCKING_IN_ASYNC")],
        )
    row = M.assemble(tmp_path, team_devs=TEAM)["areas"]["concurrency"]
    assert row["outcome"] == M.GAP
    assert set(row["missing_devs"]) == {"laptop-wsl", "agent-b"}


# UNMAPPED taxonomy-gap signal --------------------------------------------------------------------
def test_unmapped_taxonomy_gap(tmp_path):
    _write(
        tmp_path,
        "security",
        "jason",
        [_e("jason", "security", P.UNMAPPED, raw="WEIRD_BEHAVIOR", count=3)],
    )
    res = M.assemble(tmp_path, team_devs=TEAM)
    gaps = res["taxonomy_gaps"]
    assert any(
        g["area"] == "security"
        and g["raw_behavior"] == "WEIRD_BEHAVIOR"
        and g["observation_count"] == 3
        for g in gaps
    )
    # the row is not bucketed to a real key
    assert res["areas"]["security"]["outcome"] == M.GAP


# Low-confidence contradiction stays visible (not filtered by the floor) ---------------------------
def test_low_confidence_contradiction_visible(tmp_path):
    for dev in ("jason", "server-a", "laptop-wsl"):
        _write(
            tmp_path,
            "error-handling",
            dev,
            [_e(dev, "error-handling", "CUSTOM_EXC_PER_MODULE")],
        )
    # 4th dev: a contradictory key BELOW the floor (0.2 < 0.4) — must still surface
    _write(
        tmp_path,
        "error-handling",
        "agent-b",
        [
            _e(
                "agent-b",
                "error-handling",
                "STRUCTURED_ERROR_RESPONSE",
                conf=0.2,
                count=1,
            )
        ],
    )
    res = M.assemble(tmp_path, team_devs=TEAM)
    low = res["low_confidence_contradictions"]
    assert any(
        c["pattern_key"] == "STRUCTURED_ERROR_RESPONSE" and c["dev"] == "agent-b"
        for c in low
    )
    # consensus still detected, but the sub-floor signal is NOT silently dropped
    assert res["areas"]["error-handling"]["outcome"] == M.CONSENSUS


# §1.3 rule 3 + §1.6 consistency: low-conf contradictory stays visible AND CONFLICT never promotes --
def test_conflict_keeps_low_conf_and_never_promotes(tmp_path):
    # mutually-exclusive keys → CONFLICT, with one side sub-floor
    _write(
        tmp_path,
        "error-handling",
        "jason",
        [_e("jason", "error-handling", "BARE_EXCEPT")],
    )
    _write(
        tmp_path,
        "error-handling",
        "server-a",
        [_e("server-a", "error-handling", "BARE_EXCEPT")],
    )
    _write(
        tmp_path,
        "error-handling",
        "laptop-wsl",
        [
            _e(
                "laptop-wsl",
                "error-handling",
                "CUSTOM_EXC_PER_MODULE",
                conf=0.2,
                count=1,
            )
        ],
    )
    contradictions = {"error-handling": [["BARE_EXCEPT", "CUSTOM_EXC_PER_MODULE"]]}
    row = M.assemble(tmp_path, team_devs=TEAM, contradictions=contradictions)["areas"][
        "error-handling"
    ]
    assert row["outcome"] == M.CONFLICT
    # §1.6: never auto-promoted
    assert "state" not in row and not row.get("advisory_publishable")
    # §1.3 rule 3: the sub-floor contradictory signal stays visible
    assert any(
        c["pattern_key"] == "CUSTOM_EXC_PER_MODULE"
        for c in row["contradictions_visible"]
    )


# Within-dev divergence: a dev applying two different keys in one area ------------------------------
def test_within_dev_divergence(tmp_path):
    _write(
        tmp_path,
        "testing",
        "jason",
        [
            _e("jason", "testing", "SQLITE_COMPAT_TESTS"),
            _e("jason", "testing", "FIXTURE_FACTORIES"),
        ],
    )
    res = M.assemble(tmp_path, team_devs=TEAM)
    assert set(res["within_dev_divergence"]["jason"]["testing"]) == {
        "FIXTURE_FACTORIES",
        "SQLITE_COMPAT_TESTS",
    }
