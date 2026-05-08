"""Tests for action/cli.py — project picker and resolution logic."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure action package is importable without an action/__init__.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import action.cli as cli


# ---------- helpers ----------

def _args(**kwargs) -> argparse.Namespace:
    """Build a minimal Namespace with defaults for fields used by resolution logic."""
    defaults = {"project": None, "no_prompt": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------- list_known_projects ----------

def test_list_known_projects():
    """Returns a sorted non-empty list filtered by subscriptions (or all if no subs)."""
    projects = cli.list_known_projects()
    assert isinstance(projects, list)
    assert projects == sorted(projects), "list must be sorted"
    assert len(projects) > 0, "must find at least one project"
    # 'agents' is always subscribed on this machine
    assert "agents" in projects


def test_list_known_projects_tmp(tmp_path, monkeypatch):
    """list_known_projects uses KNOWLEDGE_PROJECTS_DIR, which can be overridden."""
    (tmp_path / "alpha.yaml").write_text("")
    (tmp_path / "gamma.yaml").write_text("")
    (tmp_path / "beta.yaml").write_text("")
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    result = cli.list_known_projects()
    assert result == ["alpha", "beta", "gamma"]


# ---------- resolve_project (existing, unchanged) ----------

def test_resolve_project_cwd_agents(monkeypatch):
    """cwd = ~/agents → resolves to 'agents' without touching the picker."""
    monkeypatch.chdir(cli.HOME / "agents")
    args = _args()
    assert cli.resolve_project(args) == "agents"


def test_resolve_project_explicit_known(monkeypatch):
    """--project supplied directly bypasses cwd logic (existing behavior)."""
    args = _args(project="agents")
    # resolve_project just returns it — no validation against known list
    assert cli.resolve_project(args) == "agents"


# ---------- _interactive_pick ----------

def test_interactive_pick_valid(monkeypatch):
    """Input '2' selects second candidate."""
    monkeypatch.setattr("builtins.input", lambda _: "2")
    result = cli.project_resolver.interactive_pick(["alpha", "beta", "gamma"], "Pick one:")
    assert result == "beta"


def test_interactive_pick_out_of_range_then_valid(monkeypatch):
    """Two bad inputs (out of range, non-numeric) then valid → returns project."""
    responses = iter(["99", "abc", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    result = cli.project_resolver.interactive_pick(["alpha", "beta"], "Pick one:")
    assert result == "alpha"


def test_interactive_pick_exhausted(monkeypatch):
    """Three consecutive bad inputs → ActionError."""
    monkeypatch.setattr("builtins.input", lambda _: "99")
    try:
        cli.project_resolver.interactive_pick(["alpha", "beta"], "Pick one:")
        assert False, "should have raised ActionError"
    except cli.ProjectResolutionError as e:
        assert "aborted" in str(e) or "invalid" in str(e)


def test_interactive_pick_blank(monkeypatch):
    """Blank input → ActionError immediately."""
    monkeypatch.setattr("builtins.input", lambda _: "")
    try:
        cli.project_resolver.interactive_pick(["alpha", "beta"], "Pick one:")
        assert False, "should have raised ActionError"
    except cli.ProjectResolutionError as e:
        assert "cancelled" in str(e)


def test_interactive_pick_ctrl_c(monkeypatch):
    """EOFError from input → ActionError (Ctrl-C / EOF behaviour)."""
    def raise_eof(_):
        raise EOFError
    monkeypatch.setattr("builtins.input", raise_eof)
    try:
        cli.project_resolver.interactive_pick(["alpha", "beta"], "Pick one:")
        assert False, "should have raised ActionError"
    except cli.ProjectResolutionError as e:
        assert "cancelled" in str(e)


# ---------- resolve_project_with_picker ----------

def test_no_prompt_skips_picker_even_with_tty(monkeypatch, tmp_path):
    """isatty=True but --no-prompt → hard error (no picker)."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    # cwd not in any known project dir, no --project
    monkeypatch.chdir(tmp_path)
    args = _args(no_prompt=True)
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "no project resolved" in str(e)


def test_non_tty_skips_picker(monkeypatch, tmp_path):
    """isatty=False, no --no-prompt → hard error (no picker)."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    monkeypatch.chdir(tmp_path)
    args = _args()
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert "no project resolved" in str(e)


def test_unknown_project_with_tty(monkeypatch, tmp_path):
    """--project typo + isatty=True → picker fires, returns selected project."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    (tmp_path / "alpha.yaml").write_text("")
    (tmp_path / "beta.yaml").write_text("")
    monkeypatch.setattr("builtins.input", lambda _: "1")
    args = _args(project="typo-project")
    result = cli.resolve_project_with_picker(args)
    assert result == "alpha"


