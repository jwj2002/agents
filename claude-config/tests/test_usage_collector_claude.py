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


# --- Issue #311: cross-repo attribution via --repo and git -C -----------------------------------


# Test A — `gh --repo owner/name` sets project on subsequent message
def test_gh_repo_flag_sets_project():
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                content=[_bash("gh pr merge 99 --repo jwj2002/agents --squash")],
            ),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[0]["project"] is None  # issuing message: pre-command
    assert recs[1]["project"] == "agents"
    assert recs[1]["task"] == "unattributed"  # no branch → task still unattributed


# Test B — `git -C <abs-path>` sets project on subsequent message
def test_git_dash_c_sets_project():
    recs = _extract(
        [
            _asst(1, ts="t1", content=[_bash("git -C /Users/jjob/agents status")]),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[1]["project"] == "agents"


# Test C — `git -C $R` (shell variable) does NOT set project (no mis-attribution)
def test_git_dash_c_shell_var_ignored():
    recs = _extract(
        [
            _asst(1, ts="t1", content=[_bash("git -C $R log --oneline")]),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[1]["project"] is None


# Test D — `git -C <path> checkout -b feat/issue-N-foo` sets BOTH project AND task
def test_git_dash_c_checkout_sets_project_and_task():
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                content=[
                    _bash("git -C ~/agents checkout -b feat/issue-311-attr origin/main")
                ],
            ),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[1]["project"] == "agents"
    assert recs[1]["task"] == "issue:311"


# Test E — conflicting --repo and git -C in same command → stays unattributed (precision over recall)
def test_conflicting_signals_no_project():
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                content=[_bash("git -C /path/to/repo-a status --repo owner/repo-b")],
            ),
            _asst(2, ts="t2"),
        ]
    )
    # conflicting signals → project remains None (precision over recall)
    assert recs[1]["project"] is None


# Test F — no cross-repo signal → stays unattributed, never mis-attributed
def test_no_cross_repo_signal_stays_unattributed():
    recs = _extract(
        [
            _asst(1, ts="t1", content=[_bash("echo hello")]),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[1]["task"] == "unattributed"
    assert recs[1]["project"] is None


# Test G — `cd` takes precedence over `--repo` flag on the same command
def test_cd_takes_precedence_over_repo_flag():
    # cd /Users/.../agents in command wins over a stray --repo flag
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                content=[
                    _bash("cd /Users/jjob/agents && gh pr create --title x --body y")
                ],
            ),
            _asst(2, ts="t2"),
        ]
    )
    assert recs[1]["project"] == "agents"


# Test G2 — `--repo` pointing to a DIFFERENT repo does NOT override `cd`-established project
def test_cd_beats_conflicting_repo_flag():
    # cd sets agents; --repo points to maison-scaffold; cd wins (precision over recall)
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                content=[
                    _bash(
                        "cd /Users/jjob/agents && gh pr create --repo jwj2002/maison-scaffold --title x"
                    )
                ],
            ),
            _asst(2, ts="t2"),
        ]
    )
    # cd fires first → project = "agents"; --repo block is skipped ("project" already in out)
    assert recs[1]["project"] == "agents"


# Test H — AC4: the feature REDUCES project-unattributed. Demonstrated by a counterfactual
# (identical sessions WITH vs WITHOUT a `--repo` signal — the with-signal run has fewer
# project=None records), plus an honest per-run outcome from collect() (attributed + unattributed
# = written). We do NOT diff the append-only shard total, which only grows.
def test_collect_repo_target_reduces_unattributed(tmp_path):
    # Counterfactual. WITHOUT a repo signal: no cwd repo → every record stays project=None.
    without = list(
        U.extract_records([_asst(1, ts="t1"), _asst(2, ts="t2")], inference_host=HOST)
    )
    # WITH a `--repo` signal in msg1: the subsequent message gains project=agents.
    with_signal = list(
        U.extract_records(
            [
                _asst(
                    1, ts="t1", content=[_bash("gh pr merge 1 --repo jwj2002/agents")]
                ),
                _asst(2, ts="t2"),
            ],
            inference_host=HOST,
        )
    )
    none_without = sum(1 for r in without if r.get("project") is None)
    none_with = sum(1 for r in with_signal if r.get("project") is None)
    assert none_with < none_without  # the mined --repo rescued at least one record

    # collect() reports the run's honest attribution outcome (no append-only shard diff).
    proj = tmp_path / "projects" / "-proj-x"
    proj.mkdir(parents=True)
    shard = tmp_path / "telemetry" / HOST / "usage.jsonl"
    (proj / "s1.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                _asst(
                    1, ts="t1", content=[_bash("gh pr merge 1 --repo jwj2002/agents")]
                ),
                _asst(2, ts="t2"),  # gets project=agents from the mined signal
            ]
        )
    )
    result = U.collect(tmp_path / "projects", shard, inference_host=HOST)
    assert (
        result["project_attributed"] + result["project_unattributed"]
        == result["written"]
    )
    assert (
        result["project_attributed"] >= 1
    )  # the mined --repo attributed at least one record
    # Also confirm msg3 is the attributed one: read the shard
    records = [
        json.loads(line) for line in shard.read_text().splitlines() if line.strip()
    ]
    new_records = [r for r in records if r.get("dedup_key", "").startswith("s1:")]
    attributed = [r for r in new_records if r.get("project") == "agents"]
    assert len(attributed) >= 1  # at least msg3 got project=agents


