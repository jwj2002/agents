"""Recall-quality eval gate (manual / non-CI).

Invokes `coding-memory eval --json` against the LIVE store and asserts recall hasn't
regressed from the recorded baseline. Skips automatically where the store isn't
configured/reachable (e.g. CI), so it never blocks the normal suite. Run on a
configured machine with: `pytest -m eval lib/tests/test_coding_memory_recall_quality.py`

Baseline 2026-06-15 (n=9):  hybrid 8/8/8 · vector 8/8/8 · fts 4/4/4  (hit@1/@3/@5)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[2] / "bin" / "coding-memory"


@pytest.mark.eval
def test_recall_quality_not_regressed():
    if not Path(os.path.expanduser("~/.coding_memory.env")).exists():
        pytest.skip("coding-memory not configured on this host")
    if not BIN.exists():
        pytest.skip("coding-memory CLI not found")
    try:
        out = subprocess.run(
            [str(BIN), "eval", "--json"], capture_output=True, text=True, timeout=180
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        pytest.skip(f"eval unavailable: {e}")
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip(f"store unreachable / eval failed: {out.stderr[:200]}")

    data = json.loads(out.stdout)
    n = data["n"]
    # JSON keys are strings; hybrid is the production recall mode.
    hybrid_at3 = data["hybrid"]["3"]
    assert hybrid_at3 >= 7, f"hybrid hit@3 regressed: {hybrid_at3}/{n} (baseline 8)"