def test_unknown_project_without_tty(monkeypatch, tmp_path):
    """--project typo + isatty=False + no disk dir → ActionError with Rule 3 message."""
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", tmp_path)
    # Redirect HOME so project_dir_exists("typo-project") → False
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(cli.project_resolver, "HOME", fake_home)
    # Also redirect SUBSCRIPTIONS_PATH so read_subscriptions returns []
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", tmp_path / "subs.json")
    (tmp_path / "alpha.yaml").write_text("")
    args = _args(project="typo-project")
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        assert 'unknown project "typo-project"' in str(e)
        assert "not registered" in str(e)


def test_resolve_cwd_projects_subdir(monkeypatch, tmp_path):
    """cwd = ~/projects/buddy/subdir → resolve_project returns 'buddy'."""
    buddy_sub = tmp_path / "projects" / "buddy" / "subdir"
    buddy_sub.mkdir(parents=True)
    monkeypatch.setattr(cli.project_resolver, "HOME", tmp_path)
    monkeypatch.chdir(buddy_sub)
    args = _args()
    result = cli.resolve_project(args)
    assert result == "buddy"


# ---------- project_dir_exists ----------

def test_project_dir_exists_agents(monkeypatch, tmp_path):
    """project_dir_exists('agents') returns True when HOME/agents/ exists."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setattr(cli.project_resolver, "HOME", tmp_path)
    assert cli.project_dir_exists("agents") is True


def test_project_dir_exists_regular(monkeypatch, tmp_path):
    """project_dir_exists('foo') returns True when HOME/projects/foo/ exists."""
    (tmp_path / "projects" / "foo").mkdir(parents=True)
    monkeypatch.setattr(cli.project_resolver, "HOME", tmp_path)
    assert cli.project_dir_exists("foo") is True


def test_project_dir_exists_missing(monkeypatch, tmp_path):
    """project_dir_exists('bar') returns False when HOME/projects/bar/ does not exist."""
    monkeypatch.setattr(cli.project_resolver, "HOME", tmp_path)
    assert cli.project_dir_exists("bar") is False


# ---------- read_subscriptions ----------

def test_read_subscriptions_normal(monkeypatch, tmp_path):
    """Valid JSON with subscribed list → returns list of strings."""
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["agents", "paul-jason"]}')
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    result = cli.read_subscriptions()
    assert result == ["agents", "paul-jason"]


def test_read_subscriptions_missing_file(monkeypatch, tmp_path):
    """Missing subscriptions file → returns []."""
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", tmp_path / "nonexistent.json")
    assert cli.read_subscriptions() == []


def test_read_subscriptions_empty_array(monkeypatch, tmp_path):
    """subscribed: [] → returns []."""
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": []}')
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    assert cli.read_subscriptions() == []


# ---------- add_subscription ----------

def test_add_subscription_creates_file(monkeypatch, tmp_path):
    """add_subscription creates file if absent and writes [name]."""
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    cli.add_subscription("sweetprocess")
    import json as _json
    data = _json.loads(subs_file.read_text())
    assert data["subscribed"] == ["sweetprocess"]


def test_add_subscription_appends(monkeypatch, tmp_path):
    """add_subscription appends to existing list and does not duplicate."""
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["agents"]}')
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    cli.add_subscription("sweetprocess")
    cli.add_subscription("sweetprocess")  # second call must not duplicate
    import json as _json
    data = _json.loads(subs_file.read_text())
    assert data["subscribed"] == ["agents", "sweetprocess"]


# ---------- register_project ----------

def test_register_project_creates_yaml(monkeypatch, tmp_path):
    """register_project writes correct yaml defaults and calls add_subscription."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    subs_file = tmp_path / "subs.json"
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)

    result_path = cli.register_project("myproj")

    assert result_path == projects_dir / "myproj.yaml"
    content = result_path.read_text()
    assert "project: myproj" in content
    assert "status: active" in content
    assert 'focus: ""' in content
    assert 'updated_at: "' in content  # must be quoted
    assert "updated_by: jason" in content

    import json as _json
    subs = _json.loads(subs_file.read_text())
    assert "myproj" in subs["subscribed"]


def test_register_project_already_exists(monkeypatch, tmp_path):
    """register_project raises FileExistsError if yaml already exists."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "existing.yaml").write_text("project: existing\n")
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    try:
        cli.register_project("existing")
        assert False, "should have raised FileExistsError"
    except FileExistsError:
        pass


# ---------- list_known_projects with subscriptions ----------

def test_list_known_projects_filters_subs(monkeypatch, tmp_path):
    """list_known_projects returns only registered+subscribed projects."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    for name in ["alpha", "beta", "gamma"]:
        (projects_dir / f"{name}.yaml").write_text("")
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["alpha", "gamma"]}')
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    result = cli.list_known_projects()
    assert result == ["alpha", "gamma"]


