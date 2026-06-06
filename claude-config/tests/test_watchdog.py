"""Acceptance tests for issue #232 — dead-man's-switch watchdog alarm logic (§0.1 / §2.5).

Host-agnostic: simulated observations, no live hub/poller. The deploy (launchd poller #221, hub
registry persistence) is server-a's lane and deferred; this validates the alarm LOGIC it calls.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import watchdog as W  # noqa: E402
import otel_sink as O  # noqa: E402

NOW = 1_000_000.0
FRESH = NOW - 60  # 1 min ago
STALE = NOW - 100 * 3600  # 100h ago, well past the 24h SLA


def _names(alerts):
    return {a["alert"] for a in alerts}


# Required: hub-unreachable → correct named alert (not generic) --------------------------------------
def test_hub_unreachable_named():
    obs = {"host": "server-a", "hub_reachable": False}
    alerts = W.classify_liveness(obs, now_ts=NOW)
    assert _names(alerts) == {W.ALERT_HUB_UNREACHABLE}
    assert alerts[0]["host"] == "server-a"


# Required: poller-down (poller heartbeat absent > SLA) → alarm --------------------------------------
def test_poller_down():
    obs = {
        "host": "h",
        "hub_reachable": True,
        "poller_last_beat": STALE,
        "capture_last_beat": FRESH,
        "payload": {"x": 1},
        "payload_valid": True,
    }
    assert W.ALERT_POLLER_DOWN in _names(W.classify_liveness(obs, now_ts=NOW))
    # absent poller beat is also poller-down (fail-safe)
    obs2 = {
        "host": "h",
        "hub_reachable": True,
        "poller_last_beat": None,
        "capture_last_beat": FRESH,
        "payload": {"x": 1},
        "payload_valid": True,
    }
    assert W.ALERT_POLLER_DOWN in _names(W.classify_liveness(obs2, now_ts=NOW))


# Required: heartbeat present but empty payload → heartbeat-only, NOT poller-down --------------------
def test_heartbeat_only_not_poller_down():
    obs = {
        "host": "h",
        "hub_reachable": True,
        "poller_last_beat": FRESH,
        "capture_last_beat": FRESH,
        "payload": {},
        "payload_valid": True,
    }
    names = _names(W.classify_liveness(obs, now_ts=NOW))
    assert names == {W.ALERT_HEARTBEAT_ONLY}
    assert W.ALERT_POLLER_DOWN not in names


# Required: corrupt payload → corrupt alert WITH offending shard id ----------------------------------
def test_corrupt_payload_with_shard():
    obs = {
        "host": "h",
        "hub_reachable": True,
        "poller_last_beat": FRESH,
        "capture_last_beat": FRESH,
        "payload": {"raw": "{bad json"},
        "payload_valid": False,
        "shard": "jns-mac/2026-06-06",
    }
    alerts = W.classify_liveness(obs, now_ts=NOW)
    corrupt = [a for a in alerts if a["alert"] == W.ALERT_CORRUPT]
    assert corrupt and corrupt[0]["shard"] == "jns-mac/2026-06-06"


# Required: stale-exporter (OTEL sink last-write > SLA) → stale-exporter alert -----------------------
def test_stale_exporter_alert(tmp_path):
    sink = tmp_path / "otel.jsonl"
    O.append_sink_record(sink, {"input": 1, "model": "claude-sonnet-4"})
    last = O.sink_last_write_ts(sink)
    res = W.check_exporter(sink, now_ts=last + 100 * 3600)  # 100h later
    assert res is not None and res["alert"] == W.ALERT_STALE_EXPORTER
    # fresh sink → no alert
    assert W.check_exporter(sink, now_ts=last + 60) is None
    # missing sink → still a stale-exporter alert (reason sink_missing), never silent
    missing = W.check_exporter(tmp_path / "nope.jsonl", now_ts=NOW)
    assert (
        missing["alert"] == W.ALERT_STALE_EXPORTER
        and missing["reason"] == "sink_missing"
    )


# Required: exclusion-rate alarm — deliberative session containing a diff → flagged -----------------
def test_implementation_like_but_excluded():
    session = {
        "session_id": "s1",
        "work_type": "deliberative",
        "files_edited": ["a.py"],
        "commits": ["abc123"],
    }
    a = W.implementation_like_but_excluded(session)
    assert a is not None and a["alert"] == W.ALERT_IMPL_EXCLUDED
    assert "files_edited" in a["artifacts"]
    # a clean deliberative session (no artifacts) is fine
    assert W.implementation_like_but_excluded({"work_type": "deliberative"}) is None
    # an implementation session with edits is expected — not flagged
    assert (
        W.implementation_like_but_excluded(
            {"work_type": "implementation", "files_edited": ["a.py"]}
        )
        is None
    )


# Required: PROVE-coverage alarm — code edits but no INDEPENDENT verification → alarm ----------------
def test_prove_coverage_alarm():
    session = {"session_id": "s2", "files_edited": ["a.py"], "commits": ["abc"]}
    # not in the independently-verified set → alarm
    assert (
        W.prove_coverage_alarm(session, verified_ids=set())["alert"]
        == W.ALERT_PROVE_COVERAGE
    )
    # INDEPENDENTLY verified (CI/test record from an external source) → no alarm
    assert W.prove_coverage_alarm(session, verified_ids={"s2"}) is None
    # SELF-REPORTED success must NOT suppress the alarm (Codex F7 independence)
    assert (
        W.prove_coverage_alarm(
            {**session, "tests_ran": True, "ci": "x"}, verified_ids=set()
        )["alert"]
        == W.ALERT_PROVE_COVERAGE
    )
    # no code change → nothing to verify
    assert W.prove_coverage_alarm({"session_id": "s3"}, verified_ids=set()) is None
    # a PR-only or tests-only artifact still counts as a code change (B5)
    assert W.prove_coverage_alarm({"session_id": "s4", "prs": [12]}, verified_ids=set())
    assert W.prove_coverage_alarm(
        {"session_id": "s5", "tests_changed": ["t.py"]}, verified_ids=set()
    )


# Required: reconciliation gap — filesystem change not in session report → flagged ------------------
def test_reconciliation_gap():
    g = W.reconciliation_gap(
        reported_files=["a.py"], filesystem_changed_files=["a.py", "secret_leak.py"]
    )
    assert g["alert"] == W.ALERT_RECONCILIATION_GAP
    assert g["unreported_changed_files"] == ["secret_leak.py"]
    # everything reported → no gap
    assert W.reconciliation_gap(["a.py", "b.py"], ["a.py", "b.py"]) is None


# Integration: host goes silent for > SLA → roster detects and raises host-silent -------------------
def test_roster_detects_silent_host():
    expected = ["scratch", "server-a", "laptop-wsl"]
    last_seen = {"scratch": FRESH, "server-a": STALE}  # laptop-wsl never seen
    alerts = W.check_roster(expected, last_seen, now_ts=NOW)
    silent = {a["host"]: a["reason"] for a in alerts}
    assert silent == {"server-a": "last_seen_exceeded_sla", "laptop-wsl": "never_seen"}
    assert "scratch" not in silent  # fresh host not alarmed


# Integration: all five liveness states are distinguishable in the alert output --------------------
def test_all_five_states_distinguishable():
    observations = [
        {"host": "a", "hub_reachable": False},
        {
            "host": "b",
            "hub_reachable": True,
            "poller_last_beat": STALE,
            "capture_last_beat": STALE,
            "payload": {"x": 1},
            "payload_valid": True,
        },
        {
            "host": "c",
            "hub_reachable": True,
            "poller_last_beat": FRESH,
            "capture_last_beat": FRESH,
            "payload": {},
            "payload_valid": True,
        },
        {
            "host": "d",
            "hub_reachable": True,
            "poller_last_beat": FRESH,
            "capture_last_beat": FRESH,
            "payload": {"raw": "x"},
            "payload_valid": False,
            "shard": "d/1",
        },
    ]
    alerts = W.run_liveness_watchdog(observations, now_ts=NOW)
    names = _names(alerts)
    assert W.ALERT_HUB_UNREACHABLE in names
    assert W.ALERT_POLLER_DOWN in names
    assert W.ALERT_HEARTBEAT_ONLY in names
    assert W.ALERT_CORRUPT in names
    # add a stale exporter via the aggregator's sink check using a missing sink
    with_sink = W.run_liveness_watchdog(
        observations, now_ts=NOW, sink_path="/nonexistent.jsonl"
    )
    assert W.ALERT_STALE_EXPORTER in _names(with_sink)
    # five DISTINCT names, not one generic "silent"
    assert len(_names(with_sink)) >= 5


# Content-completeness: monotonic sequence gaps + field counts --------------------------------------
def test_sequence_gaps_and_field_completeness():
    # missing seq 3 in a 1..5 shard
    recs = [{"seq": 1}, {"seq": 2}, {"seq": 4}, {"seq": 5}, {"seq": 5}]
    g = W.sequence_gaps("shardX", recs)
    assert g["alert"] == W.ALERT_SEQUENCE_GAP
    assert g["missing"] == [3] and g["duplicates"] == [5]
    # contiguous, unique → no gap
    assert W.sequence_gaps("ok", [{"seq": 1}, {"seq": 2}, {"seq": 3}]) is None
    # field completeness
    fc = W.field_completeness(
        {"ts": 1, "model": ""}, ("ts", "model", "session_id"), shard="s"
    )
    assert fc["alert"] == W.ALERT_FIELD_INCOMPLETE
    assert set(fc["missing_fields"]) == {"model", "session_id"}
    assert W.field_completeness({"ts": 1, "model": "m"}, ("ts", "model")) is None


# Exclusion-rate aggregate alarms ------------------------------------------------------------------
def test_exclusion_rate_alarms():
    sessions = [
        {"work_type": "deliberative"},
        {"work_type": "ops"},
        {"work_type": "deliberative"},
        {"work_type": "implementation"},
    ]  # 3/4 excluded
    names = _names(W.exclusion_rate_alarm(sessions, threshold=0.5))
    assert W.ALERT_EXCLUSION_RATE in names
    # unclassified rate
    unclassified = [
        {"work_type": None},
        {"work_type": None},
        {"work_type": "implementation"},
    ]
    assert W.ALERT_UNCLASSIFIED_RATE in _names(
        W.exclusion_rate_alarm(unclassified, threshold=0.5)
    )
    # empty input → no alarms, no division error
    assert W.exclusion_rate_alarm([]) == []


# run_exclusion_watchdog aggregates everything -----------------------------------------------------
def test_run_exclusion_watchdog():
    sessions = [
        {
            "session_id": "s1",
            "work_type": "deliberative",
            "files_edited": ["a.py"],
        },  # impl-excluded
        {
            "session_id": "s2",
            "work_type": "implementation",
            "files_edited": ["b.py"],
        },  # no prove
    ]
    recon = {"reported_files": ["a.py"], "filesystem_changed_files": ["a.py", "c.py"]}
    alerts = W.run_exclusion_watchdog(
        sessions, reconciliation=recon, threshold=0.9, verified_ids=set()
    )
    names = _names(alerts)
    assert W.ALERT_IMPL_EXCLUDED in names
    assert W.ALERT_PROVE_COVERAGE in names
    assert W.ALERT_RECONCILIATION_GAP in names


# Fail-closed (Codex review): missing/unknown evidence must ALARM, never read as healthy ------------
def test_fail_closed_paths():
    # missing hub_reachable field → hub-unreachable (not silently healthy)
    assert _names(W.classify_liveness({"host": "h"}, now_ts=NOW)) == {
        W.ALERT_HUB_UNREACHABLE
    }
    # unknown 'now' makes any heartbeat stale → poller-down fires (fail-closed staleness)
    obs = {
        "host": "h",
        "hub_reachable": True,
        "poller_last_beat": FRESH,
        "capture_last_beat": FRESH,
        "payload": {"x": 1},
        "payload_valid": True,
    }
    assert W.ALERT_POLLER_DOWN in _names(W.classify_liveness(obs, now_ts=None))
    # a shard whose records lack usable seq numbers is NOT silently contiguous
    g = W.sequence_gaps("s", [{"ts": 1}, {"ts": 2}])
    assert (
        g is not None and g["alert"] == W.ALERT_SEQUENCE_GAP and g["unsequenced"] == 2
    )
    # bool seq values are not mistaken for ints
    g2 = W.sequence_gaps("s", [{"seq": True}, {"seq": 2}])
    assert g2 is not None and g2["unsequenced"] == 1


# Fail-closed (Codex re-review): a dead CAPTURE heartbeat alarms even when the poller beat is fresh ---
def test_capture_down_not_masked_by_fresh_poller():
    dead_capture = {
        "host": "h",
        "hub_reachable": True,
        "poller_last_beat": FRESH,
        "capture_last_beat": STALE,
        "payload": {"x": 1},
        "payload_valid": True,
    }
    names = _names(W.classify_liveness(dead_capture, now_ts=NOW))
    assert W.ALERT_CAPTURE_DOWN in names
    assert W.ALERT_POLLER_DOWN not in names  # poller is fine; only capture is down
    # an entirely absent capture beat likewise alarms
    absent = {"host": "h", "hub_reachable": True, "poller_last_beat": FRESH}
    assert W.ALERT_CAPTURE_DOWN in _names(W.classify_liveness(absent, now_ts=NOW))
