"""Acceptance tests for issue #324 — launchd plist + Stop-hook touch script (cost-telemetry-v0 §D2).

These verify the ARTIFACTS are valid; they do NOT activate anything (no launchctl, no settings.json edit).
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import cost_collect_request as R  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
PLIST = _REPO / "claude-config" / "launchd" / "com.cost-telemetry-collect.plist"


def test_plist_exists_and_lints():
    assert PLIST.exists()
    if not (Path("/usr/bin/plutil").exists()):
        pytest.skip("plutil not available (non-macOS)")
    r = subprocess.run(
        ["/usr/bin/plutil", "-lint", str(PLIST)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_plist_schedule_and_no_api_keys():
    text = PLIST.read_text(encoding="utf-8")
    assert "<integer>21600</integer>" in text  # 6h StartInterval
    assert "PYTHONPATH" in text
    assert "<false/>" in text  # RunAtLoad false
    # must NOT bake an API key into launchd env (would force every row to 'metered')
    assert "ANTHROPIC_API_KEY" not in text and "OPENAI_API_KEY" not in text


def test_install_script_present_and_syntax_ok():
    sh = _REPO / "claude-config" / "scripts" / "install_cost_telemetry.sh"
    assert sh.exists()
    r = subprocess.run(["bash", "-n", str(sh)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_collect_request_touches_flag(tmp_path):
    assert R.request(tmp_path) == 0
    assert (tmp_path / ".collect-requested").exists()


def test_collect_request_never_raises_on_bad_dir():
    # a non-writable / bogus base must not raise (session-exit safety)
    assert R.request("/proc/nonexistent/cannot/create") == 0
