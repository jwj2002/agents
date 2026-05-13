"""Tests for lib/host_resolver.py (#161).

Subprocess calls (git, gh, ssh) are mocked via monkeypatched ``_run_local``.
This keeps tests fast and lets us simulate network/timeout/error paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import host_resolver as hr


@pytest.fixture(autouse=True)
def _reset_cache():
    hr.clear_cache()
    yield
    hr.clear_cache()


# ---------- mock helpers ----------

class MockRunner:
    """Records calls and returns scripted (rc, stdout, stderr) tuples by command match."""

    def __init__(self, responses: dict[str, tuple[int, str, str]] | None = None):
        # Key is a substring of the joined command; first match wins.
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *, cwd=None, timeout=10):
        self.calls.append(list(cmd))
        joined = " ".join(cmd)
        for needle, response in self.responses.items():
            if needle in joined:
                return response
        return (0, "", "")  # default: success, empty


def _install(monkeypatch, responses):
    runner = MockRunner(responses)
    monkeypatch.setattr(hr, "_run_local", runner)
    return runner


# ---------- gh slug derivation ----------

def test_derive_gh_slug_ssh_url():
    assert hr.derive_gh_slug("git@github.com:jwj2002/agents.git") == "jwj2002/agents"


def test_derive_gh_slug_https_url():
    assert hr.derive_gh_slug("https://github.com/jwj2002/agents.git") == "jwj2002/agents"


def test_derive_gh_slug_https_no_git_suffix():
    assert hr.derive_gh_slug("https://github.com/jwj2002/agents") == "jwj2002/agents"


def test_derive_gh_slug_empty():
    assert hr.derive_gh_slug("") is None


def test_derive_gh_slug_non_github():
    assert hr.derive_gh_slug("https://gitlab.example.com/x/y.git") is None


# ---------- git state ----------

def test_read_git_state_basic_local(monkeypatch):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref refs/remotes/origin/HEAD": (0, "refs/remotes/origin/main\n", ""),
        "rev-list --count origin/main..HEAD": (0, "2\n", ""),
        "rev-list --count HEAD..origin/main": (0, "0\n", ""),
        "status --porcelain": (0, "", ""),
        "log -1 --format": (0, "2026-05-13T10:00:00-07:00|abcdef1234|fix: a thing\n", ""),
        "--since=24 hours ago": (0, "a\nb\nc\n", ""),
        "--since=7 days ago": (0, "a\nb\nc\nd\ne\n", ""),
        "branch --merged": (0, "  main\n  feat/old\n* feature/wip\n", ""),
        "for-each-ref": (0, "main \nfeat/local [gone]\nfeat/wip [ahead 1]\n", ""),
    })
    state = hr.read_repo_state("/x/agents", use_cache=False)
    assert state.reachable
    assert state.branch == "main"
    assert state.ahead_origin == 2
    assert state.behind_origin == 0
    assert state.dirty is False
    assert state.last_commit_at == "2026-05-13T10:00:00-07:00"
    assert state.last_commit_sha == "abcdef1"
    assert state.last_commit_subject == "fix: a thing"
    assert state.commits_24h == 3
    assert state.commits_7d == 5
    assert state.stale_local_branches == ["feat/old", "feature/wip"]
    assert state.unpushed_branches == ["feat/local", "feat/wip"]


def test_unreachable_repo_marked(monkeypatch):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (128, "", "fatal: not a git repo"),
    })
    state = hr.read_repo_state("/nowhere", use_cache=False)
    assert state.reachable is False
    assert state.reason == "no-clone-or-unreachable"


def test_dirty_detected(monkeypatch):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "status --porcelain": (0, "M  src/x.py\n?? new.py\n", ""),
        "rev-list": (0, "0\n", ""),
        "log": (0, "", ""),
        "branch --merged": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    state = hr.read_repo_state("/x", use_cache=False)
    assert state.dirty is True


def test_default_branch_fallback_to_main(monkeypatch):
    """No origin/HEAD symbolic-ref → still produce ahead/behind against main."""
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (1, "", "no symbolic ref"),
        "rev-list --count origin/main..HEAD": (0, "5\n", ""),
        "rev-list --count HEAD..origin/main": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    state = hr.read_repo_state("/x", use_cache=False)
    assert state.ahead_origin == 5


# ---------- gh state ----------

def test_gh_state_collected_when_slug_provided(monkeypatch):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
        "issue list --state open": (0, "5\n", ""),
        "issue list --state closed": (0, "2\n", ""),
    })
    state = hr.read_repo_state("/x", gh_slug="jwj2002/agents", use_cache=False)
    assert state.open_issues == 5
    assert state.closed_issues_24h == 2


def test_gh_skipped_without_slug(monkeypatch):
    runner = _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    state = hr.read_repo_state("/x", use_cache=False)
    assert state.open_issues is None
    assert state.closed_issues_24h is None
    # No `gh` invocations
    gh_calls = [c for c in runner.calls if c and c[0] == "gh"]
    assert gh_calls == []


def test_gh_failure_keeps_other_fields(monkeypatch):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
        "issue list": (1, "", "auth required"),  # gh fails entirely
    })
    state = hr.read_repo_state("/x", gh_slug="x/y", use_cache=False)
    assert state.reachable is True
    assert state.open_issues is None
    assert state.closed_issues_24h is None


# ---------- ACTIONS.md ----------

_ACTIONS_TEMPLATE = """\
# Actions

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|-------|--------|-------|--------|--------|-----|-------|-------|
| A-001 | #1 | thing one | jason | open | 2026-05-10 | issue | | |
| A-002 | #2 | thing two | jason | wip | 2026-05-12 | issue | | |

