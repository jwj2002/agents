"""Tests for the edit_quality_feedback PostToolUse hook (issue #381)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import edit_quality_feedback as EQF  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_main(payload: dict, monkeypatch, capsys):
    """Pipe payload through main() and return captured stdout."""
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    try:
        EQF.main()
    except SystemExit:
        pass
    return capsys.readouterr().out


def _edit_payload(file_path: str, new_string: str = "") -> dict:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path, "new_string": new_string},
    }


def _write_payload(file_path: str, content: str = "") -> dict:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def _multiedit_payload(file_path: str, edits: list[dict]) -> dict:
    return {
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": file_path, "edits": edits},
    }


# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

def test_non_py_file_skipped(monkeypatch, capsys):
    """Write to a non-.py file produces no output."""
    # Mock ruff to ensure it is never called
    monkeypatch.setattr(EQF, "_ruff_check", lambda fp: (_ for _ in ()).throw(AssertionError("ruff called")))
    out = _run_main(_write_payload("file.js", "api_key = 'sk-abc123longvalue'"), monkeypatch, capsys)
    assert out == ""


def test_unknown_tool_skipped(monkeypatch, capsys):
    """A non-Edit/Write/MultiEdit tool produces no output."""
    payload = {"tool_name": "Read", "tool_input": {"file_path": "script.py"}}
    out = _run_main(payload, monkeypatch, capsys)
    assert out == ""


# ---------------------------------------------------------------------------
# ruff integration
# ---------------------------------------------------------------------------

def test_ruff_absent_skips_silently(monkeypatch, capsys):
    """When ruff is absent, ruff check is skipped; E15 still runs."""
    monkeypatch.setattr("shutil.which", lambda _: None)
    # No secret in content — expect empty output even without ruff
    out = _run_main(_edit_payload("script.py", "x = 1"), monkeypatch, capsys)
    assert "[ruff]" not in out


def test_ruff_finding_surfaces(monkeypatch, capsys):
    """A ruff finding line appears prefixed with [ruff] in stdout."""
    finding_line = "script.py:10:5: F841 Local variable `x` is assigned but never used"

    def _mock_run(cmd, **_kwargs):
        class R:
            stdout = finding_line
            returncode = 1
        return R()

    monkeypatch.setattr(subprocess, "run", _mock_run)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ruff")

    out = _run_main(_edit_payload("script.py", "x = 1"), monkeypatch, capsys)
    assert "[ruff]" in out
    assert "F841" in out
    assert "[edit_quality_feedback]" in out


def test_ruff_timeout_silently_skipped(monkeypatch, capsys):
    """TimeoutExpired from subprocess does not crash the hook; exit 0."""
    def _mock_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["ruff"], timeout=5)

    monkeypatch.setattr(subprocess, "run", _mock_run)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ruff")

    out = _run_main(_edit_payload("script.py", "x = 1"), monkeypatch, capsys)
    assert "[ruff]" not in out  # no crash, just silence


# ---------------------------------------------------------------------------
# E15 secret detection
# ---------------------------------------------------------------------------

def test_e15_secret_found(monkeypatch, capsys):
    """A hardcoded api_key literal triggers an E15 finding."""
    # Silence ruff so only E15 fires
    monkeypatch.setattr(EQF, "_ruff_check", lambda fp: [])

    secret_content = 'api_key = "sk-abc123xyz789longvalue"'
    out = _run_main(_edit_payload("script.py", secret_content), monkeypatch, capsys)
    assert "[E15]" in out
    assert "[edit_quality_feedback]" in out


def test_e15_allowlisted_line_skipped(monkeypatch, capsys):
    """A line with # eval-ok: E15 suppresses the E15 finding."""
    monkeypatch.setattr(EQF, "_ruff_check", lambda fp: [])

    # The allowlist comment is on the same line as the secret
    secret_content = 'api_key = "sk-abc123xyz789longvalue"  # eval-ok: E15 test fixture'
    out = _run_main(_edit_payload("script.py", secret_content), monkeypatch, capsys)
    assert "[E15]" not in out


# ---------------------------------------------------------------------------
# MultiEdit
# ---------------------------------------------------------------------------

def test_multiedit_joins_new_strings(monkeypatch, capsys):
    """MultiEdit joins all new_string values; a secret in any triggers E15."""
    monkeypatch.setattr(EQF, "_ruff_check", lambda fp: [])

    edits = [
        {"old_string": "foo", "new_string": "bar"},
        {"old_string": "baz", "new_string": 'api_key = "sk-secretlong99value"'},
    ]
    payload = _multiedit_payload("script.py", edits)
    out = _run_main(payload, monkeypatch, capsys)
    assert "[E15]" in out


# ---------------------------------------------------------------------------
# Clean path — no output
# ---------------------------------------------------------------------------

def test_clean_edit_no_output(monkeypatch, capsys):
    """Clean ruff + no secrets → stdout is empty."""
    monkeypatch.setattr(EQF, "_ruff_check", lambda fp: [])
    out = _run_main(_edit_payload("script.py", "x = 1 + 2"), monkeypatch, capsys)
    assert out == ""