def test_list_known_projects_empty_subs_fallback(monkeypatch, tmp_path):
    """list_known_projects returns all registered when subscriptions are empty."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    for name in ["alpha", "beta"]:
        (projects_dir / f"{name}.yaml").write_text("")
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": []}')
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    result = cli.list_known_projects()
    assert result == ["alpha", "beta"]


# ---------- auto-register on resolve ----------

def test_auto_register_on_resolve(monkeypatch, tmp_path, capsys):
    """resolve_project_with_picker auto-registers when disk dir exists for unknown project."""
    # Setup: HOME with projects/newproj dir, knowledge/projects dir, subs file
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (tmp_path / "projects" / "newproj").mkdir()
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    subs_file = tmp_path / "subs.json"

    monkeypatch.setattr(cli.project_resolver, "HOME", tmp_path)
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", knowledge_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)

    args = _args(project="newproj", no_prompt=True)
    result = cli.resolve_project_with_picker(args)

    assert result == "newproj"
    captured = capsys.readouterr()
    assert 'registered new project "newproj"' in captured.out
    assert (knowledge_dir / "newproj.yaml").exists()


def test_no_disk_dir_no_tty_error_message(monkeypatch, tmp_path):
    """No disk dir, not tty → ActionError with Rule 3 text."""
    projects_dir = tmp_path / "knowledge"
    projects_dir.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    subs_file = tmp_path / "subs.json"
    subs_file.write_text('{"subscribed": ["agents"]}')

    monkeypatch.setattr(cli.project_resolver, "HOME", fake_home)
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cli.project_resolver, "SUBSCRIPTIONS_PATH", subs_file)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)

    args = _args(project="ghostproject", no_prompt=True)
    try:
        cli.resolve_project_with_picker(args)
        assert False, "should have raised ActionError"
    except cli.ActionError as e:
        msg = str(e)
        assert "not registered" in msg
        assert "no repo at" in msg
        assert "Subscribed on this machine:" in msg


# ---------- git helpers (unit tests) ----------

def _make_subprocess_mock(outcomes: list[tuple[int, str, str]]):
    """
    outcomes: list of (returncode, stdout, stderr) tuples consumed in order.
    Returns a callable suitable for monkeypatching subprocess.run.
    """
    import subprocess as _subprocess
    calls = list(outcomes)
    def _mock(*args, **kwargs):
        rc, out, err = calls.pop(0)
        return _subprocess.CompletedProcess(args[0] if args else [], rc, out, err)
    return _mock


_ACTIONS_CONTENT = """\
# Test Project ACTIONS

Next ID: **A-002**

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|-------|--------|-------|--------|--------|-----|-------|-------|
| A-001 | | Test action | Jason | open | 2026-01-01 | | | |

## Recently Closed

| ID | Issue | Action | Owner | Closed | Files | Notes |
|----|-------|--------|-------|--------|-------|-------|
"""


def _make_actions_file(tmp_path: Path) -> Path:
    """Write a minimal ACTIONS.md with one open row A-001 and marker A-002."""
    p = tmp_path / "ACTIONS.md"
    p.write_text(_ACTIONS_CONTENT)
    return p


def _patch_project(monkeypatch, tmp_path: Path):
    """Wire resolve_project_with_picker and project_path to use tmp_path."""
    actions_file = _make_actions_file(tmp_path)
    monkeypatch.setattr(cli, "resolve_project_with_picker", lambda args: "testproject")
    monkeypatch.setattr(cli, "project_path", lambda name: actions_file)
    return actions_file


# T1: --new triggers subprocess in the right order (detect, branch, pull, branch, add, commit, push)
def test_new_calls_git_pull_commit_push(monkeypatch, tmp_path):
    """main() with --new calls subprocess for detect, pull, add, commit, push; exit 0."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    original_content = actions_file.read_text()

    # Outcomes in call order:
    # 1. rev-parse --show-toplevel (detect_repo → success)
    # 2. rev-parse --abbrev-ref HEAD (current_branch for pull → "main")
    # 3. pull --rebase (→ success)
    # 4. rev-parse --abbrev-ref HEAD (current_branch for commit_and_push → "main")
    # 5. git add (→ success)
    # 6. git commit (→ success)
    # 7. git push --force-with-lease (→ success)
    outcomes = [
        (0, "", ""),   # rev-parse --show-toplevel
        (0, "main\n", ""),  # rev-parse --abbrev-ref HEAD (pull)
        (0, "", ""),   # pull --rebase
        (0, "main\n", ""),  # rev-parse --abbrev-ref HEAD (push)
        (0, "", ""),   # git add
        (0, "1 file changed", ""),  # git commit
        (0, "", ""),   # git push
    ]
    mock_called = []
    import subprocess as _subprocess

    def _recording_mock(*args, **kwargs):
        rc, out, err = outcomes[len(mock_called)]
        mock_called.append(args[0] if args else [])
        return _subprocess.CompletedProcess(args[0] if args else [], rc, out, err)

    monkeypatch.setattr(cli.subprocess, "run", _recording_mock)

    rc = cli.main(["--new", "Test new action", "--owner", "Jason", "--no-prompt"])
    assert rc == 0
    # File must have been written (new row added)
    new_content = actions_file.read_text()
    assert "A-002" in new_content
    assert "Test new action" in new_content
    # subprocess must have been called (pull + push path)
    assert len(mock_called) > 0
    # push with --force-with-lease must appear
    all_args = [str(a) for call in mock_called for a in call]
    assert "--force-with-lease" in all_args


