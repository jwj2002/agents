"""Acceptance tests for issue #263 — Codex/ChatGPT session collector (§4.6)."""

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_collector_codex as X  # noqa: E402

HOST = "testhost"


def _meta(sid="sess1", cwd="/home/user/agents", git=None, model="gpt-5.5", ts="t0"):
    return {
        "timestamp": ts,
        "payload": {
            "id": sid,
            "cwd": cwd,
            "git": git,
            "model": model,
            "model_provider": "openai",
        },
    }


def _tc(last, ts="t1"):
    total = {
        **last,
        "total_tokens": last.get("input_tokens", 0) + last.get("output_tokens", 0),
    }
    return {
        "timestamp": ts,
        "payload": {
            "type": "token_count",
            "info": {"last_token_usage": last, "total_token_usage": total},
        },
    }


def _fn(cmd, ts="t1"):
    return {
        "timestamp": ts,
        "payload": {
            "type": "function_call",
            "name": "shell",
            "arguments": json.dumps({"command": ["bash", "-lc", cmd]}),
        },
    }


def _extract(entries, account_info=None):
    return X.extract_records(entries, inference_host=HOST, account_info=account_info)


# one record per token_count, correct token mapping ------------------------------------------------
def test_per_turn_records_and_token_mapping():
    recs = _extract(
        [
            _meta(),
            _tc(
                {
                    "input_tokens": 1000,
                    "cached_input_tokens": 200,
                    "output_tokens": 100,
                    "reasoning_output_tokens": 50,
                }
            ),
            _tc(
                {
                    "input_tokens": 500,
                    "cached_input_tokens": 0,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 0,
                }
            ),
        ]
    )
    assert len(recs) == 2
    # fresh input = input - cached; output += reasoning; cache_read = cached; no cache_creation
    assert (
        recs[0]["input"] == 800
        and recs[0]["cache_read"] == 200
        and recs[0]["output"] == 150
    )
    assert recs[0]["cache_creation"] == 0
    assert recs[1]["input"] == 500 and recs[1]["output"] == 30
    assert all(r["provider"] == "codex" and r["cost_usd"] > 0 for r in recs)


# cwd → project ------------------------------------------------------------------------------------
def test_cwd_project():
    recs = _extract(
        [
            _meta(cwd="/home/user/agents", git=None),
            _tc({"input_tokens": 10, "output_tokens": 1}),
        ]
    )
    assert recs[0]["project"] == "agents"


# git block: branch → task, repo url → project -----------------------------------------------------
def test_git_block_task_and_project():
    git = {
        "branch": "fix/issue-1812-x",
        "repository_url": "https://github.com/jwj2002/meeting-buddy.git",
    }
    recs = _extract([_meta(git=git), _tc({"input_tokens": 10, "output_tokens": 1})])
    assert recs[0]["task"] == "issue:1812"
    assert recs[0]["project"] == "meeting-buddy"


# function_call git checkout → task ----------------------------------------------------------------
def test_function_call_checkout_task():
    recs = _extract(
        [
            _meta(git=None, cwd="/x"),
            _fn("git checkout -b feat/issue-55-y"),
            _tc({"input_tokens": 10, "output_tokens": 1}),
        ]
    )
    assert recs[0]["task"] == "issue:55"


# account from auth.json, key NEVER in output ------------------------------------------------------
def test_account_from_auth_no_key_leak(tmp_path):
    claims = (
        base64.urlsafe_b64encode(json.dumps({"email": "u@example.com"}).encode())
        .decode()
        .rstrip("=")
    )
    jwt = f"h.{claims}.sig"
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "OPENAI_API_KEY": "sk-SECRET-MUST-NOT-LEAK",
                "tokens": {"account_id": "b00eXXXX", "id_token": jwt},
            }
        )
    )
    info = X.read_codex_account(auth)
    assert info["account"] == "b00eXXXX"
    assert info["email"] == "u@example.com"
    assert info["billing_type"] == "subscription"
    recs = _extract(
        [_meta(), _tc({"input_tokens": 10, "output_tokens": 1})], account_info=info
    )
    blob = json.dumps(recs)
    assert (
        "sk-SECRET-MUST-NOT-LEAK" not in blob
    )  # the auth key never reaches a shard record
    assert (
        recs[0]["account"] == "b00eXXXX" and recs[0]["billing_type"] == "subscription"
    )
    # API-key-only auth → metered
    auth2 = tmp_path / "auth2.json"
    auth2.write_text(json.dumps({"OPENAI_API_KEY": "sk-x"}))
    assert X.read_codex_account(auth2)["billing_type"] == "metered"


