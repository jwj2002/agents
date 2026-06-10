from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lib.agent_state import write_codex_checkpoint
from lib.context_budget import percent_remaining, severity_for


def test_context_budget_extracts_remaining_from_used_total() -> None:
    assert percent_remaining({"context_window": {"used": 75, "total": 100}}) == 25
    assert severity_for(25) == "CRITICAL"
    assert severity_for(35) == "WARNING"
    assert severity_for(80) == "NONE"


def test_write_codex_checkpoint_is_compact_yaml(tmp_path: Path) -> None:
    path = write_codex_checkpoint(
        tmp_path,
        {"session_id": "s1", "trigger": "auto", "message": "working issue #422"},
    )

    text = path.read_text(encoding="utf-8")
    assert "session_id: s1" in text
    assert "trigger: auto" in text
    assert "  - 422" in text


def test_codex_hook_wrappers_emit_json_or_nothing(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    payload = json.dumps({"session_id": "test", "context_percent_remaining": 20})
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    for script in sorted((repo / "codex-config" / "hooks").glob("*.py")):
        if script.name == "hook_common.py":
            continue
        completed = subprocess.run(
            [sys.executable, str(script)],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmp_path,
            env=env,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        output = completed.stdout.strip()
        if output:
            json.loads(output)
