"""Acceptance tests for issue #323 — cost-telemetry freshness watchdog (cost-telemetry-v0 §D6)."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cost_telemetry_freshness as F  # noqa: E402

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _state(base: Path, last_success, extra=None):
    base.mkdir(parents=True, exist_ok=True)
    obj = {"last_success": last_success}
    if extra:
        obj.update(extra)
    (base / F.STATE_FILENAME).write_text(json.dumps(obj), encoding="utf-8")


def _shard(base: Path):
    (base / F.SHARD_FILENAME).write_text('{"x":1}\n', encoding="utf-8")


def test_stale_last_success_warns(tmp_path):
    _state(tmp_path, (NOW - timedelta(days=4)).isoformat())
    _shard(tmp_path)
    stale, reason = F.check(tmp_path, now=NOW)
    assert stale and "stale" in reason


def test_fresh_is_silent(tmp_path):
    _state(tmp_path, (NOW - timedelta(hours=1)).isoformat())
    _shard(tmp_path)
    stale, reason = F.check(tmp_path, now=NOW)
    assert not stale and "fresh" in reason


def test_successful_no_new_rows_does_not_false_alarm(tmp_path):
    # collector ran 2h ago, wrote 0 rows — shard mtime is old but last_success is recent → NOT stale
    _state(
        tmp_path,
        (NOW - timedelta(hours=2)).isoformat(),
        extra={"last_run_stats": {"rows_known_written": 0}},
    )
    _shard(tmp_path)
    stale, _ = F.check(tmp_path, now=NOW)
    assert not stale


def test_missing_shard_warns_even_if_recent(tmp_path):
    _state(
        tmp_path, (NOW - timedelta(hours=1)).isoformat()
    )  # recent success, but no shard
    stale, reason = F.check(tmp_path, now=NOW)
    assert stale and "usage.jsonl missing" in reason


def test_missing_state_warns(tmp_path):
    stale, reason = F.check(tmp_path, now=NOW)  # collector never ran
    assert stale and "never run" in reason


def test_missing_last_success_warns(tmp_path):
    _state(tmp_path, None)
    _shard(tmp_path)
    stale, reason = F.check(tmp_path, now=NOW)
    assert stale and "last_success" in reason


def test_malformed_state_warns(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / F.STATE_FILENAME).write_text("{bad json", encoding="utf-8")
    stale, reason = F.check(tmp_path, now=NOW)
    assert stale and "unreadable" in reason


def test_main_exit_codes(tmp_path):
    _state(tmp_path, (NOW - timedelta(hours=1)).isoformat())
    _shard(tmp_path)
    assert F.main(["--base", str(tmp_path)]) == 0  # fresh
    _state(tmp_path, (NOW - timedelta(days=5)).isoformat())
    assert (
        F.main(["--base", str(tmp_path), "--log", str(tmp_path / "log")]) == 1
    )  # stale
    assert (tmp_path / "log").exists()  # stale wrote a durable log line


def test_hook_mode_always_exits_zero_even_when_stale(tmp_path):
    """#339: --hook must exit 0 even when stale/missing (never fail a session start); CLI stays nonzero."""
    missing = tmp_path / "nope"
    log = tmp_path / "log"
    assert F.main(["--base", str(missing), "--log", str(log)]) == 1  # CLI: stale → nonzero
    assert F.main(["--base", str(missing), "--log", str(log), "--hook"]) == 0  # hook: always 0


def test_fresh_when_shard_in_per_host_subdir(tmp_path):
    """#339: real layout writes the shard to <base>/<host>/usage.jsonl, not <base>/usage.jsonl —
    freshness must find it there and NOT false-alarm 'shard missing'."""
    _state(tmp_path, (NOW - timedelta(days=1)).isoformat())
    host = tmp_path / "jns-mac"
    host.mkdir()
    (host / F.SHARD_FILENAME).write_text("{}\n", encoding="utf-8")
    stale, reason = F.check(tmp_path, now=NOW)
    assert stale is False, reason