# mine_command unit tests for AC compliance
def test_mine_command_gh_repo():
    assert (
        U.mine_command("gh pr merge 99 --repo jwj2002/agents --squash")["project"]
        == "agents"
    )


def test_mine_command_git_dash_c_abs():
    assert U.mine_command("git -C /Users/jjob/agents status")["project"] == "agents"


def test_mine_command_git_dash_c_shell_var():
    assert "project" not in U.mine_command("git -C $R log")


def test_mine_command_git_dash_c_checkout():
    result = U.mine_command("git -C ~/agents checkout -b feat/issue-311-foo")
    assert result["project"] == "agents"
    assert result["task"] == "issue:311"


def test_mine_command_conflicting_signals():
    result = U.mine_command("git -C /path/to/repo-a status --repo owner/repo-b")
    assert result.get("project") is None or "project" not in result


# AC3 precision: per-message cwd-vs-mined precedence tests (issue #311 fix 2)


# Test I — hijack prevention: cwd=agents + stray --repo in earlier message → later msgs stay project=agents
def test_cwd_repo_beats_stray_mined_project():
    """A real-cwd session (cwd=/Users/jjob/agents) must not be hijacked by a stray --repo flag.
    After msg1 mines project=maison-scaffold, msg2 has cwd=agents → must get project=agents (cwd wins)."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/jjob/agents",
                content=[_bash("gh pr view 99 --repo jwj2002/maison-scaffold")],
            ),
            _asst(2, ts="t2", cwd="/Users/jjob/agents"),
        ]
    )
    # msg1: pre-command, cwd=agents → project=agents (cwd wins over nothing mined yet)
    assert recs[0]["project"] == "agents"
    # msg2: active["project"] is now "maison-scaffold" from mining msg1, but cwd=agents → cwd wins
    assert recs[1]["project"] == "agents"


# Test J — #311 target: cwd=None (no repo) + --repo signal → project from mined signal
def test_scratch_cwd_uses_mined_project():
    """The primary #311 target: cwd is absent (simulates abs-path-outside-any-repo session).
    cwd yields None → mined active["project"] fills the gap (the #311 win)."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd=None,
                content=[_bash("gh pr merge 5 --repo jwj2002/agents --squash")],
            ),
            _asst(2, ts="t2", cwd=None),
        ]
    )
    # msg1: no cwd → project=None (pre-command, nothing mined yet)
    assert recs[0]["project"] is None
    # msg2: no cwd → cwd_project=None → falls back to mined active["project"] = "agents"
    assert recs[1]["project"] == "agents"


# Test K — ssh-develop regression: ssh-derived project still wins when work_host != inference_host
def test_ssh_develop_project_attribution_not_regressed():
    """SSH-develop (§4.2): when ssh sets work_host to a remote, active["project"] (mined from ssh
    'cd repo') must still win for subsequent messages — even though cwd is local."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/jjob",  # local cwd — irrelevant under ssh-develop
                content=[_bash("ssh jns 'cd ~/app-repos/app-buddy && git status'")],
            ),
            _asst(2, ts="t2", cwd="/Users/jjob"),  # still local cwd after ssh
        ]
    )
    # msg1: pre-command, cwd=/Users/jjob → _project_from_path gives "jjob"; work_host still HOST
    # so on_remote is False for msg1 → cwd wins → project="jjob"
    assert recs[0]["project"] == "jjob"
    # msg2: after ssh, work_host="jns" (≠ HOST) → on_remote=True → ssh-mined active["project"]
    # wins. ssh 'cd ~/app-repos/app-buddy' → mine_command sets project="app-buddy" via cd.
    assert recs[1]["work_host"] == "jns"
    assert recs[1]["project"] == "app-buddy"
