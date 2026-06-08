"""Acceptance tests for issue #321 — metered billing-type helper (cost-telemetry-v0 §D7)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_billing as B  # noqa: E402


def _claude_json(tmp_path, obj) -> Path:
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_env_anthropic_key_beats_oauth(tmp_path):
    # an API key in env → metered even when a subscription oauthAccount exists
    cj = _claude_json(tmp_path, {"oauthAccount": {"billingType": "max"}})
    assert B.resolve_billing_type({"ANTHROPIC_API_KEY": "sk-x"}, cj) == "metered"


def test_env_openai_key_metered(tmp_path):
    cj = _claude_json(tmp_path, {"oauthAccount": {"billingType": "pro"}})
    assert B.resolve_billing_type({"OPENAI_API_KEY": "sk-o"}, cj) == "metered"


def test_subscription_oauth_no_key(tmp_path):
    cj = _claude_json(tmp_path, {"oauthAccount": {"billingType": "max"}})
    assert B.resolve_billing_type({}, cj) == "subscription"


def test_oauth_no_billingtype_is_subscription(tmp_path):
    # an OAuth login without an explicit metered plan → subscription
    cj = _claude_json(tmp_path, {"oauthAccount": {"emailAddress": "x@y.com"}})
    assert B.resolve_billing_type({}, cj) == "subscription"


def test_console_oauth_is_metered(tmp_path):
    cj = _claude_json(tmp_path, {"oauthAccount": {"billingType": "console"}})
    assert B.resolve_billing_type({}, cj) == "metered"


def test_malformed_json_unknown(tmp_path):
    p = tmp_path / ".claude.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert B.resolve_billing_type({}, p) == "unknown"


def test_missing_file_unknown(tmp_path):
    assert B.resolve_billing_type({}, tmp_path / "nope.json") == "unknown"


def test_no_oauth_account_unknown(tmp_path):
    cj = _claude_json(tmp_path, {"someOtherKey": 1})
    assert B.resolve_billing_type({}, cj) == "unknown"


def test_non_dict_json_unknown(tmp_path):
    p = tmp_path / ".claude.json"
    p.write_text('"a string"', encoding="utf-8")
    assert B.resolve_billing_type({}, p) == "unknown"
