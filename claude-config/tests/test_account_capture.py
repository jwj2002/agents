"""Acceptance tests for issue #265 — account capture hook + collector join (§4.1)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import usage_account_capture as H  # noqa: E402
import usage_collector_claude as U  # noqa: E402

OAUTH = {
    "accountUuid": "87a-uuid",
    "organizationName": "Jason's Org",
    "organizationUuid": "org-uuid",
    "emailAddress": "jas@example.com",
    "billingType": "subscription",
    "seatTier": "max",
}
SECRET = "oauth-token-SHOULD-NOT-LEAK"


def _claude_json(tmp_path, oauth=OAUTH, secret=True):
    d = {"oauthAccount": dict(oauth), "userID": "u1"}
    if secret:
        d["oauthAccount"]["accessToken"] = (
            SECRET  # a secret field that must NOT be copied
        )
    p = tmp_path / "claude.json"
    p.write_text(json.dumps(d))
    return p


# Hook: build_entry copies the identity fields, classifies billing, and leaks NO secret --------------
def test_hook_build_entry(tmp_path):
    entry = H.build_entry(
        _claude_json(tmp_path), "sess-1", now_ts="2026-06-06T00:00:00Z"
    )
    assert entry["session_id"] == "sess-1"
    assert entry["account_uuid"] == "87a-uuid"
    assert entry["org"] == "Jason's Org"
    assert entry["email"] == "jas@example.com"
    assert entry["billing_type"] == "subscription"
    assert SECRET not in json.dumps(entry)  # the auth token never reaches the sidecar


def test_hook_classify_billing():
    assert H.classify_billing("subscription") == "subscription"
    assert H.classify_billing("max") == "subscription"
    assert H.classify_billing("console") == "metered"
    assert H.classify_billing("api") == "metered"
    assert H.classify_billing(None) is None


def test_hook_append_then_load_roundtrip(tmp_path):
    sidecar = tmp_path / "account-map.jsonl"
    H.append_entry(sidecar, H.build_entry(_claude_json(tmp_path), "sess-9", now_ts="t"))
    amap = U.load_account_map(sidecar)
    assert amap["sess-9"]["account_uuid"] == "87a-uuid"


# Collector join: sidecar entry → account fields on the record --------------------------------------
def _rec(sid):
    return {"session_id": sid, "account": None, "billing_type": None}


def test_join_from_sidecar():
    amap = {
        "sX": {
            "account_uuid": "87a",
            "org": "O",
            "email": "e",
            "billing_type": "subscription",
        }
    }
    rec = U._apply_account(_rec("sX"), amap, None)
    assert rec["account"] == "87a" and rec["billing_type"] == "subscription"
    assert rec["account_source"] == "sidecar"


def test_join_fallback_not_unknown():
    fb = {
        "account_uuid": "cur",
        "billing_type": "metered",
        "account_source": "current_fallback",
    }
    rec = U._apply_account(_rec("missing"), {}, fb)
    assert rec["account"] == "cur"  # current-account fallback, NOT unknown
    assert rec["account_source"] == "current_fallback"


def test_current_account_missing_file_is_unknown(tmp_path):
    fb = U.current_account(tmp_path / "does-not-exist.json")
    assert fb["account_uuid"] == "unknown"
    rec = U._apply_account(_rec("s"), {}, fb)
    assert rec["account"] == "unknown"  # only when ~/.claude.json is absent


def test_current_account_reads_billing(tmp_path):
    fb = U.current_account(_claude_json(tmp_path))
    assert fb["account_uuid"] == "87a-uuid" and fb["billing_type"] == "subscription"


# Codex #265 robustness: malformed shapes don't crash; unknown only when ABSENT --------------------
def test_malformed_shapes_robust(tmp_path):
    # non-object claude.json → hook no-crash, empty fields
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]")
    e = H.build_entry(bad, "s", now_ts="t")
    assert e["account_uuid"] is None and e["session_id"] == "s"
    # non-object oauthAccount → no crash
    bad2 = tmp_path / "bad2.json"
    bad2.write_text(json.dumps({"oauthAccount": "not-an-object"}))
    assert H.build_entry(bad2, "s", now_ts="t")["account_uuid"] is None
    # malformed sidecar lines ignored, not crashed
    sc = tmp_path / "sc.jsonl"
    sc.write_text(
        '[1,2]\n"a string"\nnull\n'
        + json.dumps({"session_id": "ok", "account_uuid": "u"})
        + "\n"
    )
    amap = U.load_account_map(sc)
    assert list(amap) == ["ok"]
    # absent file → unknown; UNPARSEABLE file → unreadable (NOT unknown); valid-JSON-non-object → no crash
    assert U.current_account(tmp_path / "absent.json")["account_source"] == "unknown"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not valid json")
    assert U.current_account(malformed)["account_source"] == "unreadable"
    assert U.current_account(malformed)["account_uuid"] is None
    # valid JSON but a non-object (list) → readable fallback with empty account, no crash
    assert U.current_account(bad)["account_uuid"] is None


# Codex billing_type classification (lives in #263; verified here per the AC) ------------------------
def test_codex_billing_classification(tmp_path):
    import usage_collector_codex as X

    sub = tmp_path / "a1.json"
    sub.write_text(json.dumps({"tokens": {"account_id": "b00e"}}))
    assert X.read_codex_account(sub)["billing_type"] == "subscription"
    api = tmp_path / "a2.json"
    api.write_text(json.dumps({"OPENAI_API_KEY": "sk-x"}))
    assert X.read_codex_account(api)["billing_type"] == "metered"


# Integration: hook captures → collector joins → record has account + billing_type -------------------
def test_integration_hook_then_collect(tmp_path):
    # capture
    sidecar = tmp_path / "telemetry" / "account-map.jsonl"
    H.append_entry(sidecar, H.build_entry(_claude_json(tmp_path), "sessZ", now_ts="t0"))
    # a transcript for that session
    proj = tmp_path / "projects" / "-p"
    proj.mkdir(parents=True)
    msg = {
        "type": "assistant",
        "sessionId": "sessZ",
        "uuid": "u1",
        "timestamp": "t1",
        "message": {
            "role": "assistant",
            "model": "claude-opus-4",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "content": [],
        },
    }
    (proj / "sessZ.jsonl").write_text(json.dumps(msg))
    shard = tmp_path / "telemetry" / "host" / "usage.jsonl"
    U.collect(
        tmp_path / "projects",
        shard,
        inference_host="host",
        sidecar_path=sidecar,
        claude_json_path=_claude_json(tmp_path),
    )
    rec = json.loads(shard.read_text().strip().splitlines()[0])
    assert rec["account"] == "87a-uuid"
    assert rec["billing_type"] == "subscription"
    assert rec["account_source"] == "sidecar"
