"""Acceptance tests for issue #262 — Claude transcript collector + activity-miner."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import usage_collector_claude as U  # noqa: E402

HOST = "testhost"


def _bash(cmd):
    return {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}


def _asst(
    uuid,
    *,
    ts,
    sid="s1",
    model="claude-opus-4",
    usage=None,
    content=None,
    gitBranch=None,
    cwd=None,
):
    return {
        "type": "assistant",
        "sessionId": sid,
        "uuid": uuid,
        "timestamp": ts,
        "gitBranch": gitBranch,
        "cwd": cwd,
        "message": {
            "role": "assistant",
            "model": model,
            "usage": usage or {"input_tokens": 100, "output_tokens": 50},
            "content": content or [],
        },
    }


def _extract(entries):
    return U.extract_records(entries, inference_host=HOST)


# 1. per-message timestamps, not one record at session start ----------------------------------------
def test_per_message_records_and_timestamps():
    recs = _extract(
        [
            _asst(1, ts="2026-04-01T00:00:00Z"),
            _asst(2, ts="2026-05-01T00:00:00Z"),
            _asst(3, ts="2026-06-01T00:00:00Z"),
        ]
    )
    assert len(recs) == 3
    assert [r["ts"] for r in recs] == [
        "2026-04-01T00:00:00Z",
        "2026-05-01T00:00:00Z",
        "2026-06-01T00:00:00Z",
    ]


# 2. git checkout -b → task on subsequent messages --------------------------------------------------
def test_checkout_sets_task_on_subsequent():
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                content=[_bash("git checkout -b feat/issue-42-foo origin/main")],
            ),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[0]["task"] == "unattributed"  # the issuing msg is pre-command
    assert recs[1]["task"] == "issue:42"  # subsequent msg gets it


# 3. ssh host 'cd repo' → work_host + project on subsequent ------------------------------------------
def test_ssh_sets_work_host_and_project():
    recs = _extract(
        [
            _asst(1, ts="t1", content=[_bash("ssh jns 'cd ~/agents && git status'")]),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[1]["work_host"] == "jns"
    assert recs[1]["project"] == "agents"


# 4. multi-task session: branch switch midway → segmentation ----------------------------------------
def test_multi_task_segmentation():
    recs = _extract(
        [
            _asst(1, ts="t1", content=[_bash("git checkout -b feat/issue-42-a")]),
            _asst(2, ts="t2"),
            _asst(3, ts="t3", content=[_bash("git checkout -b feat/issue-99-b")]),
            _asst(4, ts="t4"),
        ]
    )
    assert recs[1]["task"] == "issue:42"
    assert recs[3]["task"] == "issue:99"


# 5. no git/ssh activity → unattributed, work_host == inference_host ---------------------------------
def test_no_activity_unattributed():
    recs = _extract([_asst(1, ts="t1", gitBranch="main", cwd="/tmp/x")])
    assert recs[0]["task"] == "unattributed"
    assert recs[0]["work_host"] == HOST


# 6. gitBranch field → task without any command mining ----------------------------------------------
def test_gitbranch_fast_path():
    recs = _extract([_asst(1, ts="t1", gitBranch="feat/issue-7-foo")])
    assert recs[0]["task"] == "issue:7"


# 7. parallel sessions: independent, tokens sum, no cross-session bleed ------------------------------
def test_parallel_sessions_no_bleed():
    a = _extract(
        [
            _asst(
                1, ts="t1", sid="A", content=[_bash("git checkout -b feat/issue-1-a")]
            ),
            _asst(2, ts="t2", sid="A"),
        ]
    )
    b = _extract(
        [_asst(1, ts="t1", sid="B", usage={"input_tokens": 999, "output_tokens": 0})]
    )
    # session B's task is NOT polluted by A's checkout (separate transcripts)
    assert b[0]["task"] == "unattributed"
    assert b[0]["input"] == 999
    assert a[1]["task"] == "issue:1"  # A keeps its own attribution
    assert {r["session_id"] for r in a} == {"A"} and b[0]["session_id"] == "B"


# 8. unknown model → loud error, not a zero-cost record ---------------------------------------------
def test_unknown_model_raises():
    with pytest.raises(ValueError):
        _extract([_asst(1, ts="t1", model="gpt-99-unknown")])


# 8b. Claude Code internal <synthetic> model is SKIPPED, not crashed (real-transcript edge) ----------
def test_synthetic_model_skipped():
    recs = _extract(
        [
            _asst(1, ts="t1", model="<synthetic>"),  # injected/non-API → skipped
            _asst(2, ts="t2", model="claude-opus-4"),  # real → emitted
        ]
    )
    assert len(recs) == 1
    assert recs[0]["model"] == "claude-opus-4"


# 9. compaction flagged on the record with the cache_creation spike ---------------------------------
def test_compaction_flagged():
    recs = _extract(
        [
            _asst(1, ts="t1"),
            {"type": "summary", "isCompactSummary": True, "timestamp": "t2"},
            _asst(
                2,
                ts="t3",
                usage={"input_tokens": 10, "cache_creation_input_tokens": 200000},
            ),
        ]
    )
    by = {r["dedup_key"]: r for r in recs}
    assert by["s1:1"]["compaction"] is False
    assert by["s1:2"]["compaction"] is True
    assert by["s1:2"]["cache_creation"] == 200000


# 10. idempotent collect: running twice produces no duplicate shard records --------------------------
def test_idempotent_collect(tmp_path):
    proj = tmp_path / "projects" / "-proj-x"
    proj.mkdir(parents=True)
    (proj / "s1.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                _asst(1, ts="t1"),
                _asst(2, ts="t2"),
            ]
        )
    )
    shard = tmp_path / "telemetry" / HOST / "usage.jsonl"
    r1 = U.collect(tmp_path / "projects", shard, inference_host=HOST)
    r2 = U.collect(tmp_path / "projects", shard, inference_host=HOST)
    assert r1["written"] == 2
    assert r2["written"] == 0 and r2["skipped"] == 2
    assert len(shard.read_text().strip().splitlines()) == 2  # no duplicates


# Codex #262 hardening: SSH host parsing skips flags + their args -----------------------------------
def test_ssh_host_parsing_skips_flag_args():
    assert U.mine_command("ssh -p 22 jns 'cd ~/x'")["work_host"] == "jns"  # not "22"
    assert U.mine_command("ssh -i ~/.ssh/key deploy@server")["work_host"] == "server"
    assert U.mine_command("ssh -v jns")["work_host"] == "jns"
    # combined short flags where the last takes an arg (Codex #262 re-review)
    assert U.mine_command("ssh -vp 22 jns")["work_host"] == "jns"  # not "22"
    assert (
        U.mine_command("ssh -p22 jns")["work_host"] == "jns"
    )  # inline value, no next-token skip


# Codex #262: gitBranch is ground-truth per message → natural subsequent-message boundary ------------
def test_gitbranch_gives_subsequent_boundary():
    # the checkout message still shows the OLD branch; the next shows the new one
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                gitBranch="main",
                content=[_bash("git checkout -b feat/issue-5-x")],
            ),
            _asst(2, ts="t2", gitBranch="feat/issue-5-x"),
        ]
    )
    assert recs[0]["task"] == "unattributed"  # old branch (main) → not the new task
    assert recs[1]["task"] == "issue:5"  # new branch on the subsequent message


# Codex #262: malformed records don't crash + don't collapse on missing uuid ------------------------
def test_malformed_and_missing_uuid_robust():
    # non-dict message must not crash
    entries = [{"type": "assistant", "message": "oops-not-a-dict", "timestamp": "t0"}]
    assert _extract(entries) == []
    # two usage records missing uuid → distinct dedup_keys (no collapse/undercount)
    e1 = _asst(None, ts="t1", usage={"input_tokens": 1, "output_tokens": 0})
    e2 = _asst(None, ts="t2", usage={"input_tokens": 2, "output_tokens": 0})
    for e in (e1, e2):
        e["uuid"] = None
    recs = _extract([e1, e2])
    assert len(recs) == 2
    assert recs[0]["dedup_key"] != recs[1]["dedup_key"]


# 11. emitted record carries the §3 schema fields --------------------------------------------------
def test_record_schema():
    rec = _extract([_asst(1, ts="t1")])[0]
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
    assert rec["provider"] == "claude"
    assert rec["account"] is None and rec["billing_type"] is None  # filled by #265
    assert rec["cost_usd"] > 0
