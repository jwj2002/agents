"""Tests for D7e — files_changed_enrich.py (issue #325).

Coverage:
  1. pr_git → (N, "pr_git") on a fixture git repo with a squash-merge commit touching N files
  2. session_shard single-task → used; multi-task session → (None, "none") (no overstatement)
  3. session_shard excludes telemetry/temp paths + dedupes
  4. pr_git beats session_shard when both present
  5. no signal → (None, "none")
  6. project_metrics → (N, "project_metrics")
  7. pr_git beats project_metrics
  8. usage_collect with --no-enrich → rows have files_changed=null, source="none"
  9. usage_collect default → a row whose task has pr_git data gets files_changed=N, source="pr_git"
 10. Non-issue task string → (None, "none")
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import files_changed_enrich as FCE  # noqa: E402
import usage_collect as UC  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers: git fixture repo
# ---------------------------------------------------------------------------

HOST = "testhost"


def _make_git_repo_with_squash_commit(
    tmp_path: Path, issue: int, files: list[str]
) -> Path:
    """Create a minimal git repo with a squash-merge commit for issue N touching `files`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    # Create the files and commit
    for f in files:
        p = repo / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"content of {f}", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "--all"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            f"feat(#42): implement thing (#{issue})",
        ],
        check=True,
        capture_output=True,
    )
    return repo


def _make_sessions_shard(tmp_path: Path, records: list[dict]) -> Path:
    """Write sessions.jsonl to a temp dir and return the path."""
    shard = tmp_path / "sessions.jsonl"
    with shard.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return shard


def _session_record(
    issue: int | None,
    issue_refs: list[int] | None = None,
    files_touched: list[str] | None = None,
) -> dict:
    """Build a minimal sessions.jsonl record."""
    return {
        "schema_version": 1,
        "event_type": "session_capture",
        "session_id": "s1",
        "host": HOST,
        "task_attribution": {
            "issue": issue,
            "branch": None,
            "phase": None,
            "source": "branch",
        },
        "artifact_evidence": {
            "files_touched": files_touched or [],
            "pr_links": [],
            "issue_refs": issue_refs or ([] if issue is None else [issue]),
            "has_code_edits": True,
            "has_pr_link": False,
            "has_test_run": False,
            "has_commit": False,
        },
        "boundary": {"frozen_at": "none"},
    }


def _make_metrics_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    """Write metrics.jsonl to tmp_path and return its path."""
    p = tmp_path / "metrics.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return p


# ---------------------------------------------------------------------------
# 1. pr_git: squash-merge commit → (N, "pr_git")
# ---------------------------------------------------------------------------


def test_pr_git_returns_file_count(tmp_path):
    files = ["a.py", "b.py", "c.py"]
    repo = _make_git_repo_with_squash_commit(tmp_path, issue=42, files=files)
    fc, src = FCE.enrich_task("issue:42", repo_root=repo)
    assert src == "pr_git"
    assert fc == len(files)


def test_pr_git_no_matching_commit(tmp_path):
    files = ["a.py"]
    repo = _make_git_repo_with_squash_commit(tmp_path, issue=42, files=files)
    # Ask for issue 99, which has no commit
    fc, src = FCE.enrich_task("issue:99", repo_root=repo)
    assert (fc, src) == (None, "none")


# ---------------------------------------------------------------------------
# 2. project_metrics → (N, "project_metrics")
# ---------------------------------------------------------------------------


def test_project_metrics_found(tmp_path):
    m = _make_metrics_jsonl(
        tmp_path, [{"issue": 42, "files_changed": 7, "status": "SUCCESS"}]
    )
    fc, src = FCE.enrich_task("issue:42", metrics_path=m)
    assert src == "project_metrics"
    assert fc == 7


def test_project_metrics_not_found(tmp_path):
    m = _make_metrics_jsonl(
        tmp_path, [{"issue": 99, "files_changed": 3, "status": "SUCCESS"}]
    )
    fc, src = FCE.enrich_task("issue:42", metrics_path=m)
    assert (fc, src) == (None, "none")