## Recently Closed

| ID | Issue | Action | Owner | Opened | Closed | Files | Notes |
|----|-------|--------|-------|--------|--------|-------|-------|
| A-003 | #3 | done | jason | 2026-05-01 | {recent} | | |
| A-004 | #4 | old done | jason | 2026-04-01 | 2026-04-10 | | |

Next ID: **A-005**
"""


def test_actions_md_counts(monkeypatch, tmp_path):
    from datetime import date
    today = date.today().isoformat()
    actions = tmp_path / "ACTIONS.md"
    actions.write_text(_ACTIONS_TEMPLATE.format(recent=today))
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    state = hr.read_repo_state(str(tmp_path), actions_path=actions, use_cache=False)
    assert state.open_actions == 2
    assert state.closed_actions_24h == 1


def test_actions_md_missing(monkeypatch, tmp_path):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    state = hr.read_repo_state(
        str(tmp_path), actions_path=tmp_path / "missing.md", use_cache=False,
    )
    assert state.open_actions == -1  # signal "—" in dataview


# ---------- SSH path ----------

def test_ssh_command_built_correctly(monkeypatch):
    runner = _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    hr.read_repo_state("/home/jjob/agents", ssh_host="jbox06", use_cache=False)
    # First SSH call: includes connect timeout + BatchMode + the remote host
    first = runner.calls[0]
    assert first[0] == "ssh"
    assert "-o" in first
    assert "ConnectTimeout=5" in first
    assert "BatchMode=yes" in first
    assert "jbox06" in first
    # The remote command appears as a single argument
    remote_cmd = first[-1]
    assert "git -C /home/jjob/agents rev-parse --abbrev-ref HEAD" in remote_cmd


def test_ssh_timeout_marks_unreachable(monkeypatch):
    _install(monkeypatch, {
        "ssh": (-1, "", "timeout"),
    })
    state = hr.read_repo_state("/x", ssh_host="ghost", use_cache=False)
    assert state.reachable is False


def test_actions_md_skipped_on_ssh(monkeypatch, tmp_path):
    """SSH mode doesn't read remote ACTIONS.md in v1; open_actions stays -1."""
    actions = tmp_path / "ACTIONS.md"
    actions.write_text(_ACTIONS_TEMPLATE.format(recent="2026-05-13"))
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    state = hr.read_repo_state(
        str(tmp_path), ssh_host="jbox06", actions_path=actions, use_cache=False,
    )
    assert state.open_actions == -1


# ---------- cache ----------

def test_cache_hit_skips_second_subprocess_burst(monkeypatch):
    runner = _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    hr.read_repo_state("/x", use_cache=True, now=1000.0)
    first_call_count = len(runner.calls)
    hr.read_repo_state("/x", use_cache=True, now=1100.0)  # within 5-min TTL
    assert len(runner.calls) == first_call_count


def test_cache_expires_after_ttl(monkeypatch):
    runner = _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    hr.read_repo_state("/x", use_cache=True, now=1000.0)
    first_call_count = len(runner.calls)
    hr.read_repo_state("/x", use_cache=True, now=1000.0 + 301)  # past TTL
    assert len(runner.calls) > first_call_count


def test_cache_disabled_always_runs(monkeypatch):
    runner = _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    hr.read_repo_state("/x", use_cache=False)
    first = len(runner.calls)
    hr.read_repo_state("/x", use_cache=False)
    assert len(runner.calls) > first


def test_cache_key_distinguishes_hosts(monkeypatch):
    _install(monkeypatch, {
        "rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
        "symbolic-ref": (0, "refs/remotes/origin/main\n", ""),
        "rev-list": (0, "0\n", ""),
        "status": (0, "", ""),
        "log": (0, "", ""),
        "branch": (0, "", ""),
        "for-each-ref": (0, "", ""),
    })
    a = hr.read_repo_state("/x", ssh_host="hostA", use_cache=True, now=1000.0)
    b = hr.read_repo_state("/x", ssh_host="hostB", use_cache=True, now=1000.0)
    # Different objects (separate cache entries)
    assert a is not b


# ---------- to_dict ----------

def test_to_dict_includes_all_sidecar_fields():
    state = hr.RepoState(reachable=True, branch="main", dirty=True)
    out = state.to_dict()
    for key in (
        "reachable", "last_commit_at", "last_commit_subject", "last_commit_sha",
        "commits_24h", "commits_7d", "open_actions", "closed_actions_24h",
        "open_issues", "closed_issues_24h", "branch", "ahead_origin",
        "behind_origin", "dirty", "stale_local_branches", "unpushed_branches",
    ):
        assert key in out


def test_to_dict_omits_reason_when_reachable():
    state = hr.RepoState(reachable=True)
    assert "reason" not in state.to_dict()


def test_to_dict_includes_reason_when_unreachable():
    state = hr.RepoState(reachable=False, reason="no-clone-or-unreachable")
    out = state.to_dict()
    assert out["reason"] == "no-clone-or-unreachable"


# ---------- utc_now_iso ----------

def test_utc_now_iso_format():
    s = hr.utc_now_iso()
    assert s.endswith("Z")
    assert "T" in s
    # No microseconds — second precision
    assert "." not in s
