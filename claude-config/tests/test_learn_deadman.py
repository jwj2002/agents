"""Tests for the learn-loop dead-man's switch (issue #359).

No live sends: send_fn is injected. State path and clock are injected so tests
never touch the real machine state.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import learn_deadman as D  # noqa: E402

NOW = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)
CFG = {
    "enabled": True,
    "account": {"type": "gmail", "sender": "me@gmail.com", "creds": "~/x/token.json"},
    "recipient": "me@gmail.com",
}
NO_CFG = {"enabled": False}


def _recorder():
    calls = []

    def send(**kwargs):
        calls.append(kwargs)

    return calls, send


def _state(tmp_path, **kw):
    p = tmp_path / "deadman.json"
    if kw:
        p.write_text(json.dumps(kw), encoding="utf-8")
    return p


def test_first_trip_arms_without_alert(tmp_path):
    calls, send = _recorder()
    p = _state(tmp_path)
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=send)
    assert "armed" in msg
    assert calls == []
    assert json.loads(p.read_text())["tripped_since"] == NOW.isoformat()


def test_stuck_under_threshold_no_alert(tmp_path):
    calls, send = _recorder()
    p = _state(tmp_path, tripped_since=(NOW - timedelta(days=3)).isoformat())
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=send)
    assert "no alert" in msg
    assert calls == []


def test_stuck_past_threshold_sends_alert(tmp_path):
    calls, send = _recorder()
    p = _state(tmp_path, tripped_since=(NOW - timedelta(days=8)).isoformat())
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=send)
    assert "EMAILED" in msg
    assert len(calls) == 1
    assert "DEAD-MAN ALERT" in calls[0]["subject"]
    assert "8 days" in calls[0]["body"]
    assert json.loads(p.read_text())["last_alert_at"] == NOW.isoformat()


def test_alert_rate_limited(tmp_path):
    calls, send = _recorder()
    p = _state(
        tmp_path,
        tripped_since=(NOW - timedelta(days=10)).isoformat(),
        last_alert_at=(NOW - timedelta(days=1)).isoformat(),
    )
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=send)
    assert "rate-limited" in msg
    assert calls == []


def test_alert_fires_again_after_rate_limit_window(tmp_path):
    calls, send = _recorder()
    p = _state(
        tmp_path,
        tripped_since=(NOW - timedelta(days=10)).isoformat(),
        last_alert_at=(NOW - timedelta(days=4)).isoformat(),
    )
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=send)
    assert "EMAILED" in msg
    assert len(calls) == 1


def test_no_email_config_is_log_only(tmp_path):
    calls, send = _recorder()
    p = _state(tmp_path, tripped_since=(NOW - timedelta(days=8)).isoformat())
    msg = D.trip(now=NOW, state_path=p, config=NO_CFG, send_fn=send)
    assert "NO EMAIL CONFIG" in msg
    assert calls == []


def test_send_failure_does_not_raise_or_advance_state(tmp_path):
    def boom(**kwargs):
        raise RuntimeError("send helper failed (exit 1)")

    p = _state(tmp_path, tripped_since=(NOW - timedelta(days=8)).isoformat())
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=boom)
    assert "FAILED" in msg
    assert json.loads(p.read_text()).get("last_alert_at") is None  # retry next run


def test_clear_disarms(tmp_path):
    p = _state(tmp_path, tripped_since=NOW.isoformat(), last_alert_at=NOW.isoformat())
    msg = D.clear(state_path=p)
    assert "cleared" in msg
    state = json.loads(p.read_text())
    assert state["tripped_since"] is None
    assert state["last_alert_at"] is None


def test_clear_when_idle_is_noop(tmp_path):
    p = _state(tmp_path)
    assert D.clear(state_path=p) == "deadman: idle"
    assert not p.exists()  # never written for a no-op


def test_corrupt_state_treated_as_fresh(tmp_path):
    p = tmp_path / "deadman.json"
    p.write_text("{not json", encoding="utf-8")
    calls, send = _recorder()
    msg = D.trip(now=NOW, state_path=p, config=CFG, send_fn=send)
    assert "armed" in msg
    assert calls == []
