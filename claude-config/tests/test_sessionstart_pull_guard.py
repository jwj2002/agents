"""Tests for the stamp-file pull-guard in sessionstart_restore_state (issue #407).

Injected dependencies (pattern from test_learn_deadman.py):
  - stamp_path  — tmp_path-relative Path
  - today_str   — fixed ISO date string
  - git_fn      — callable returning a mock result with .returncode

No live git or network calls.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import sessionstart_restore_state as H  # noqa: E402

TODAY = "2026-06-10"
YESTERDAY = "2026-06-09"


def _ok_result():
    """Return a mock subprocess result indicating success."""
    return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")


def _fail_result():
    """Return a mock subprocess result indicating failure."""
    return SimpleNamespace(returncode=1, stdout=b"", stderr=b"error")


# ---------------------------------------------------------------------------
# test_pull_runs_when_no_stamp
# ---------------------------------------------------------------------------

def test_pull_runs_when_no_stamp(tmp_path):
    stamp = tmp_path / ".agents-pull-stamp"
    calls = []

    def git_fn():
        calls.append("pull")
        return _ok_result()

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    result = H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    assert result is True
    assert len(calls) == 1, "git_fn should have been called once"
    assert stamp.exists(), "stamp must be written after successful pull"


# ---------------------------------------------------------------------------
# test_pull_skipped_when_stamp_is_today
# ---------------------------------------------------------------------------

def test_pull_skipped_when_stamp_is_today(tmp_path):
    stamp = tmp_path / ".agents-pull-stamp"
    # Write stamp and set its mtime to a time within TODAY (UTC noon).
    stamp.touch()
    ts = datetime.fromisoformat(f"{TODAY}T12:00:00+00:00").timestamp()
    os.utime(stamp, (ts, ts))

    calls = []

    def git_fn():
        calls.append("pull")
        return _ok_result()

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    result = H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    assert result is False, "_maybe_pull_agents should return False when skipping"
    assert calls == [], "git_fn must NOT be called when stamp is today"


# ---------------------------------------------------------------------------
# test_pull_runs_when_stamp_is_yesterday
# ---------------------------------------------------------------------------

def test_pull_runs_when_stamp_is_yesterday(tmp_path):
    stamp = tmp_path / ".agents-pull-stamp"
    stamp.touch()
    ts = datetime.fromisoformat(f"{YESTERDAY}T12:00:00+00:00").timestamp()
    os.utime(stamp, (ts, ts))

    calls = []

    def git_fn():
        calls.append("pull")
        return _ok_result()

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    result = H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    assert result is True
    assert len(calls) == 1, "git_fn should be called for a stale stamp"
    # stamp should be updated (touched)
    stamp_date = datetime.fromtimestamp(
        stamp.stat().st_mtime, tz=timezone.utc
    ).date().isoformat()
    assert stamp_date == TODAY, "stamp mtime must be updated to today after successful pull"


# ---------------------------------------------------------------------------
# test_stamp_not_written_on_pull_failure
# ---------------------------------------------------------------------------

def test_stamp_not_written_on_pull_failure(tmp_path):
    stamp = tmp_path / ".agents-pull-stamp"

    def git_fn():
        return _fail_result()

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    assert not stamp.exists(), "stamp must NOT be written when pull fails"


# ---------------------------------------------------------------------------
# test_stamp_not_written_on_timeout
# ---------------------------------------------------------------------------

def test_stamp_not_written_on_timeout(tmp_path):
    stamp = tmp_path / ".agents-pull-stamp"

    def git_fn():
        raise subprocess.TimeoutExpired(cmd=["git", "pull"], timeout=10)

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    # Must not raise
    H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    assert not stamp.exists(), "stamp must NOT be written on TimeoutExpired"


# ---------------------------------------------------------------------------
# test_advisory_printed_on_failure
# ---------------------------------------------------------------------------

def test_advisory_printed_on_failure(tmp_path, capsys):
    stamp = tmp_path / ".agents-pull-stamp"

    def git_fn():
        return _fail_result()

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    captured = capsys.readouterr()
    assert "Advisory" in captured.out, "advisory message must be printed on pull failure"
    assert "pull" in captured.out.lower(), "advisory must mention pull"


# ---------------------------------------------------------------------------
# test_offline_non_fatal
# ---------------------------------------------------------------------------

def test_offline_non_fatal(tmp_path):
    stamp = tmp_path / ".agents-pull-stamp"

    def git_fn():
        raise OSError("Network unreachable")

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    # Must not raise — fail-open behavior
    H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)  # no-raise

    assert not stamp.exists(), "stamp must not be written when offline"


# ---------------------------------------------------------------------------
# test_telemetry_gate_evaluated_when_pull_skipped
# ---------------------------------------------------------------------------

def test_telemetry_gate_evaluated_independently(tmp_path, capsys):
    """The telemetry gate runs inside the pull-success path.
    When pull is skipped (stamp is today), the gate is NOT invoked — this is
    intentional: the gate was already evaluated in the pull session that wrote
    the stamp.  This test verifies the gate is correctly called when pull runs.
    """
    stamp = tmp_path / ".agents-pull-stamp"

    def git_fn():
        return _ok_result()

    agents_root = tmp_path / "agents"
    agents_root.mkdir()

    # Create a fake telemetry_gate.py that prints a gate message
    gate_script = agents_root / "claude-config" / "scripts" / "telemetry_gate.py"
    gate_script.parent.mkdir(parents=True)
    gate_script.write_text(
        "import sys\nprint('gate tripped: run /learn')\nsys.exit(0)\n"
    )

    H._maybe_pull_agents(agents_root, stamp, TODAY, git_fn=git_fn)

    captured = capsys.readouterr()
    assert "gate tripped" in captured.out, (
        "telemetry gate output should appear when pull succeeds"
    )