def test_project_metrics_missing_field(tmp_path):
    m = _make_metrics_jsonl(tmp_path, [{"issue": 42, "status": "SUCCESS"}])
    fc, src = FCE.enrich_task("issue:42", metrics_path=m)
    assert (fc, src) == (None, "none")


# ---------------------------------------------------------------------------
# 3. session_shard single-task → used; multi-task session → (None, "none")
# ---------------------------------------------------------------------------


def test_session_shard_single_task_used(tmp_path):
    shard = _make_sessions_shard(
        tmp_path,
        [_session_record(issue=42, files_touched=["a.py", "b.py", "c.py"])],
    )
    fc, src = FCE.enrich_task("issue:42", sessions_shard=shard)
    assert src == "session_shard"
    assert fc == 3


def test_session_shard_multi_task_disqualified(tmp_path):
    """Session references both issue 42 and issue 99 — multi-task → disqualified."""
    rec = _session_record(issue=42, issue_refs=[42, 99], files_touched=["a.py", "b.py"])
    shard = _make_sessions_shard(tmp_path, [rec])
    fc, src = FCE.enrich_task("issue:42", sessions_shard=shard)
    assert (fc, src) == (None, "none")


def test_session_shard_multi_task_via_task_attribution(tmp_path):
    """Session task_attribution.issue=42 but issue_refs=[42,100] → multi-task."""
    rec = {
        "schema_version": 1,
        "event_type": "session_capture",
        "session_id": "s1",
        "host": HOST,
        "task_attribution": {
            "issue": 42,
            "branch": None,
            "phase": None,
            "source": "branch",
        },
        "artifact_evidence": {
            "files_touched": ["a.py"],
            "pr_links": [],
            "issue_refs": [42, 100],
            "has_code_edits": True,
            "has_pr_link": False,
            "has_test_run": False,
            "has_commit": False,
        },
        "boundary": {"frozen_at": "none"},
    }
    shard = _make_sessions_shard(tmp_path, [rec])
    fc, src = FCE.enrich_task("issue:42", sessions_shard=shard)
    assert (fc, src) == (None, "none")


# ---------------------------------------------------------------------------
# 4. session_shard: telemetry/ and temp/ paths are excluded; deduplication
# ---------------------------------------------------------------------------


def test_session_shard_excludes_telemetry_and_temp_paths(tmp_path):
    files = [
        "scripts/foo.py",  # kept
        "telemetry/mac/sessions.jsonl",  # excluded (telemetry)
        "scripts/bar.py",  # kept
        ".claude/telemetry/usage.jsonl",  # excluded (telemetry)
        "temp/scratch.txt",  # excluded (temp)
    ]
    shard = _make_sessions_shard(
        tmp_path,
        [_session_record(issue=42, files_touched=files)],
    )
    fc, src = FCE.enrich_task("issue:42", sessions_shard=shard)
    assert src == "session_shard"
    assert fc == 2  # only scripts/foo.py and scripts/bar.py


def test_session_shard_deduplicates_paths(tmp_path):
    files = ["a.py", "b.py", "a.py", "c.py", "b.py"]
    shard = _make_sessions_shard(
        tmp_path,
        [_session_record(issue=42, files_touched=files)],
    )
    fc, src = FCE.enrich_task("issue:42", sessions_shard=shard)
    assert src == "session_shard"
    assert fc == 3  # a.py, b.py, c.py after dedup


# ---------------------------------------------------------------------------
# 5. pr_git beats session_shard (and project_metrics) when both present
# ---------------------------------------------------------------------------


def test_pr_git_beats_session_shard(tmp_path):
    files_git = ["a.py", "b.py"]  # 2 files in git
    repo = _make_git_repo_with_squash_commit(tmp_path, issue=42, files=files_git)
    shard = _make_sessions_shard(
        tmp_path,
        [_session_record(issue=42, files_touched=["x.py", "y.py", "z.py"])],
    )
    fc, src = FCE.enrich_task("issue:42", repo_root=repo, sessions_shard=shard)
    assert src == "pr_git"
    assert fc == 2


