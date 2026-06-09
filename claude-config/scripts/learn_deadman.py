"""Dead-man's switch for the learn loop (issue #359).

The learn-gate poller silently failed for months (`claude: command not found`
under launchd; before that, dirty-tree pull failures) while the gate sat
tripped with 40+ unconsumed failures. Nothing alerted. This module makes that
state loud: if the gate has been tripped for more than ALERT_AFTER_DAYS
without a successful /learn run, send an email via the machine-local
transport config (~/.claude/cost-telemetry/email.json, shared with the weekly
cost report — #355). No config -> log-only, never raises, never blocks the
poller.

State (machine-local, not committed): ~/.claude/learn-gate-deadman.json
  { "tripped_since": iso8601|null, "last_alert_at": iso8601|null }

CLI (called from learn-gate-poller.sh):
  learn_deadman.py trip    gate tripped but /learn did NOT complete this run
  learn_deadman.py clear   /learn succeeded (or gate is no longer tripped)
  learn_deadman.py status  print state as JSON

Stdlib-only so it runs under launchd's /usr/bin/python3. Email transport is
reused from usage_email (also stdlib-only).
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from usage_email import _default_send, load_email_config  # noqa: E402

STATE_PATH = Path.home() / ".claude" / "learn-gate-deadman.json"
ALERT_AFTER_DAYS = 7   # tripped this long without a successful learn -> alert
RATE_LIMIT_DAYS = 3    # at most one email per this many days


class DeadmanStateError(Exception):
    """State file exists but cannot be parsed (corrupt JSON / wrong shape)."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _host() -> str:
    name_file = Path.home() / ".claude" / "host-name"
    try:
        text = name_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    return socket.gethostname()


def load_state(path: Path | None = None) -> dict:
    """Read deadman state. Missing file -> fresh state. Corrupt file -> fresh
    state too (the deadman must never crash the poller), but the caller can
    distinguish via DeadmanStateError if it asks."""
    path = path or STATE_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {"tripped_since": None, "last_alert_at": None}
    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise DeadmanStateError(f"state is {type(state).__name__}, expected object")
    except (ValueError, DeadmanStateError):
        return {"tripped_since": None, "last_alert_at": None}
    state.setdefault("tripped_since", None)
    state.setdefault("last_alert_at", None)
    return state


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _alert_body(tripped_since: datetime, now: datetime, host: str) -> str:
    days = (now - tripped_since).days
    return (
        f"# Learn-loop dead-man alert — {host}\n\n"
        f"The learn gate has been TRIPPED for **{days} days** "
        f"(since {tripped_since.isoformat()}) without a successful /learn run.\n\n"
        "The self-learning loop is not consuming failures. Likely causes:\n"
        "- `claude` CLI not resolvable from the launchd environment\n"
        "- repo pull failing (dirty tree / auth)\n"
        "- /learn run crashing\n\n"
        "Check: `tail -50 ~/Library/Logs/claude-learn/poller.log`\n"
        "Then run manually: `claude --print '/learn --apply --cross-project --validate'`\n"
    )


def trip(
    *,
    now: datetime | None = None,
    state_path: Path | None = None,
    config: dict | None = None,
    send_fn=None,
) -> str:
    """Record a tripped-but-unconsumed gate; alert if it has been stuck too
    long. Returns a one-line status for the poller log. Never raises."""
    now = now or _utc_now()
    state = load_state(state_path)

    tripped_since = _parse_iso(state["tripped_since"])
    if tripped_since is None:
        tripped_since = now
        state["tripped_since"] = now.isoformat()
        save_state(state, state_path)
        return f"deadman: armed (tripped_since={now.isoformat()})"

    stuck_for = now - tripped_since
    if stuck_for < timedelta(days=ALERT_AFTER_DAYS):
        return f"deadman: armed, stuck {stuck_for.days}d (<{ALERT_AFTER_DAYS}d, no alert)"

    last_alert = _parse_iso(state["last_alert_at"])
    if last_alert is not None and (now - last_alert) < timedelta(days=RATE_LIMIT_DAYS):
        return f"deadman: stuck {stuck_for.days}d, alert rate-limited (last {last_alert.isoformat()})"

    config = config if config is not None else load_email_config()
    recipient = (config.get("recipient") or "").strip()
    account = config.get("account") or {}
    host = _host()
    if not config.get("enabled") or not recipient or account.get("type") in (None, "none"):
        return f"deadman: stuck {stuck_for.days}d, NO EMAIL CONFIG — alert is log-only"

    subject = f"[learn-loop] DEAD-MAN ALERT: gate tripped {stuck_for.days}d on {host}"
    body = _alert_body(tripped_since, now, host)
    send = send_fn or _default_send
    try:
        send(account=account, recipient=recipient, subject=subject, body=body, html_path=None)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return f"deadman: stuck {stuck_for.days}d, alert send FAILED ({type(exc).__name__})"
    state["last_alert_at"] = now.isoformat()
    save_state(state, state_path)
    return f"deadman: stuck {stuck_for.days}d, alert EMAILED to {recipient}"


def clear(*, state_path: Path | None = None) -> str:
    """Learn succeeded (or gate untripped): disarm. Never raises."""
    state = load_state(state_path)
    was_armed = state["tripped_since"] is not None
    if was_armed:
        save_state({"tripped_since": None, "last_alert_at": None}, state_path)
        return "deadman: cleared (learn loop healthy again)"
    return "deadman: idle"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "trip":
        print(trip())
    elif cmd == "clear":
        print(clear())
    elif cmd == "status":
        print(json.dumps(load_state(), indent=2))
    else:
        print(f"usage: learn_deadman.py trip|clear|status (got {cmd!r})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
