"""Tests for the cross-platform coding-memory maintenance SessionStart guard."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import coding_memory_maint as M  # noqa: E402


def _exe_wrapper(tmp_path):
    w = tmp_path / "w.sh"
    w.write_text("#!/bin/bash\n")
    w.chmod(0o755)
    return w


def test_skips_when_not_configured(tmp_path):
    calls = []
    ran = M.maybe_run(
        stamp_path=tmp_path / "s",
        today="2026-06-15",
        config_ok=False,
        spawn_fn=lambda w: calls.append(w),
        wrapper=_exe_wrapper(tmp_path),
    )
    assert ran is False and calls == []  # residency gate: never run unconfigured


def test_runs_when_due(tmp_path):
    calls = []
    stamp = tmp_path / "s"
    ran = M.maybe_run(
        stamp_path=stamp,
        today="2026-06-15",
        config_ok=True,
        spawn_fn=lambda w: calls.append(w),
        wrapper=_exe_wrapper(tmp_path),
    )
    assert ran is True and len(calls) == 1 and stamp.exists()


def test_skips_when_already_run_today(tmp_path):
    stamp = tmp_path / "s"
    stamp.touch()  # mtime = now -> today (local)
    today = datetime.now().date().isoformat()
    calls = []
    ran = M.maybe_run(
        stamp_path=stamp,
        today=today,
        config_ok=True,
        spawn_fn=lambda w: calls.append(w),
        wrapper=_exe_wrapper(tmp_path),
    )
    assert ran is False and calls == []  # at most once per day


def test_skips_when_wrapper_missing(tmp_path):
    calls = []
    ran = M.maybe_run(
        stamp_path=tmp_path / "s",
        today="2026-06-15",
        config_ok=True,
        spawn_fn=lambda w: calls.append(w),
        wrapper=tmp_path / "does-not-exist.sh",
    )
    # don't run (or stamp) if we can't execute it -> retry next session
    assert ran is False and calls == [] and not (tmp_path / "s").exists()


def test_config_ok_detects_personal_store(tmp_path):
    p = tmp_path / "cfg"
    assert M._config_ok(p) is False
    p.write_text("CODING_MEMORY_SSH=jns-server\n")
    assert M._config_ok(p) is True


def test_config_ok_ignores_comments_and_empty(tmp_path):
    p = tmp_path / "cfg"
    p.write_text("# CODING_MEMORY_SSH=jns-server\nDATABASE_URL=\n")
    assert M._config_ok(p) is False  # commented + empty value must not enable