def test_pr_git_beats_project_metrics(tmp_path):
    files_git = ["a.py", "b.py", "c.py"]  # 3 files in git
    repo = _make_git_repo_with_squash_commit(tmp_path, issue=42, files=files_git)
    m = _make_metrics_jsonl(tmp_path, [{"issue": 42, "files_changed": 99}])
    fc, src = FCE.enrich_task("issue:42", repo_root=repo, metrics_path=m)
    assert src == "pr_git"
    assert fc == 3


def test_project_metrics_beats_session_shard(tmp_path):
    m = _make_metrics_jsonl(tmp_path, [{"issue": 42, "files_changed": 5}])
    shard = _make_sessions_shard(
        tmp_path,
        [_session_record(issue=42, files_touched=["x.py", "y.py"])],
    )
    fc, src = FCE.enrich_task("issue:42", metrics_path=m, sessions_shard=shard)
    assert src == "project_metrics"
    assert fc == 5


# ---------------------------------------------------------------------------
# 6. No signal → (None, "none")
# ---------------------------------------------------------------------------


def test_no_signal_none(tmp_path):
    fc, src = FCE.enrich_task("issue:42")
    assert (fc, src) == (None, "none")


def test_no_signal_none_all_paths_empty(tmp_path):
    shard = _make_sessions_shard(tmp_path, [])
    m = _make_metrics_jsonl(tmp_path, [])
    fc, src = FCE.enrich_task(
        "issue:42",
        metrics_path=m,
        sessions_shard=shard,
    )
    assert (fc, src) == (None, "none")


# ---------------------------------------------------------------------------
# 7. Non-issue task string → (None, "none")
# ---------------------------------------------------------------------------


def test_non_issue_task_none():
    fc, src = FCE.enrich_task("free-text-task")
    assert (fc, src) == (None, "none")


def test_none_task_none():
    fc, src = FCE.enrich_task(None)
    assert (fc, src) == (None, "none")


def test_empty_task_none():
    fc, src = FCE.enrich_task("")
    assert (fc, src) == (None, "none")


# ---------------------------------------------------------------------------
# 8. usage_collect --no-enrich → rows have files_changed=null, source="none"
# ---------------------------------------------------------------------------


def _asst_entry(uuid, *, ts, sid="s1", gitBranch=None, cwd=None):
    return {
        "type": "assistant",
        "sessionId": sid,
        "uuid": uuid,
        "timestamp": ts,
        "gitBranch": gitBranch,
        "cwd": cwd,
        "message": {
            "role": "assistant",
            "model": "claude-opus-4",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "content": [],
        },
    }


def _run_collect(
    tmp_path, *, enrich=True, metrics_path=None, repo_root=None, full=True
):
    base = tmp_path / "telemetry" / HOST
    base.mkdir(parents=True, exist_ok=True)
    claude_dir = tmp_path / "claude_projects"
    claude_dir.mkdir(exist_ok=True)
    code, stats = UC.run_collect(
        base_dir=base,
        full=full,
        enrich=enrich,
        repo_root=repo_root,
        metrics_path=metrics_path,
        claude_projects_dir=claude_dir,
        codex_sessions_dir=Path("/nonexistent_codex_dir_xyz"),
        sidecar_path=tmp_path / "account-map.jsonl",
        claude_json_path=tmp_path / ".claude.json",
        codex_auth_path=tmp_path / "auth.json",
    )
    return code, stats, base, claude_dir


def _write_transcript(claude_dir, session, entries):
    d = claude_dir / "proj1"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{session}.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return p


def test_no_enrich_rows_have_null_files_changed(tmp_path):
    """--no-enrich: rows written with files_changed=null and source='none'."""
    code, stats, base, claude_dir = _run_collect(tmp_path, enrich=False)
    entries = [
        _asst_entry("u1", ts="2026-06-01T00:00:00Z", gitBranch="feature/issue-42-slug"),
    ]
    _write_transcript(claude_dir, "sess1", entries)

    code, stats, base, _ = _run_collect(tmp_path, enrich=False, full=True)
    usage_path = base / "usage.jsonl"
    rows = [
        json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()
    ]
    assert len(rows) >= 1
    for row in rows:
        assert row.get("files_changed") is None, "no-enrich: files_changed must be null"
        assert row.get("files_changed_source") in (None, "none"), (
            "no-enrich: source must be none"
        )


