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


# Test E — tokenized parsing: `--repo` in a `git` command is NOT a gh signal; only `-C` fires
def test_conflicting_signals_no_project():
    # With tokenized parsing: `git -C /path/to/repo-a status --repo owner/repo-b` is a `git`
    # invocation.  Only `-C /path/to/repo-a` fires (tokenized git-C match requires toks[0]=="git").
    # `--repo owner/repo-b` requires toks[0]=="gh" to fire → it doesn't.
    # Result: project = "repo-a" (no conflict — the `--repo` is ignored in a git context).
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
    assert (
        recs[1]["project"] == "repo-a"
    )  # only git -C fires; --repo in git context is ignored


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
    # With tokenized parsing, `--repo` in a `git` command is NOT a gh signal.
    # Only `git -C /path/to/repo-a` fires → project = "repo-a".
    result = U.mine_command("git -C /path/to/repo-a status --repo owner/repo-b")
    assert result.get("project") == "repo-a"


# AC3 precision: per-message cwd-vs-mined precedence tests (issue #311 fix 2)


# Test I — hijack prevention: gitBranch present → real repo → stray --repo cannot override
def test_cwd_repo_beats_stray_mined_project():
    """A real-cwd session must not be hijacked by a stray --repo flag.
    gitBranch present confirms cwd IS a real git repo → cwd-derived project is authoritative.
    A later message with gitBranch=feat/... must get project=agents (branch 2 wins), NOT
    the mined project=maison-scaffold from mining the earlier --repo flag."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/agents",
                gitBranch="feat/issue-9-x",
                content=[_bash("gh pr view 99 --repo jwj2002/maison-scaffold")],
            ),
            _asst(2, ts="t2", cwd="/Users/x/agents", gitBranch="feat/issue-9-x"),
        ]
    )
    # msg1: gitBranch present → branch 2 → cwd-derived project wins → "agents"
    assert recs[0]["project"] == "agents"
    # msg2: active["project"] is now "maison-scaffold" from mining msg1, but gitBranch present →
    # branch 2 fires → cwd wins → project stays "agents" (hijack prevented)
    assert recs[1]["project"] == "agents"


# Test J — #311 TARGET: cwd=/Users/x/projects/scratch (non-repo), gitBranch absent → mined --repo wins
def test_scratch_cwd_uses_mined_project():
    """THE #311 TARGET CASE — realistic non-repo cwd with a cross-repo --repo signal.
    cwd=/Users/x/projects/scratch is a real path but NOT a git repo → gitBranch is absent/empty.
    With the old code, _project_from_path("scratch") would fire branch 2 and return "scratch",
    IGNORING the mined --repo agents signal entirely.
    With the gitBranch discriminant: gitBranch absent → branch 3 → mined project wins."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/projects/scratch",
                gitBranch=None,  # not in a git repo
                content=[_bash("gh pr merge 1 --repo jwj2002/agents --squash")],
            ),
            _asst(2, ts="t2", cwd="/Users/x/projects/scratch", gitBranch=None),
        ]
    )
    # msg1: gitBranch absent, no mined project yet → branch 4 fallback → cwd basename "scratch"
    assert recs[0]["project"] == "scratch"
    # msg2: gitBranch absent, active["project"]="agents" (mined from msg1) → branch 3 → "agents"
    # THIS IS THE #311 WIN: scratch-session gets attributed to agents, not "scratch".
    assert recs[1]["project"] == "agents"


