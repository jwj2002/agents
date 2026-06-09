#!/usr/bin/env python3
"""Weekly cost-telemetry report — build locally, then email per machine config.

Run by `com.cost-telemetry-report-weekly` (Mondays). It ALWAYS writes a local
report to ~/.claude/cost-reports/ (the archive/fallback); email delivery is on
top of that and only happens when ~/.claude/cost-telemetry/email.json is
configured + enabled (see usage_email). Never blocks; logs + exits 0.

Pipeline reuses the existing modules:
  usage_aggregator.read_shards + aggregate  ->  usage_report.write_report (html+md)
  ->  usage_email.send_weekly (transport selected by the machine-local config)
"""

from __future__ import annotations

import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import usage_aggregator as A  # noqa: E402
import usage_email as E  # noqa: E402
import usage_report as R  # noqa: E402

TELEMETRY_DIR = Path.home() / ".claude" / "telemetry"          # read_shards globs */usage.jsonl under here
REPORTS_DIR = Path.home() / ".claude" / "cost-reports"
EMAIL_STATE = Path.home() / ".claude" / "cost-telemetry" / "email-state.json"  # email-only state (no collector races)


def _host() -> str:
    try:
        sys.path.insert(0, str(Path.home() / "agents" / "lib"))
        from project_resolver import get_host_name
        return get_host_name()
    except Exception:
        return socket.gethostname().split(".")[0] or "unknown"


def _load_state() -> dict:
    try:
        return json.loads(EMAIL_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    EMAIL_STATE.parent.mkdir(parents=True, exist_ok=True)
    EMAIL_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = datetime.now(timezone.utc)
    host = _host()
    iso = now.isocalendar()
    wk = f"{iso[0]}-W{iso[1]:02d}"

    records = A.read_shards(TELEMETRY_DIR)
    agg = A.aggregate(records)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = REPORTS_DIR / f"cost-report-{host}-{wk}.html"
    R.write_report(agg, html_path, records=records)          # writes .html + .md
    md = html_path.with_suffix(".md").read_text(encoding="utf-8")  # email body = the local .md
    print(f"[{now.isoformat()}] local report: {html_path} ({len(records)} records)")

    state = _load_state()
    code, new_state = E.send_weekly(
        md_summary=md, html_path=str(html_path), state=state, host=host, now=now,
    )
    if code == E.SENT_OR_SKIP and new_state != state:
        _save_state(new_state)
    status = {
        E.SENT_OR_SKIP: "emailed (or already sent this week)",
        E.DISABLED: "email disabled — local report only",
        E.SEND_FAILED: "email FAILED (local report written)",
    }.get(code, str(code))
    print(f"[{now.isoformat()}] email: {status} (exit {code})")
    return 0  # never block the cadence


if __name__ == "__main__":
    raise SystemExit(main())
