"""Weekly cost-report email delivery (cost-telemetry-v0 §D5) — FAST-FOLLOW / cut-able.

The LOCAL report is the v0 gate; this only adds delivery. It is NOT triggered live by this module —
wiring the weekly job + the first real send is part of the deferred activation / joint smoke test.

`send_fn` is injectable so the real M365 send (`~/agents/m365/send_mail.py`) is decoupled and testable.
Idempotent (one send per ISO week, tracked in the collector state); a send failure logs + returns exit 4
and NEVER blocks collection. Always sends as jjob@vital-enterprises.com (never overrides the sender).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SENDER = "jjob@vital-enterprises.com"
DEFAULT_SEND_MAIL = Path.home() / "agents" / "m365" / "send_mail.py"
# Graph creds are NOT ambient under launchd — point at the token cache explicitly when activated.
DEFAULT_TOKEN_CACHE = Path.home() / ".claude" / "m365" / "token-cache.bin"


def _week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _default_send(*, subject: str, body: str, html_path, recipient: str) -> None:
    """Real send via the M365 helper. Raises on non-zero exit."""
    cmd = [
        sys.executable,
        str(DEFAULT_SEND_MAIL),
        "--to",
        recipient,
        "--subject",
        subject,
        "--body",
        body,
    ]
    if html_path:
        cmd += ["--attach", str(html_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"send_mail failed ({r.returncode}): {r.stderr.strip()}")


def send_weekly(
    *,
    md_summary: str,
    html_path,
    state: dict,
    host: str,
    recipient: str = SENDER,
    now: datetime | None = None,
    send_fn=None,
) -> tuple[int, dict]:
    """Send the weekly report if not already sent this ISO week.
    Returns (exit_code, updated_state): 0 = sent OR idempotent-skip; 4 = send failure (caller logs;
    collection is never blocked). State is only advanced on a successful send."""
    now = now or datetime.now(timezone.utc)
    wk = _week_key(now)
    if state.get("last_email_sent_week") == wk:
        return 0, state  # idempotent — already sent this week
    send = send_fn or _default_send
    subject = f"[cost-telemetry] {host} — week {wk}"
    try:
        send(subject=subject, body=md_summary, html_path=html_path, recipient=recipient)
    except Exception:
        return 4, state  # never block collection; caller logs the failure
    return 0, {**state, "last_email_sent_week": wk}