# unknown model → loud error -----------------------------------------------------------------------
def test_unknown_model_raises():
    with pytest.raises(ValueError):
        _extract(
            [
                _meta(model="gpt-99-unknown"),
                _tc({"input_tokens": 10, "output_tokens": 1}),
            ]
        )


# mixed shard: codex + claude records, provider distinguishes --------------------------------------
def test_mixed_shard_provider_field(tmp_path):
    shard = tmp_path / "telemetry" / HOST / "usage.jsonl"
    shard.parent.mkdir(parents=True)
    # a claude record already in the shard
    shard.write_text(
        json.dumps({"provider": "claude", "dedup_key": "s:1", "model": "claude-opus-4"})
        + "\n"
    )
    sess = tmp_path / "sessions" / "2026" / "06"
    sess.mkdir(parents=True)
    (sess / "r1.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in [_meta(), _tc({"input_tokens": 10, "output_tokens": 1})]
        )
    )
    X.collect(
        tmp_path / "sessions",
        shard,
        inference_host=HOST,
        auth_path=tmp_path / "none.json",
    )
    providers = {
        json.loads(line)["provider"]
        for line in shard.read_text().splitlines()
        if line.strip()
    }
    assert providers == {"claude", "codex"}


# bridge vs local: same account, inference_host separates ------------------------------------------
def test_inference_host_separates_same_account():
    acct = {"account": "b00e", "email": None, "billing_type": "subscription"}
    server = X.extract_records(
        [_meta(sid="srv"), _tc({"input_tokens": 10, "output_tokens": 1})],
        inference_host="jns-server",
        account_info=acct,
    )
    mac = X.extract_records(
        [_meta(sid="mac"), _tc({"input_tokens": 10, "output_tokens": 1})],
        inference_host="jns-mac",
        account_info=acct,
    )
    assert server[0]["account"] == mac[0]["account"] == "b00e"  # one account
    assert (
        server[0]["inference_host"] != mac[0]["inference_host"]
    )  # host is the separator


# idempotent collect -------------------------------------------------------------------------------
def test_idempotent_collect(tmp_path):
    sess = tmp_path / "sessions" / "2026"
    sess.mkdir(parents=True)
    (sess / "r.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                _meta(),
                _tc({"input_tokens": 10, "output_tokens": 1}),
                _tc({"input_tokens": 5, "output_tokens": 1}),
            ]
        )
    )
    shard = tmp_path / "telemetry" / HOST / "usage.jsonl"
    r1 = X.collect(
        tmp_path / "sessions",
        shard,
        inference_host=HOST,
        auth_path=tmp_path / "no.json",
    )
    r2 = X.collect(
        tmp_path / "sessions",
        shard,
        inference_host=HOST,
        auth_path=tmp_path / "no.json",
    )
    assert r1["written"] == 2 and r2["written"] == 0 and r2["skipped"] == 2
    assert len(shard.read_text().strip().splitlines()) == 2


# Codex #263 hardening: malformed payloads don't crash; missing session_id doesn't collide ----------
def test_malformed_payloads_robust():
    # non-dict info, non-numeric token values, missing session id → no crash
    entries = [
        _meta(sid=None),
        {
            "timestamp": "t1",
            "payload": {"type": "token_count", "info": "bad-not-a-dict"},
        },
        {
            "timestamp": "t2",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": "oops",
                        "output_tokens": [1, 2],
                    }
                },
            },
        },
        _tc({"input_tokens": 10, "output_tokens": 1}, ts="t3"),
        _tc({"input_tokens": 20, "output_tokens": 2}, ts="t4"),
    ]
    recs = X.extract_records(entries, inference_host=HOST)
    # the non-dict info is skipped; the non-numeric one coerces to 0; the two valid ones emit
    assert len(recs) == 3
    bad = next(r for r in recs if r["ts"] == "t2")
    assert bad["input"] == 0 and bad["output"] == 0  # coerced, not crashed
    # missing session_id → distinct dedup_keys (no collision/data-loss)
    keys = [r["dedup_key"] for r in recs]
    assert len(set(keys)) == len(keys)


# schema fields present ----------------------------------------------------------------------------
def test_record_schema():
    rec = _extract([_meta(), _tc({"input_tokens": 10, "output_tokens": 1})])[0]
    for f in (
        "provider",
        "account",
        "billing_type",
        "inference_host",
        "work_host",
        "project",
        "model",
        "task",
        "input",
        "output",
        "cache_read",
        "cache_creation",
        "cost_usd",
        "ts",
        "session_id",
    ):
        assert f in rec, f