# ---------------------------------------------------------------------------
# 9. usage_collect default: row whose task has pr_git data → files_changed=N, source="pr_git"
# ---------------------------------------------------------------------------


def test_default_enrich_uses_pr_git(tmp_path):
    """Default enrich=True: row with task=issue:42 gets files_changed from git commit."""
    # Make a git repo with a squash-merge commit for issue 42
    files_git = ["a.py", "b.py", "c.py"]
    repo = _make_git_repo_with_squash_commit(tmp_path, issue=42, files=files_git)

    code, stats, base, claude_dir = _run_collect(tmp_path, enrich=True)
    # The transcript needs gitBranch so task is attributed to issue:42
    entries = [
        _asst_entry("u1", ts="2026-06-01T00:00:00Z", gitBranch="feature/issue-42-slug"),
    ]
    _write_transcript(claude_dir, "sess1", entries)

    code, stats, base, _ = _run_collect(
        tmp_path, enrich=True, repo_root=repo, full=True
    )
    usage_path = base / "usage.jsonl"
    rows = [
        json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()
    ]
    assert len(rows) >= 1

    # Find the row attributed to issue:42
    issue_rows = [r for r in rows if r.get("task") == "issue:42"]
    assert issue_rows, f"No row with task=issue:42 found; rows={rows}"
    for row in issue_rows:
        assert row.get("files_changed") == len(files_git), (
            f"Expected {len(files_git)}, got {row.get('files_changed')}"
        )
        assert row.get("files_changed_source") == "pr_git"


# ---------------------------------------------------------------------------
# 10. Golden-parity: enrichment does NOT change attribution fields
# ---------------------------------------------------------------------------


def test_enrich_does_not_change_attribution_fields(tmp_path):
    """Enrichment only stamps files_changed/source — attribution fields unchanged."""
    files_git = ["x.py"]
    repo = _make_git_repo_with_squash_commit(tmp_path, issue=42, files=files_git)
    entries = [
        _asst_entry("u1", ts="2026-06-01T00:00:00Z", gitBranch="feature/issue-42-slug"),
    ]
    _, _, base_no_enrich, claude_dir = _run_collect(tmp_path, enrich=False)
    _write_transcript(claude_dir, "sess_base", entries)
    _, _, base_no_enrich, _ = _run_collect(
        tmp_path, enrich=False, repo_root=repo, full=True
    )
    rows_no = [
        json.loads(line)
        for line in (base_no_enrich / "usage.jsonl").read_text().splitlines()
        if line.strip()
    ]

    # Reset and run with enrich
    base2 = tmp_path / "telemetry2" / HOST
    base2.mkdir(parents=True, exist_ok=True)
    claude_dir2 = tmp_path / "claude_projects2"
    claude_dir2.mkdir(exist_ok=True)
    _write_transcript(claude_dir2, "sess_enrich", entries)
    _, _, base_enrich, _ = (
        lambda: (
            *UC.run_collect(
                base_dir=base2,
                full=True,
                enrich=True,
                repo_root=repo,
                claude_projects_dir=claude_dir2,
                codex_sessions_dir=Path("/nonexistent_codex_xyz"),
                sidecar_path=tmp_path / "account-map2.jsonl",
                claude_json_path=tmp_path / ".claude2.json",
                codex_auth_path=tmp_path / "auth2.json",
            ),
            base2,
            claude_dir2,
        )
    )()
    rows_en = [
        json.loads(line)
        for line in (base_enrich / "usage.jsonl").read_text().splitlines()
        if line.strip()
    ]

    assert len(rows_no) == len(rows_en), "row count must match"
    for rn, re_ in zip(rows_no, rows_en):
        for field in (
            "project",
            "task",
            "work_host",
            "dedup_key",
            "model",
            "input",
            "output",
        ):
            assert rn.get(field) == re_.get(field), (
                f"field {field!r} changed by enrichment: {rn.get(field)!r} != {re_.get(field)!r}"
            )
        # enrichment fields differ (that's the point)
        assert re_.get("files_changed") is not None or re_.get("task") != "issue:42"
