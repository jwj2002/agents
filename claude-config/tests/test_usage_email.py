"""Tests for the per-machine email config + transport layer (usage_email).

No live send: the transport is mocked via the injectable send_fn. Config is
passed explicitly (or via a temp file) so tests never touch the real machine config.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_email as E  # noqa: E402

NOW = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
GMAIL_CFG = {
    "enabled": True,
    "account": {"type": "gmail", "sender": "me@gmail.com", "creds": "~/agents/google/token.json"},
    "recipient": "me@gmail.com",
}


def _recorder():
    calls = []

    def send_fn(**kw):
        calls.append(kw)

    return calls, send_fn


# ---- send_weekly contract -------------------------------------------------

def test_first_send_of_week_calls_transport_and_updates_state():
    calls, send_fn = _recorder()
    code, state = E.send_weekly(
        md_summary="# report", html_path="/tmp/r.html", state={}, host="jns-mac",
        config=GMAIL_CFG, now=NOW, send_fn=send_fn,
    )
    assert code == E.SENT_OR_SKIP
    assert len(calls) == 1
    assert calls[0]["recipient"] == "me@gmail.com"        # from config
    assert calls[0]["account"]["type"] == "gmail"          # transport passed through
    assert calls[0]["html_path"] == "/tmp/r.html"
    assert calls[0]["body"] == "# report"
    assert "jns-mac" in calls[0]["subject"]
    assert state["last_email_sent_week"] == E._week_key(NOW)


def test_idempotent_no_double_send_same_week():
    calls, send_fn = _recorder()
    prior = {"last_email_sent_week": E._week_key(NOW)}
    code, state = E.send_weekly(
        md_summary="x", html_path=None, state=prior, host="h",
        config=GMAIL_CFG, now=NOW, send_fn=send_fn,
    )
    assert code == E.SENT_OR_SKIP and calls == [] and state == prior


def test_next_week_sends_again():
    calls, send_fn = _recorder()
    later = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    prior = {"last_email_sent_week": E._week_key(NOW)}
    code, state = E.send_weekly(
        md_summary="x", html_path=None, state=prior, host="h",
        config=GMAIL_CFG, now=later, send_fn=send_fn,
    )
    assert code == E.SENT_OR_SKIP and len(calls) == 1
    assert state["last_email_sent_week"] == E._week_key(later)


def test_send_failure_returns_4_and_does_not_advance_state():
    def boom(**kw):
        raise RuntimeError("transport down")
    code, state = E.send_weekly(
        md_summary="x", html_path=None, state={}, host="h",
        config=GMAIL_CFG, now=NOW, send_fn=boom,
    )
    assert code == E.SEND_FAILED and "last_email_sent_week" not in state


def test_disabled_config_does_not_send():
    calls, send_fn = _recorder()
    for cfg in ({"enabled": False}, {"enabled": True, "recipient": "", "account": {"type": "gmail"}},
                {"enabled": True, "recipient": "x@y.z", "account": {"type": "none"}}):
        code, state = E.send_weekly(
            md_summary="x", html_path=None, state={}, host="h",
            config=cfg, now=NOW, send_fn=send_fn,
        )
        assert code == E.DISABLED, cfg
    assert calls == []  # nothing sent in any disabled shape


# ---- config loader --------------------------------------------------------

def test_load_config_absent_is_disabled(tmp_path):
    assert E.load_email_config(tmp_path / "nope.json") == {"enabled": False}


def test_load_config_malformed_is_disabled(tmp_path):
    p = tmp_path / "email.json"
    p.write_text("{not json")
    assert E.load_email_config(p) == {"enabled": False}


def test_load_config_valid(tmp_path):
    p = tmp_path / "email.json"
    p.write_text(json.dumps(GMAIL_CFG))
    cfg = E.load_email_config(p)
    assert cfg["enabled"] and cfg["recipient"] == "me@gmail.com"
    assert cfg["account"]["type"] == "gmail"


# ---- transport argv resolution -------------------------------------------

def test_helper_argv_gmail_uses_token_and_stdin_body():
    cmd = E._helper_argv(
        {"type": "gmail", "creds": "~/agents/google/token.json"},
        recipient="me@gmail.com", subject="s", html_path="/tmp/r.html",
    )
    assert str(E.GMAIL_HELPER) in cmd
    assert "--token" in cmd and "--to" in cmd and "--attach" in cmd
    assert "--creds" not in cmd
    assert cmd[cmd.index("--body") + 1] == "-"      # body via stdin, not argv


def test_helper_argv_m365_uses_creds_and_bodyfile():
    cmd = E._helper_argv(
        {"type": "m365", "creds": "~/.claude/m365/agent.json"},
        recipient="x@vital.com", subject="s", html_path=None, body_file="/tmp/body.md",
    )
    assert str(E.M365_HELPER) in cmd
    assert "--creds" in cmd and "--token" not in cmd
    assert "--attach" not in cmd                     # no html → no attach
    assert cmd[cmd.index("--body-file") + 1] == "/tmp/body.md"  # body via file, not argv


def test_helper_argv_none_is_unsendable():
    assert E._helper_argv({"type": "none"}, recipient="x", subject="s", html_path=None) is None
    assert E._helper_argv({}, recipient="x", subject="s", html_path=None) is None
