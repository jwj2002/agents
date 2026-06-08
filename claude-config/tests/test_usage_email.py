"""Acceptance tests for issue #326 — weekly email delivery (cost-telemetry-v0 §D5).

No live send: the M365 helper is mocked via the injectable send_fn. Activation/first real send is deferred.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_email as E  # noqa: E402

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _recorder():
    calls = []

    def send_fn(**kw):
        calls.append(kw)

    return calls, send_fn


def test_first_send_of_week_calls_sender_and_updates_state():
    calls, send_fn = _recorder()
    code, state = E.send_weekly(
        md_summary="# report",
        html_path="/tmp/r.html",
        state={},
        host="jns-mac",
        now=NOW,
        send_fn=send_fn,
    )
    assert code == 0
    assert len(calls) == 1
    assert calls[0]["recipient"] == E.SENDER  # never overrides sender
    assert calls[0]["html_path"] == "/tmp/r.html"
    assert calls[0]["body"] == "# report"
    assert "jns-mac" in calls[0]["subject"]
    assert state["last_email_sent_week"] == E._week_key(NOW)


def test_idempotent_no_double_send_same_week():
    calls, send_fn = _recorder()
    prior = {"last_email_sent_week": E._week_key(NOW)}
    code, state = E.send_weekly(
        md_summary="x",
        html_path=None,
        state=prior,
        host="h",
        now=NOW,
        send_fn=send_fn,
    )
    assert code == 0
    assert calls == []  # NOT called — already sent this week
    assert state == prior


def test_send_failure_returns_4_and_does_not_advance_state():
    def boom(**kw):
        raise RuntimeError("graph down")

    code, state = E.send_weekly(
        md_summary="x",
        html_path=None,
        state={},
        host="h",
        now=NOW,
        send_fn=boom,
    )
    assert code == 4
    assert "last_email_sent_week" not in state  # not advanced → retried next run


def test_next_week_sends_again():
    calls, send_fn = _recorder()
    later = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)  # a different ISO week
    prior = {"last_email_sent_week": E._week_key(NOW)}
    code, state = E.send_weekly(
        md_summary="x",
        html_path=None,
        state=prior,
        host="h",
        now=later,
        send_fn=send_fn,
    )
    assert code == 0 and len(calls) == 1
    assert state["last_email_sent_week"] == E._week_key(later)


def test_refuses_nonstandard_recipient_unless_opted_in():
    # #339: the report carries internal cost data — refuse any non-SENDER recipient by default.
    calls, send_fn = _recorder()
    code, _ = E.send_weekly(
        md_summary="x", html_path=None, state={}, host="h",
        recipient="evil@example.com", now=NOW, send_fn=send_fn,
    )
    assert code == 4 and calls == []  # refused, nothing sent
    code2, _ = E.send_weekly(
        md_summary="x", html_path=None, state={}, host="h",
        recipient="evil@example.com", allow_nonstandard_recipient=True, now=NOW, send_fn=send_fn,
    )
    assert code2 == 0 and len(calls) == 1  # explicit dev opt-in allows it