# Test K — ssh-develop regression: ssh-derived project still wins when work_host != inference_host
def test_ssh_develop_project_attribution_not_regressed():
    """SSH-develop (§4.2): when ssh sets work_host to a remote, active["project"] (mined from ssh
    'cd repo') must still win for subsequent messages — even though cwd is local.
    Uses realistic cwd (a real local dir, but not the remote repo) and gitBranch to confirm
    branch 1 (on_remote) fires before branch 2 (gitBranch) and wins."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/projects/scratch",
                gitBranch=None,  # local cwd is not a git repo; user is SSHing out
                content=[_bash("ssh jns 'cd ~/app-repos/app-buddy && git status'")],
            ),
            _asst(
                2, ts="t2", cwd="/Users/x/projects/scratch", gitBranch=None
            ),  # still local after ssh
        ]
    )
    # msg1: on_remote=False (ssh fires but work_host still HOST until NEXT message), gitBranch absent,
    # no mined project yet → branch 4 → cwd basename "scratch"
    assert recs[0]["project"] == "scratch"
    # msg2: after ssh cmd, work_host="jns" (≠ HOST) → on_remote=True → branch 1 → ssh-mined
    # active["project"] wins. ssh 'cd ~/app-repos/app-buddy' → project="app-buddy" via cd.
    assert recs[1]["work_host"] == "jns"
    assert recs[1]["project"] == "app-buddy"


# --- Finding 3: tokenization tests (no raw-string false positives) ---------------------------------


def test_tokenization_echo_repo_not_matched():
    """echo '--repo evil/repo' must NOT mine a project — it is not a real gh invocation."""
    result = U.mine_command("echo '--repo evil/repo'")
    assert "project" not in result or result.get("project") is None


def test_tokenization_comment_not_matched():
    """A comment containing --repo must NOT mine a project."""
    result = U.mine_command("# gh pr view --repo jwj2002/agents")
    assert "project" not in result or result.get("project") is None


def test_tokenization_gh_inline_equals():
    """gh --repo=owner/name (inline =) must mine the project."""
    result = U.mine_command("gh pr create --repo=jwj2002/agents --title x")
    assert result.get("project") == "agents"


def test_tokenization_gh_no_slash_ignored():
    """gh --repo noSlashHere must not produce a project (no owner/name separator)."""
    result = U.mine_command("gh pr view --repo noSlashHere")
    assert "project" not in result or result.get("project") is None


# --- Finding 4: cross-command conflict guard --------------------------------------------------------


def test_cross_command_conflict_clears_project():
    """Two commands in the same message mining DIFFERENT projects → active["project"] cleared.
    The conflicting mined signal must NOT determine subsequent attribution; cwd fallback applies.
    Specifically: the project must NOT be "agents" or "maison-scaffold" (neither wins)."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/projects/scratch",
                gitBranch=None,
                content=[
                    _bash("gh pr view 1 --repo jwj2002/agents"),
                    _bash("gh pr view 2 --repo jwj2002/maison-scaffold"),
                ],
            ),
            _asst(2, ts="t2", cwd="/Users/x/projects/scratch", gitBranch=None),
        ]
    )
    # Conflicting mines → active["project"] cleared → branch 3 doesn't fire.
    # Branch 4 falls back to cwd basename "scratch" (the cwd itself is unambiguous).
    # Neither "agents" nor "maison-scaffold" must win (last-write-win prevented).
    assert recs[1]["project"] not in ("agents", "maison-scaffold"), (
        f"conflict guard FAILED: a conflicted project leaked through as {recs[1]['project']!r}"
    )


def test_cross_command_same_project_not_cleared():
    """Two commands mining the SAME project must NOT clear it (only conflict clears)."""
    recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/projects/scratch",
                gitBranch=None,
                content=[
                    _bash("gh pr view 1 --repo jwj2002/agents"),
                    _bash("gh pr view 2 --repo jwj2002/agents"),
                ],
            ),
            _asst(2, ts="t2", cwd="/Users/x/projects/scratch", gitBranch=None),
        ]
    )
    # Same project from both commands → no conflict → project = "agents"
    assert recs[1]["project"] == "agents"


# --- AC4 counterfactual: #311 target vs old cwd-basename mis-attribution ---------------------------


def test_311_target_vs_old_cwd_basename():
    """Demonstrate the #311 win: with gitBranch discriminant, a scratch session with
    gh --repo jwj2002/agents correctly attributes to agents, not to the cwd basename 'scratch'.
    Also demonstrate that the hijack case (gitBranch present) correctly prevents override."""
    # THE #311 TARGET: cwd=scratch (not a repo), gitBranch absent → mined --repo wins
    target_recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/projects/scratch",
                gitBranch=None,
                content=[_bash("gh pr merge 1 --repo jwj2002/agents --squash")],
            ),
            _asst(2, ts="t2", cwd="/Users/x/projects/scratch", gitBranch=None),
        ]
    )
    # msg2 must get project=agents (not "scratch", which the old code would return)
    assert target_recs[1]["project"] == "agents", (
        f"#311 target FAILED: expected 'agents', got {target_recs[1]['project']!r}"
    )

    # HIJACK-PREVENTED: cwd=agents with gitBranch present → cwd wins, stray --repo ignored
    hijack_recs = _extract(
        [
            _asst(
                1,
                ts="t1",
                cwd="/Users/x/agents",
                gitBranch="feat/issue-9-x",
                content=[_bash("gh pr view 99 --repo jwj2002/maison-scaffold")],
            ),
            _asst(2, ts="t2", cwd="/Users/x/agents", gitBranch="feat/issue-9-x"),
        ]
    )
    # msg2 must get project=agents (not "maison-scaffold" — hijack prevented)
    assert hijack_recs[1]["project"] == "agents", (
        f"hijack FAILED: expected 'agents', got {hijack_recs[1]['project']!r}"
    )
