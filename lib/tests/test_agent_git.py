from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.agent_git import parse_status, preflight, readiness, ship


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd)


def make_repo(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"

    git(["init", "--bare", str(remote)], tmp_path)
    git(["clone", str(remote), str(work)], tmp_path)
    git(["config", "user.email", "agent@example.com"], work)
    git(["config", "user.name", "Agent"], work)
    (work / "README.md").write_text("# Test\n", encoding="utf-8")
    git(["add", "README.md"], work)
    git(["commit", "-m", "docs: seed"], work)
    git(["branch", "-M", "main"], work)
    git(["push", "-u", "origin", "main"], work)
    git(["remote", "set-head", "origin", "-a"], work)
    return work


def branch(work: Path) -> None:
    git(["switch", "-c", "feature/issue-1-test", "origin/main"], work)


def branch_for_issue(work: Path, issue: int = 42) -> None:
    git(["switch", "-c", f"feature/issue-{issue}-add-tooling", "origin/main"], work)


def commit_file(work: Path, path: str = "tooling.txt", message: str = "feat(git): add tooling") -> None:
    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("content\n", encoding="utf-8")
    git(["add", path], work)
    git(["commit", "-m", message], work)


def test_preflight_fails_on_main_branch(tmp_path: Path) -> None:
    work = make_repo(tmp_path)

    result = preflight(work, no_fetch=True)

    assert not result.ok
    assert any("Current branch is main" in error for error in result.errors)


def test_preflight_passes_on_clean_issue_branch(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch(work)

    result = preflight(work, no_fetch=True)

    assert result.ok
    assert result.branch == "feature/issue-1-test"
    assert result.default_branch == "main"


def test_preflight_fails_on_unsafe_dirty_file(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch(work)
    (work / "README.md").write_text("# Dirty\n", encoding="utf-8")

    result = preflight(work, no_fetch=True)

    assert not result.ok
    assert any("Unsafe dirty file: README.md" in error for error in result.errors)


def test_preflight_warns_on_generated_dirty_file(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch(work)
    telemetry = work / "telemetry" / "host" / "failures.jsonl"
    telemetry.parent.mkdir(parents=True)
    telemetry.write_text("{}\n", encoding="utf-8")

    result = preflight(work, no_fetch=True)

    assert result.ok
    assert any("Generated or runtime dirty file" in warning for warning in result.warnings)


def test_preflight_detects_stale_branch(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch(work)

    other = tmp_path / "other"
    git(["clone", str(tmp_path / "remote.git"), str(other)], tmp_path)
    git(["config", "user.email", "agent@example.com"], other)
    git(["config", "user.name", "Agent"], other)
    (other / "other.txt").write_text("new\n", encoding="utf-8")
    git(["add", "other.txt"], other)
    git(["commit", "-m", "docs: update remote"], other)
    git(["push", "origin", "main"], other)

    result = preflight(work)

    assert not result.ok
    assert result.behind_default == 1
    assert any("behind origin/main by 1 commit" in error for error in result.errors)


def test_parse_status_marks_conflicts() -> None:
    files = parse_status("UU src/app.py\n?? scratch.txt\n!! .pytest_cache/data\n")

    assert files[0].conflict is True
    assert files[0].kind == "tracked"
    assert files[1].kind == "untracked"
    assert files[2].kind == "ignored"


def test_cli_json_output(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch(work)
    script = Path(__file__).resolve().parents[2] / "bin" / "agent-git"

    completed = subprocess.run(
        [sys.executable, str(script), "preflight", "--repo", str(work), "--no-fetch", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["branch"] == "feature/issue-1-test"


def test_github_cli_missing_degrades(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch(work)

    monkeypatch.setattr("lib.agent_git.shutil.which", lambda _: None)

    result = preflight(work, no_fetch=True)

    assert result.ok
    assert any("GitHub CLI not found" in warning for warning in result.warnings)


def test_readiness_passes_with_issue_summary_tests_and_scope(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, "src/tool.py")

    result = readiness(
        work,
        issue=42,
        summary="add shared git tooling",
        test_evidence=["pytest lib/tests/test_agent_git.py -q"],
        allowed_paths=["src/"],
        generate_pr_body=True,
    )

    assert result.ok
    assert result.issue == 42
    assert "Closes #42" in (result.pr_body or "")


def test_readiness_fails_invalid_branch(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    git(["switch", "-c", "feature/no-issue", "origin/main"], work)
    commit_file(work)

    result = readiness(
        work,
        issue=42,
        summary="add shared git tooling",
        test_evidence=["pytest -q"],
    )

    assert not result.ok
    assert any("Branch name must match" in error for error in result.errors)


def test_readiness_fails_missing_test_evidence(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work)

    result = readiness(work, issue=42, summary="add shared git tooling")

    assert not result.ok
    assert any("Test Plan evidence is required" in error for error in result.errors)


def test_readiness_fails_invalid_commit_summary(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, message="bad commit")

    result = readiness(
        work,
        issue=42,
        summary="add shared git tooling",
        test_evidence=["pytest -q"],
    )

    assert not result.ok
    assert any("Commit summary is not Conventional Commits" in error for error in result.errors)


def test_readiness_fails_changed_file_outside_allowed_scope(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, "docs/tooling.md", "docs(git): add tooling docs")

    result = readiness(
        work,
        issue=42,
        summary="add shared git tooling",
        test_evidence=["pytest -q"],
        allowed_paths=["src/"],
    )

    assert not result.ok
    assert any("outside allowed scope" in error for error in result.errors)


def test_readiness_cli_generates_pr_body(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, "src/tool.py")
    script = Path(__file__).resolve().parents[2] / "bin" / "agent-git"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "readiness",
            "--repo",
            str(work),
            "--issue",
            "42",
            "--summary",
            "add shared git tooling",
            "--test-evidence",
            "pytest lib/tests/test_agent_git.py -q",
            "--allowed-path",
            "src/",
            "--generate-pr-body",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert "Closes #42" in payload["pr_body"]


def test_ship_dry_run_passes_through_gates(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, "src/tool.py")

    result = ship(
        work,
        issue=42,
        summary="add shared git tooling",
        test_evidence=["pytest lib/tests/test_agent_git.py -q"],
        allowed_paths=["src/"],
        dry_run=True,
        no_fetch=True,
    )

    assert result.ok
    assert result.dry_run is True
    assert result.stopped is False
    assert "squash_merge" in result.steps


def test_ship_stops_on_preflight_failure(tmp_path: Path) -> None:
    work = make_repo(tmp_path)

    result = ship(
        work,
        issue=42,
        summary="add shared git tooling",
        test_evidence=["pytest -q"],
        dry_run=True,
        no_fetch=True,
    )

    assert not result.ok
    assert result.stopped is True
    assert result.stop_reason == "preflight failed"
    assert any("Current branch is main" in error for error in result.errors)


def test_ship_stops_on_readiness_failure(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, "src/tool.py")

    result = ship(
        work,
        issue=42,
        summary="add shared git tooling",
        dry_run=True,
        no_fetch=True,
    )

    assert not result.ok
    assert result.stopped is True
    assert result.stop_reason == "readiness failed"
    assert any("Test Plan evidence is required" in error for error in result.errors)


def test_ship_cli_dry_run_json(tmp_path: Path) -> None:
    work = make_repo(tmp_path)
    branch_for_issue(work, 42)
    commit_file(work, "src/tool.py")
    script = Path(__file__).resolve().parents[2] / "bin" / "agent-git"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "ship",
            "--repo",
            str(work),
            "--issue",
            "42",
            "--summary",
            "add shared git tooling",
            "--test-evidence",
            "pytest lib/tests/test_agent_git.py -q",
            "--allowed-path",
            "src/",
            "--dry-run",
            "--no-fetch",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert "squash_merge" in payload["steps"]
