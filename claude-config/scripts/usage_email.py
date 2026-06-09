"""Weekly cost-report email delivery — per-machine configurable account + transport.

The account to send FROM (type + sender + creds) and the recipient are read from
a machine-local config so each computer mails the right place:
  - personal laptop  -> gmail  / jasonwadejob@gmail.com
  - work laptop      -> m365   / jjob@vital-enterprises.com

Config (machine-local, NOT committed): ~/.claude/cost-telemetry/email.json
  {
    "enabled": true,
    "account": { "type": "gmail", "sender": "...", "creds": "~/agents/google/token.json" },
    "recipient": "..."
  }
JSON (stdlib) — also valid YAML — so it parses under launchd's /usr/bin/python3.
A committed `cost-telemetry-email.yaml.example` documents the shape.

Transports shell out to the existing send helpers (selected by `account.type`):
  gmail -> ~/agents/google/send_mail.py  (--token <creds>; sender = token account)
  m365  -> ~/agents/m365/send_mail.py    (--creds <creds>; sender = creds sender_upn)
  none  -> no send (caller writes a local report instead)

Each transport helper enforces its own recipient safety (e.g. m365 refuses
gmail recipients unless explicitly unblocked). The machine-local config file is
the authorization: send only when `enabled` is true and a recipient is set.
A send failure logs + returns nonzero and NEVER blocks collection. Idempotent:
one send per ISO week, tracked in the collector state. `send_fn` stays injectable
for tests.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "cost-telemetry" / "email.json"
VENV_PY = Path.home() / "agents" / ".venv" / "bin" / "python"
GMAIL_HELPER = Path.home() / "agents" / "google" / "send_mail.py"
M365_HELPER = Path.home() / "agents" / "m365" / "send_mail.py"
VALID_TYPES = ("gmail", "m365", "none")

# Exit codes (stable; used by the weekly job to decide local-report fallback):
SENT_OR_SKIP = 0     # sent this week, or idempotent skip
DISABLED = 3         # email not configured / disabled -> caller writes local report
SEND_FAILED = 4      # transport raised (logged; collection never blocked)


def _week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _python_bin() -> str:
    """Helpers need third-party libs (googleapiclient / msal+requests) from the
    repo venv; fall back to the current interpreter if the venv is absent."""
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def load_email_config(path: Path | None = None) -> dict:
    """Read the machine-local email config. Fail-safe: any problem -> disabled.

    Returns a dict with at least {"enabled": bool}. Never raises.
    """
    path = path or CONFIG_PATH
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": False}
    if not isinstance(cfg, dict):
        return {"enabled": False}
    cfg.setdefault("enabled", False)
    cfg.setdefault("account", {})
    return cfg


def _helper_argv(account: dict, *, recipient: str, subject: str, body: str, html_path) -> list[str] | None:
    """Build the send-helper argv for the account type, or None if unsendable."""
    atype = (account or {}).get("type", "none")
    creds = (account or {}).get("creds")
    creds = str(Path(creds).expanduser()) if creds else None
    if atype == "gmail":
        cmd = [_python_bin(), str(GMAIL_HELPER), "--to", recipient, "--subject", subject, "--body", body]
        if creds:
            cmd += ["--token", creds]
        if html_path:
            cmd += ["--attach", str(html_path)]
        return cmd
    if atype == "m365":
        cmd = [_python_bin(), str(M365_HELPER), "--to", recipient, "--subject", subject, "--body", body]
        if creds:
            cmd += ["--creds", creds]
        if html_path:
            cmd += ["--attach", str(html_path)]
        return cmd
    return None  # 'none' / unknown


def _default_send(*, account: dict, recipient: str, subject: str, body: str, html_path) -> None:
    """Real send via the configured transport helper. Raises on failure."""
    cmd = _helper_argv(account, recipient=recipient, subject=subject, body=body, html_path=html_path)
    if cmd is None:
        raise RuntimeError(f"no transport for account type {account.get('type')!r}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # Do not echo the helper's stdout (may contain addresses); type + code only.
        raise RuntimeError(f"send helper failed (exit {r.returncode})")


def send_weekly(
    *,
    md_summary: str,
    html_path,
    state: dict,
    host: str,
    config: dict | None = None,
    now: datetime | None = None,
    send_fn=None,
) -> tuple[int, dict]:
    """Send the weekly report per the machine-local config, if not already sent
    this ISO week. Returns (exit_code, updated_state). State advances only on a
    successful send. Never raises (collection is never blocked)."""
    now = now or datetime.now(timezone.utc)
    config = config if config is not None else load_email_config()

    recipient = (config.get("recipient") or "").strip()
    account = config.get("account") or {}
    if not config.get("enabled") or not recipient or account.get("type") in (None, "none"):
        return DISABLED, state  # caller writes a local report instead

    wk = _week_key(now)
    if state.get("last_email_sent_week") == wk:
        return SENT_OR_SKIP, state  # idempotent — already sent this week

    subject = f"[cost-telemetry] {host} — week {wk}"
    send = send_fn or _default_send
    try:
        send(account=account, recipient=recipient, subject=subject, body=md_summary, html_path=html_path)
    except Exception:
        return SEND_FAILED, state  # caller logs; collection never blocked
    return SENT_OR_SKIP, {**state, "last_email_sent_week": wk}


# ----------------------------------------------------------------- CLI

def _creds_default(atype: str) -> str:
    return {
        "gmail": "~/agents/google/token.json",
        "m365": "~/.claude/m365/agent.json",
    }.get(atype, "")


def cmd_configure() -> int:
    print("Configure the cost-telemetry weekly email for THIS machine.\n")
    atype = input(f"Account type {VALID_TYPES}: ").strip() or "none"
    if atype not in VALID_TYPES:
        print(f"invalid type {atype!r}; must be one of {VALID_TYPES}", file=sys.stderr)
        return 2
    cfg: dict = {"enabled": atype != "none", "account": {"type": atype}, "recipient": ""}
    if atype != "none":
        cfg["account"]["sender"] = input("Sender account (from address): ").strip()
        creds = input(f"Creds path [{_creds_default(atype)}]: ").strip() or _creds_default(atype)
        cfg["account"]["creds"] = creds
        cfg["recipient"] = input("Recipient address: ").strip()
        cp = Path(creds).expanduser()
        if not cp.exists():
            print(f"  ! warning: creds not found at {cp} — set them up before the first send.")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    CONFIG_PATH.chmod(0o600)
    print(f"\nWrote {CONFIG_PATH}\nRun `usage_email.py --check-config` to validate, "
          "or `--test-send` to send a test now.")
    return 0


def cmd_check_config() -> int:
    cfg = load_email_config()
    print(json.dumps(cfg, indent=2))
    if not cfg.get("enabled"):
        print(f"\nstatus: DISABLED (no/invalid {CONFIG_PATH}) — weekly job writes a local report only.")
        return 0
    account = cfg.get("account") or {}
    creds = account.get("creds")
    cp = Path(creds).expanduser() if creds else None
    print(f"\ntransport: {account.get('type')}  sender: {account.get('sender')}")
    print(f"recipient: {cfg.get('recipient')}")
    print(f"creds:     {cp} {'(present)' if cp and cp.exists() else '(MISSING)'}")
    print(f"python:    {_python_bin()}")
    return 0


def cmd_test_send() -> int:
    cfg = load_email_config()
    now = datetime.now(timezone.utc)
    code, _ = send_weekly(
        md_summary=f"cost-telemetry test send at {now.isoformat()}",
        html_path=None, state={}, host="test", config=cfg, now=now,
    )
    msg = {SENT_OR_SKIP: "sent (or already sent this week)", DISABLED: "disabled/not configured",
           SEND_FAILED: "send FAILED"}.get(code, str(code))
    print(f"test-send: {msg} (exit {code})")
    return 0 if code == SENT_OR_SKIP else code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="usage_email", description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--configure", action="store_true", help="interactively write this machine's email config")
    g.add_argument("--check-config", action="store_true", help="print the resolved config + transport (no send)")
    g.add_argument("--test-send", action="store_true", help="send a one-off test email via the configured transport")
    args = ap.parse_args(argv)
    if args.configure:
        return cmd_configure()
    if args.check_config:
        return cmd_check_config()
    return cmd_test_send()


if __name__ == "__main__":
    raise SystemExit(main())
