#!/usr/bin/env python3
"""Collection-request marker (cost-telemetry-v0 §D2): touch `.collect-requested`. The work is trivial
(a single touch); end to end as a spawned command hook it measures ~20ms (process startup dominates),
and it NEVER raises — a telemetry marker must not affect session exit.

⚠ NOT WIRED, and intentionally so. This was conceived as a `Stop` hook, but `Stop` fires at the end of
every assistant TURN (not at session end), and — more importantly — nothing consumes this marker: the
launchd collector runs on its own 6h timer and mines the transcript JSONLs by mtime, which already
captures resumed and multi-day sessions (a still-open session's transcript keeps a fresh mtime, so its
running cost is picked up every cycle). So the timer + transcript is the reliable source; this marker
adds nothing and is left dormant. If event-driven collection is ever wanted, wire a `SessionEnd` hook
(the correct "session ended" event) to kickstart the launchd job — do NOT use `Stop`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def request(base_dir=None) -> int:
    try:
        base = Path(base_dir) if base_dir else Path.home() / ".claude" / "telemetry"
        base.mkdir(parents=True, exist_ok=True)
        (base / ".collect-requested").touch()
    except Exception:
        pass  # never break session exit
    return 0


if __name__ == "__main__":
    sys.exit(request())
