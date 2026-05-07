"""Tests for review-session/cli.py — pending review flow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Repo root on path so we can import review_session.cli + lib.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import review_session.cli as cli  # noqa: E402


# ---------- fixtures ----------

_SAMPLE = {
    "buddy": {
        "commits": [
            {"sha": "aaa", "message": "feat: A"},
            {"sha": "bbb", "message": "fix: B"},
        ],
        "current_focus": "Buddy current",
        "session_end": "2026-05-04T10:00:00",
    },
    "agents": {
        "commits": [
            {"sha": "ccc", "message": "chore: C"},
        ],
        "current_focus": "Agents current",
        "session_end": "2026-05-05T10:00:00",
    },
}


def _wire_paths(monkeypatch, tmp_path: Path, *, with_pending: dict | None = None,
                register: tuple[str, ...] = ("buddy", "agents")):
    """Redirect PENDING_REVIEWS_PATH and KNOWLEDGE_PROJECTS_DIR to tmp_path.

    If with_pending is given, write it to the pending file. If register is
    non-empty, create empty <name>.yaml files so project_yaml_path(name).exists()
    returns True.
    """
    pending_path = tmp_path / "pending_focus_reviews.json"
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    for name in register:
        (projects_dir / f"{name}.yaml").write_text(
            f"project: {name}\nstatus: active\nfocus: ''\n"
        )
    if with_pending is not None:
        pending_path.write_text(json.dumps(with_pending))

    monkeypatch.setattr(cli, "PENDING_REVIEWS_PATH", pending_path)
    # Test-pollution gotcha: lib functions read from lib's own constants,
    # so monkeypatch the lib namespace, not cli's.
    monkeypatch.setattr(cli.project_resolver, "KNOWLEDGE_PROJECTS_DIR", projects_dir)
    return pending_path, projects_dir


def _stub_subprocess_capture(monkeypatch):
    """Replace subprocess.run with a recorder. Returns the call list."""
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False):
        calls.append(list(cmd))
        return _FakeResult(0, "", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return calls


class _FakeResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub_inputs(monkeypatch, responses: list[str]):
    """Feed deterministic answers to cli.prompt(). Mutates `responses`."""
    queue = list(responses)

    def fake_prompt(text):
        if not queue:
            raise AssertionError(f"unexpected extra prompt: {text!r}")
        return queue.pop(0)

    monkeypatch.setattr(cli, "prompt", fake_prompt)
    return queue


# ---------- no-pending paths ----------

def test_no_pending_file_returns_clean_message(monkeypatch, tmp_path, capsys):
    _wire_paths(monkeypatch, tmp_path)  # no file written
    rc = cli.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "all caught up" in out


def test_empty_pending_returns_clean_message(monkeypatch, tmp_path, capsys):
    _wire_paths(monkeypatch, tmp_path, with_pending={})
    rc = cli.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "all caught up" in out


def test_corrupt_pending_errors(monkeypatch, tmp_path, capsys):
    pending, _ = _wire_paths(monkeypatch, tmp_path)
    pending.write_text("{not valid json")
    rc = cli.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "could not parse" in err


def test_non_object_pending_errors(monkeypatch, tmp_path, capsys):
    pending, _ = _wire_paths(monkeypatch, tmp_path)
    pending.write_text("[1, 2, 3]")
    rc = cli.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "must be a JSON object" in err


# ---------- --list mode ----------

def test_list_mode_prints_summary(monkeypatch, tmp_path, capsys):
    _wire_paths(monkeypatch, tmp_path, with_pending=_SAMPLE)
    rc = cli.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 projects pending review" in out
    assert "buddy" in out and "2 commits" in out
    assert "agents" in out and "1 commit " in out  # singular


def test_list_mode_does_not_prompt(monkeypatch, tmp_path):
    _wire_paths(monkeypatch, tmp_path, with_pending=_SAMPLE)

    def boom(text):
        raise AssertionError(f"--list must not prompt, got: {text!r}")

    monkeypatch.setattr(cli, "prompt", boom)
    rc = cli.main(["--list"])
    assert rc == 0


def test_list_mode_empty(monkeypatch, tmp_path, capsys):
    _wire_paths(monkeypatch, tmp_path)
    rc = cli.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "all caught up" in out


# ---------- apply path ----------

def test_apply_calls_project_cli(monkeypatch, tmp_path, capsys):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending={"buddy": _SAMPLE["buddy"]})
    calls = _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["a", "New buddy focus"])

    rc = cli.main([])
    assert rc == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("project/cli.py")
    assert cmd[2] == "buddy"
    assert "--focus" in cmd
    assert "New buddy focus" in cmd
    assert "--no-prompt" in cmd
    # Pending file should be deleted (only entry processed).
    assert not pending.exists()


def test_apply_failure_preserves_entry(monkeypatch, tmp_path, capsys):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending={"buddy": _SAMPLE["buddy"]})

    def fake_run(cmd, capture_output=False, text=False):
        return _FakeResult(1, "", "boom")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    _stub_inputs(monkeypatch, ["a", "Whatever"])

    rc = cli.main([])
    assert rc == 0  # main itself doesn't fail; it reports and quits the loop
    err = capsys.readouterr().err
    assert "apply failed" in err
    # Entry must remain pending so the user can retry.
    surviving = json.loads(pending.read_text())
    assert "buddy" in surviving


def test_empty_focus_treated_as_skip(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending={"buddy": _SAMPLE["buddy"]})
    calls = _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["a", ""])  # apply, then empty focus

    rc = cli.main([])
    assert rc == 0
    assert calls == []  # never called
    assert not pending.exists()  # entry was dropped


# ---------- skip / quit ----------

def test_skip_drops_entry(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending={"buddy": _SAMPLE["buddy"]})
    calls = _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["s"])

    rc = cli.main([])
    assert rc == 0
    assert calls == []
    assert not pending.exists()


def test_quit_preserves_remaining(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending=dict(_SAMPLE))
    calls = _stub_subprocess_capture(monkeypatch)
    # First project: skip. Second project: quit.
    _stub_inputs(monkeypatch, ["s", "q"])

    rc = cli.main([])
    assert rc == 0
    assert calls == []
    surviving = json.loads(pending.read_text())
    # Whichever project came second should still be pending.
    assert len(surviving) == 1


def test_quit_first_preserves_all(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending=dict(_SAMPLE))
    _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["q"])

    rc = cli.main([])
    assert rc == 0
    surviving = json.loads(pending.read_text())
    assert len(surviving) == 2


# ---------- file lifecycle ----------

def test_pending_deleted_when_empty(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending=dict(_SAMPLE))
    _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["s", "s"])  # skip both

    rc = cli.main([])
    assert rc == 0
    assert not pending.exists()


def test_atomic_write_no_temp_left(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending=dict(_SAMPLE))
    _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["s", "q"])

    rc = cli.main([])
    assert rc == 0
    leftover = list(pending.parent.glob("pending_focus_reviews.json.*tmp"))
    assert leftover == []


# ---------- specific-project arg ----------

def test_specific_project_arg(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending=dict(_SAMPLE))
    calls = _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["a", "Just buddy"])

    rc = cli.main(["buddy"])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0][2] == "buddy"
    surviving = json.loads(pending.read_text())
    assert "buddy" not in surviving
    assert "agents" in surviving  # untouched


def test_unknown_project_arg_errors(monkeypatch, tmp_path, capsys):
    _wire_paths(monkeypatch, tmp_path, with_pending=dict(_SAMPLE))
    rc = cli.main(["nonexistent"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no pending review" in err
    assert "nonexistent" in err


# ---------- registration / no-prompt ----------

def test_unregistered_project_skipped(monkeypatch, tmp_path, capsys):
    pending, _ = _wire_paths(
        monkeypatch, tmp_path,
        with_pending={"ghostproj": {"commits": [], "current_focus": "x"}},
        register=(),  # no yamls
    )
    calls = _stub_subprocess_capture(monkeypatch)

    rc = cli.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ghostproj.yaml not found" in out
    assert calls == []
    # Entry dropped (skip outcome).
    assert not pending.exists()


def test_no_prompt_skips_all(monkeypatch, tmp_path):
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending={"buddy": _SAMPLE["buddy"]})
    calls = _stub_subprocess_capture(monkeypatch)

    rc = cli.main(["--no-prompt"])
    assert rc == 0
    assert calls == []  # never invoked
    assert not pending.exists()  # entry dropped as skipped


# ---------- malformed entries ----------

def test_malformed_entry_skipped(monkeypatch, tmp_path, capsys):
    bad = {"buddy": "not-a-dict", "agents": _SAMPLE["agents"]}
    pending, _ = _wire_paths(monkeypatch, tmp_path, with_pending=bad)
    _stub_subprocess_capture(monkeypatch)
    _stub_inputs(monkeypatch, ["s"])  # skip the one valid entry

    rc = cli.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "malformed entry" in out
    assert not pending.exists()


# ---------- argparse smoke ----------

def test_parse_args_defaults():
    a = cli.parse_args([])
    assert a.project is None
    assert a.list is False
    assert a.no_prompt is False