# T2: --no-commit skips all git, file still written
def test_no_commit_skips_all_git(monkeypatch, tmp_path):
    """--no-commit: subprocess never called; file written; exit 0."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    called = []
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: called.append(a) or (_ for _ in ()).throw(AssertionError("subprocess.run called with --no-commit")))

    # Use a lambda that records and raises so we detect any call
    def no_git(*args, **kwargs):
        called.append(args)
        raise AssertionError(f"subprocess.run should not be called, got: {args}")

    monkeypatch.setattr(cli.subprocess, "run", no_git)

    rc = cli.main(["--new", "No-commit action", "--owner", "Jason", "--no-prompt", "--no-commit"])
    assert rc == 0
    assert "No-commit action" in actions_file.read_text()
    assert called == []


# T3: pull conflict → abort before write
def test_pull_conflict_aborts_write(monkeypatch, tmp_path, capsys):
    """pull returns conflict → file unchanged; stderr contains 'cannot sync ACTIONS.md'; exit 1."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    original_content = actions_file.read_text()

    import subprocess as _subprocess
    outcomes = [
        (0, "", ""),           # rev-parse --show-toplevel (detect)
        (0, "main\n", ""),     # rev-parse --abbrev-ref HEAD (branch)
        (1, "CONFLICT (content): Merge conflict in ACTIONS.md", "CONFLICT"),  # pull
    ]
    monkeypatch.setattr(cli.subprocess, "run", _make_subprocess_mock(outcomes))

    rc = cli.main(["--new", "Conflict action", "--owner", "Jason", "--no-prompt"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "cannot sync ACTIONS.md" in captured.err
    assert actions_file.read_text() == original_content  # file unchanged


# T4: pull network failure → warning printed, file written, push skipped
def test_pull_network_failure_warns_and_writes(monkeypatch, tmp_path, capsys):
    """pull returns network error → warning to stdout; file IS written; push NOT attempted; exit 0."""
    actions_file = _patch_project(monkeypatch, tmp_path)

    import subprocess as _subprocess
    call_count = [0]

    def _mock(*args, **kwargs):
        n = call_count[0]
        call_count[0] += 1
        if n == 0:
            return _subprocess.CompletedProcess(args[0], 0, "", "")   # detect
        if n == 1:
            return _subprocess.CompletedProcess(args[0], 0, "main\n", "")  # branch
        if n == 2:
            return _subprocess.CompletedProcess(args[0], 1, "", "Could not resolve host: github.com")  # pull fails
        raise AssertionError(f"unexpected subprocess call #{n}: {args[0]}")

    monkeypatch.setattr(cli.subprocess, "run", _mock)

    rc = cli.main(["--new", "Network action", "--owner", "Jason", "--no-prompt"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "offline" in captured.out or "WARNING" in captured.out
    assert "Network action" in actions_file.read_text()
    # Only 3 subprocess calls (detect + branch + pull); no push
    assert call_count[0] == 3


# T5: push rejected → abort with retry message, exit 1
def test_push_rejected_aborts_with_retry_message(monkeypatch, tmp_path, capsys):
    """pull succeeds; commit succeeds; push rejected → stderr 'push rejected'; exit 1."""
    actions_file = _patch_project(monkeypatch, tmp_path)

    import subprocess as _subprocess
    outcomes = [
        (0, "", ""),           # detect
        (0, "main\n", ""),     # branch (pull)
        (0, "", ""),           # pull
        (0, "main\n", ""),     # branch (push)
        (0, "", ""),           # git add
        (0, "1 file", ""),     # git commit
        (1, "", "rejected: non-fast-forward"),  # push rejected
    ]
    monkeypatch.setattr(cli.subprocess, "run", _make_subprocess_mock(outcomes))

    rc = cli.main(["--new", "Rejected action", "--owner", "Jason", "--no-prompt"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "push rejected" in captured.err


# T6: --strict + network failure → abort before write, exit 1
def test_strict_network_failure_aborts(monkeypatch, tmp_path, capsys):
    """--strict + pull network error: file unchanged; stderr 'cannot sync — offline'; exit 1."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    original_content = actions_file.read_text()

    import subprocess as _subprocess
    outcomes = [
        (0, "", ""),           # detect
        (0, "main\n", ""),     # branch
        (1, "", "Could not resolve host: github.com"),  # pull fails
    ]
    monkeypatch.setattr(cli.subprocess, "run", _make_subprocess_mock(outcomes))

    rc = cli.main(["--new", "Strict action", "--owner", "Jason", "--no-prompt", "--strict"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "cannot sync — offline" in captured.err
    assert actions_file.read_text() == original_content  # file must be unchanged


# T7: --list does NOT call subprocess
def test_list_does_not_call_git(monkeypatch, tmp_path):
    """main() with --list: subprocess never called; exit 0."""
    actions_file = _patch_project(monkeypatch, tmp_path)

    def no_git(*args, **kwargs):
        raise AssertionError(f"subprocess.run should not be called on --list, got: {args}")

    monkeypatch.setattr(cli.subprocess, "run", no_git)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0


# T8: show (A-001) does NOT call subprocess
def test_show_does_not_call_git(monkeypatch, tmp_path):
    """main() with A-001 (show): subprocess never called; exit 0."""
    actions_file = _patch_project(monkeypatch, tmp_path)

    def no_git(*args, **kwargs):
        raise AssertionError(f"subprocess.run should not be called on show, got: {args}")

    monkeypatch.setattr(cli.subprocess, "run", no_git)
    rc = cli.main(["A-001", "--no-prompt"])
    assert rc == 0


# T9: non-git directory → detect returns NOT_A_REPO → write succeeds, no further git calls
def test_non_git_dir_write_succeeds(monkeypatch, tmp_path):
    """rev-parse returns non-zero (not a git repo) → file still written; no further git calls."""
    actions_file = _patch_project(monkeypatch, tmp_path)

    import subprocess as _subprocess
    call_count = [0]

    def _mock(*args, **kwargs):
        n = call_count[0]
        call_count[0] += 1
        if n == 0:
            # rev-parse --show-toplevel → non-zero = not a git repo
            return _subprocess.CompletedProcess(args[0], 128, "", "not a git repository")
        raise AssertionError(f"unexpected subprocess call #{n} after non-git detect")

    monkeypatch.setattr(cli.subprocess, "run", _mock)

    rc = cli.main(["--new", "Non-git action", "--owner", "Jason", "--no-prompt"])
    assert rc == 0
    assert "Non-git action" in actions_file.read_text()
    # Only 1 call (the detect)
    assert call_count[0] == 1


# T10: stale marker → data wins → new item is A-004
def test_stale_marker_uses_data_id(monkeypatch, tmp_path):
    """ACTIONS.md has rows A-001, A-002, A-003 but marker says A-002; --new creates A-004."""
    stale_content = """\
# Stale Project

Next ID: **A-002**

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|-------|--------|-------|--------|--------|-----|-------|-------|
| A-001 | | Action one | Jason | open | 2026-01-01 | | | |
| A-002 | | Action two | Jason | open | 2026-01-02 | | | |
| A-003 | | Action three | Jason | open | 2026-01-03 | | | |

## Recently Closed

| ID | Issue | Action | Owner | Closed | Files | Notes |
|----|-------|--------|-------|--------|-------|-------|
"""
    actions_file = tmp_path / "ACTIONS.md"
    actions_file.write_text(stale_content)
    monkeypatch.setattr(cli, "resolve_project_with_picker", lambda args: "testproject")
    monkeypatch.setattr(cli, "project_path", lambda name: actions_file)

    # parse_next_id_from_data inline assertion
    assert cli.parse_next_id_from_data(stale_content) == 4  # max(1,2,3) + 1

    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: __import__("subprocess").CompletedProcess(a[0] if a else [], 128, "", "not a repo"))

    rc = cli.main(["--new", "Fourth action", "--owner", "Jason", "--no-prompt"])
    assert rc == 0
    new_content = actions_file.read_text()
    assert "A-004" in new_content
    # Marker must have been updated to A-005
    assert "A-005" in new_content


# ---------- --list rendering ----------

_RICH_ACTIONS_CONTENT = """\
# Rich Test Project

Next ID: **A-003**

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|-------|--------|-------|--------|--------|-----|-------|-------|
| A-001 | #42 | Short action | Jason | open | 2026-05-01 | M1 | /tmp/a.txt, /tmp/b.txt | |
| A-002 |  | This is a deliberately long action description that should exceed any reasonable terminal width budget so that the truncation logic kicks in and we can verify that the trailing ellipsis is appended correctly | Paul | wip | 2026-05-02 |  |  | |

## Recently Closed

| ID | Issue | Action | Owner | Closed | Files | Notes |
|----|-------|--------|-------|--------|-------|-------|
"""


def _patch_rich_project(monkeypatch, tmp_path: Path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_RICH_ACTIONS_CONTENT)
    monkeypatch.setattr(cli, "resolve_project_with_picker", lambda args: "rich")
    monkeypatch.setattr(cli, "project_path", lambda name: p)
    return p


def test_list_default_shows_metadata_columns(monkeypatch, tmp_path, capsys):
    """Default --list shows the wide tabular header with metadata columns."""
    _patch_rich_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    # First line is the section label "Open (N):"; second line is the header
    lines = out.splitlines()
    assert lines[0].startswith("Open (")
    header = next(line for line in lines if line.startswith("ID"))
    for col in ("ID", "Owner", "Status", "Opened", "Src", "Issue", "Files", "Action"):
        assert col in header, f"missing column {col!r} in header: {header!r}"


def test_list_default_renders_metadata_values(monkeypatch, tmp_path, capsys):
    """Row data populates Opened, Src, Issue, Files (count) cells."""
    _patch_rich_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    a001 = next(line for line in out.splitlines() if line.startswith("A-001"))
    # row populated: opened date, src, issue link, files count = 2
    assert "2026-05-01" in a001
    assert "M1" in a001
    assert "#42" in a001
    assert " 2 " in a001 or a001.endswith(" 2") or " 2  " in a001  # files count


def test_list_dash_for_empty_metadata(monkeypatch, tmp_path, capsys):
    """A row with no Issue/Src/Files renders '-' in those cells."""
    _patch_rich_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    a002 = next(line for line in out.splitlines() if line.startswith("A-002"))
    # Issue, Src, Files are all empty for A-002 → all rendered as "-"
    # Action text is long so it appears at the end; the metadata block before it must contain "-"
    assert "-" in a002


def test_list_short_keeps_compact_format(monkeypatch, tmp_path, capsys):
    """--short preserves the legacy compact format (no header row)."""
    _patch_rich_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--short", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    # No header row in short mode
    assert not lines[0].startswith("ID "), f"unexpected header in --short output: {lines[0]!r}"
    # First line is A-001 row, compact 4-col format
    assert lines[0].startswith("A-001  Jason")


def test_list_default_truncates_long_action(monkeypatch, tmp_path, capsys):
    """Default --list truncates a long Action with an ellipsis."""
    _patch_rich_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    # Force a small terminal so truncation is guaranteed
    monkeypatch.setattr(cli.shutil, "get_terminal_size", lambda fallback=(120, 24): __import__("os").terminal_size((100, 24)))
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    a002 = next(line for line in out.splitlines() if line.startswith("A-002"))
    assert a002.endswith("…"), f"expected trailing ellipsis on truncated row: {a002!r}"


def test_list_no_trunc_preserves_full_action_text(monkeypatch, tmp_path, capsys):
    """--no-trunc emits the full Action text regardless of terminal width."""
    _patch_rich_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cli.shutil, "get_terminal_size", lambda fallback=(120, 24): __import__("os").terminal_size((80, 24)))
    rc = cli.main(["--list", "--no-trunc", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    a002 = next(line for line in out.splitlines() if line.startswith("A-002"))
    assert "trailing ellipsis is appended correctly" in a002
    assert not a002.endswith("…")


# ---------- open/closed split + Opened column on closed (A-013-style) ----------

_MIXED_ACTIONS_CONTENT = """\
# Mixed Test Project

Next ID: **A-005**

## Open

| ID | Issue | Action | Owner | Status | Opened | Src | Files | Notes |
|----|-------|--------|-------|--------|--------|-----|-------|-------|
| A-001 | #42 | Open action | Jason | open | 2026-05-01 |  |  | |

## Recently Closed

| ID | Issue | Action | Owner | Opened | Closed | Files | Notes |
|----|-------|--------|-------|--------|--------|-------|-------|
| A-002 |  | Recently closed | Jason | 2026-05-01 | 2026-05-05 |  | |
"""


def _patch_mixed_project(monkeypatch, tmp_path: Path):
    p = tmp_path / "ACTIONS.md"
    p.write_text(_MIXED_ACTIONS_CONTENT)
    monkeypatch.setattr(cli, "resolve_project_with_picker", lambda args: "mixed")
    monkeypatch.setattr(cli, "project_path", lambda name: p)
    return p


def test_list_default_open_only_has_no_closed_section(monkeypatch, tmp_path, capsys):
    _patch_mixed_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Open (1):" in out
    assert "Closed (" not in out
    assert "A-001" in out
    assert "A-002" not in out


def test_list_closed_only(monkeypatch, tmp_path, capsys):
    _patch_mixed_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--closed", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Closed (1):" in out
    assert "Open (" not in out
    # Closed table must surface BOTH Opened and Closed columns now
    header = next(line for line in out.splitlines() if line.startswith("ID"))
    assert "Opened" in header and "Closed" in header
    a002 = next(line for line in out.splitlines() if line.startswith("A-002"))
    assert "2026-05-01" in a002  # Opened
    assert "2026-05-05" in a002  # Closed


def test_list_all_renders_two_distinct_tables(monkeypatch, tmp_path, capsys):
    _patch_mixed_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--list", "--all", "--no-prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Open (1):" in out
    assert "Closed (1):" in out
    # Open should appear before Closed in output
    assert out.index("Open (1):") < out.index("Closed (1):")
    assert "A-001" in out
    assert "A-002" in out


# ---------- close-flow forwards Opened (A-013-style) ----------

def test_close_open_action_carries_opened_to_closed_table(monkeypatch, tmp_path):
    """When `action A-NNN --status done` moves a row, the original Opened
    date must travel with it so duration stays queryable."""
    p = tmp_path / "ACTIONS.md"
    p.write_text(_MIXED_ACTIONS_CONTENT)
    monkeypatch.setattr(cli, "resolve_project_with_picker", lambda args: "mixed")
    monkeypatch.setattr(cli, "project_path", lambda name: p)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["A-001", "--status", "done", "--no-prompt", "--no-commit"])
    assert rc == 0
    text = p.read_text()
    # Find A-001's new row in Closed table; it should carry Opened=2026-05-01
    closed_lines = [line for line in text.splitlines() if line.startswith("| A-001")]
    assert len(closed_lines) == 1
    assert "2026-05-01" in closed_lines[0]  # original Opened preserved


# ---------- --new capture parity (cap → action consolidation) ----------

def _patch_empty_project(monkeypatch, tmp_path: Path) -> Path:
    """Project dir exists but ACTIONS.md is missing (auto-template creation case)."""
    project_dir = tmp_path / "newproj"
    project_dir.mkdir()
    actions_file = project_dir / "ACTIONS.md"
    monkeypatch.setattr(cli, "resolve_project_with_picker", lambda args: "newproj")
    monkeypatch.setattr(cli, "project_path", lambda name: actions_file)
    return actions_file


def test_new_default_owner_is_jason(monkeypatch, tmp_path):
    """--new without --owner defaults to 'Jason' (cap parity)."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--new", "owner-default", "--no-prompt", "--no-commit"])
    assert rc == 0
    assert "owner-default" in actions_file.read_text()
    # Owner cell holds "Jason"
    assert "| Jason |" in actions_file.read_text()


def test_new_multi_row_positional(monkeypatch, tmp_path):
    """--new with multiple positionals creates one row per text in a single batch."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--new", "alpha", "beta", "gamma", "--no-prompt", "--no-commit"])
    assert rc == 0
    text = actions_file.read_text()
    assert "alpha" in text and "beta" in text and "gamma" in text
    # 3 new rows + 1 existing fixture row = 4 lines starting with `| A-`
    open_rows = [ln for ln in text.splitlines() if ln.startswith("| A-")]
    assert len(open_rows) == 4


def test_new_stdin_when_flag_takes_no_value(monkeypatch, tmp_path):
    """`echo ... | action --new` reads from stdin (one row per line)."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    import io
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("piped one\npiped two\n"))
    # Force isatty=False on the patched stdin (StringIO has no isatty by default)
    cli.sys.stdin.isatty = lambda: False
    rc = cli.main(["--new", "--no-prompt", "--no-commit"])
    assert rc == 0
    text = actions_file.read_text()
    assert "piped one" in text and "piped two" in text


def test_new_auto_creates_actions_md_from_template(monkeypatch, tmp_path):
    """When ACTIONS.md is missing, --new bootstraps it from the v2 template (cap parity)."""
    actions_file = _patch_empty_project(monkeypatch, tmp_path)
    assert not actions_file.exists()
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--new", "first ever action", "--no-prompt", "--no-commit"])
    assert rc == 0
    text = actions_file.read_text()
    assert "## Open" in text
    assert "## Recently Closed" in text
    assert "## Archive" in text
    assert "Files" in text  # v2 schema (Files column present)
    assert "first ever action" in text
    assert "A-001" in text


def test_new_short_p_flag_resolves_project(monkeypatch, tmp_path):
    """`-p NAME` works as a short form of `--project NAME`."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--new", "p-short", "-p", "testproject", "--no-prompt", "--no-commit"])
    assert rc == 0
    assert "p-short" in actions_file.read_text()


def test_new_editor_requires_tty(monkeypatch, tmp_path, capsys):
    """--editor errors clearly when stdin is not a TTY."""
    _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    rc = cli.main(["--new", "--editor", "--no-prompt", "--no-commit"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "TTY" in err or "tty" in err


def test_new_interactive_requires_tty(monkeypatch, tmp_path, capsys):
    """--interactive errors clearly when stdin is not a TTY."""
    _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    rc = cli.main(["--new", "--interactive", "--no-prompt", "--no-commit"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "TTY" in err or "tty" in err


def test_new_editor_and_interactive_mutex(monkeypatch, tmp_path, capsys):
    """--editor and --interactive together is rejected."""
    _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    rc = cli.main(["--new", "--editor", "--interactive", "--no-prompt", "--no-commit"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "mutually exclusive" in err


def test_new_editor_writes_rows_from_temp_file(monkeypatch, tmp_path):
    """Happy path: editor template + parsed rows become ACTIONS.md entries."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)

    def _fake_editor(argv, *a, **kw):
        # argv[1] is the temp file path. Append two action lines to it.
        editor_tmp = Path(argv[1])
        editor_tmp.write_text(
            "# This is the template comment\n"
            "from editor one\n"
            "from editor two\n"
            "# Another comment\n"
        )
        import subprocess as _sp
        return _sp.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cli.subprocess, "run", _fake_editor)

    rc = cli.main(["--new", "--editor", "--no-prompt", "--no-commit"])
    assert rc == 0
    text = actions_file.read_text()
    assert "from editor one" in text
    assert "from editor two" in text
    # Comment lines must be skipped
    assert "This is the template comment" not in text


def test_new_interactive_loop_writes_until_blank(monkeypatch, tmp_path):
    """--interactive prompts until a blank Action and writes all collected rows."""
    actions_file = _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)

    inputs = iter(["repl one", "repl two", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    rc = cli.main(["--new", "--interactive", "--no-prompt", "--no-commit"])
    assert rc == 0
    text = actions_file.read_text()
    assert "repl one" in text
    assert "repl two" in text


def test_new_no_input_raises(monkeypatch, tmp_path, capsys):
    """--new with no positionals, no stdin, no editor/interactive errors."""
    _patch_project(monkeypatch, tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    rc = cli.main(["--new", "--no-prompt", "--no-commit"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no actions" in err.lower()


def test_commit_message_for_add_list_of_ids():
    """_commit_message_for handles list[str] for multi-row adds."""
    # single-element list renders as the bare ID
    assert cli._commit_message_for("add", ["A-008"], owner="Jason") == "chore(action): add A-008 (Jason)"
    # ≤3 IDs joined with commas
    assert (
        cli._commit_message_for("add", ["A-008", "A-009", "A-010"], owner="Jason")
        == "chore(action): add A-008, A-009, A-010 (Jason)"
    )
    # >3 IDs collapsed to range + count
    assert (
        cli._commit_message_for("add", ["A-008", "A-009", "A-010", "A-011"], owner="Jason")
        == "chore(action): add A-008..A-011 (4 actions) (Jason)"
    )
    # Backwards-compat: bare string still works
    assert cli._commit_message_for("add", "A-001") == "chore(action): add A-001"


# T11: _commit_message_for verb table
def test_commit_message_for_verbs():
    """Unit test _commit_message_for for all documented verb patterns."""
    assert cli._commit_message_for("add", "A-008", owner="Jason") == "chore(action): add A-008 (Jason)"
    assert cli._commit_message_for("close", "A-005", status="done") == "chore(action): close A-005 → done"
    assert cli._commit_message_for("reopen", "A-003") == "chore(action): reopen A-003"
    assert cli._commit_message_for("note", "A-002") == "chore(action): note on A-002"
    assert cli._commit_message_for("update", "A-005") == "chore(action): update A-005"
    # owner-only add (no owner)
    assert cli._commit_message_for("add", "A-001") == "chore(action): add A-001"
