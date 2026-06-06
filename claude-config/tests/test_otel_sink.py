"""Acceptance tests for issue #230 — OTEL → readable-sink export (§1.1, §1.2).

Runs against SIMULATED OTEL pushes (per the ACs) — host-agnostic, no live exporter needed.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import otel_sink as S  # noqa: E402


# 1. sink written after a simulated OTEL push, all required fields present --------------------
def test_simulated_push_writes_all_fields(tmp_path):
    sink = tmp_path / "otel.jsonl"
    # simulate raw OTEL claude_code.token.usage datapoints (one per type)
    datapoints = [
        {"value": 1000, "attributes": {"type": "input", "model": "claude-sonnet-4"}},
        {"value": 200, "attributes": {"type": "output", "model": "claude-sonnet-4"}},
        {"value": 5000, "attributes": {"type": "cache_read", "model": "claude-sonnet-4"}},
        {"value": 800, "attributes": {"type": "cache_creation", "model": "claude-sonnet-4"}},
    ]
    rec = S.normalize_from_datapoints(datapoints)
    S.append_sink_record(sink, rec)
    got = S.read_sink(sink)
    assert len(got) == 1
    r = got[0]
    for f in (*S.TOKEN_FIELDS, "model"):
        assert f in r, f
    assert r["input"] == 1000 and r["cache_read"] == 5000 and r["model"] == "claude-sonnet-4"


# 2. cache-aware cost: cache_read ≈ 10% of same-token fresh input -----------------------------
def test_cache_read_is_ten_percent_of_fresh_input():
    n = 100_000
    for model in ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4"):
        fresh = S.compute_cost({"input": n, "model": model})
        cached = S.compute_cost({"cache_read": n, "model": model})
        assert fresh > 0
        assert cached == pytest.approx(0.10 * fresh, rel=1e-6), model
    # output is the dearest token type (§1.2)
    out = S.compute_cost({"output": n, "model": "claude-sonnet-4"})
    assert out > S.compute_cost({"input": n, "model": "claude-sonnet-4"})


# 3 & 4. exporter-freshness alarm fires when stale, not when fresh ----------------------------
def test_freshness_alarm_fires_when_stale(tmp_path):
    sink = tmp_path / "otel.jsonl"
    S.append_sink_record(sink, {"input": 1, "model": "claude-sonnet-4"})
    now = S.sink_last_write_ts(sink)
    # pure predicate
    assert S.is_stale(now - 100 * 3600, now, sla_seconds=24 * 3600) is True
    # via the file: backdate the sink's mtime 48h and check
    old = now - 48 * 3600
    os.utime(sink, (old, old))
    res = S.check_exporter_freshness(sink, now_ts=now, sla_seconds=24 * 3600)
    assert res["alarm"] is True and res["reason"] == "stale_exporter"


def test_freshness_alarm_quiet_when_fresh(tmp_path):
    sink = tmp_path / "otel.jsonl"
    S.append_sink_record(sink, {"input": 1, "model": "claude-sonnet-4"})
    now = S.sink_last_write_ts(sink) + 60  # one minute later
    res = S.check_exporter_freshness(sink, now_ts=now, sla_seconds=24 * 3600)
    assert res["alarm"] is False and res["reason"] == "fresh"
    assert S.is_stale(S.sink_last_write_ts(sink), now, sla_seconds=24 * 3600) is False


# 5. back-to-back sessions append without truncation/corruption -------------------------------
def test_back_to_back_appends_intact(tmp_path):
    sink = tmp_path / "otel.jsonl"
    S.append_sink_record(sink, {"input": 10, "output": 1, "model": "claude-opus-4", "session_id": "s1"})
    S.append_sink_record(sink, {"input": 20, "output": 2, "model": "claude-sonnet-4", "session_id": "s2"})
    got = S.read_sink(sink)
    assert len(got) == 2
    assert {r["session_id"] for r in got} == {"s1", "s2"}
    assert got[0]["input"] == 10 and got[1]["input"] == 20  # order + values preserved


# 6. missing sink path → graceful, actionable error (not silent) -----------------------------
def test_missing_sink_raises_actionable_error(tmp_path):
    missing = tmp_path / "does_not_exist.jsonl"
    with pytest.raises(FileNotFoundError) as ei:
        S.read_sink(missing)
    msg = str(ei.value)
    assert "OTEL_SINK_SETUP.md" in msg and "not found" in msg.lower()
    # freshness on a missing sink alarms as sink_missing (not a silent pass)
    res = S.check_exporter_freshness(missing, now_ts=1_000_000.0)
    assert res["alarm"] is True and res["reason"] == "sink_missing"
