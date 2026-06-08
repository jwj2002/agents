#!/usr/bin/env python3
"""Stop-hook marker (cost-telemetry-v0 §D2): touch `.collect-requested` so the launchd collector
knows a session just ended and a scan is wanted. The work is trivial (a single touch); end to end as
a spawned command hook it measures ~20ms (process startup dominates), and it NEVER raises — a telemetry
marker must not affect session exit. The full scan runs under launchd, not here.

NOT wired into settings.json by this change — registering it as a Stop hook is part of the deferred
cost-telemetry activation / joint smoke test.
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
