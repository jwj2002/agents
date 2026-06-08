#!/usr/bin/env python3
"""SessionStart hook — capture the Claude billing account into a sidecar (fleet-usage-monitor §4.1).

The billing identity lives in `~/.claude.json` → `oauthAccount` at session-start time, NOT in the
transcript — so it must be captured then and joined later by the usage collector (#262). This hook
writes ONE line per session to `~/.claude/telemetry/account-map.jsonl`:

    {"session_id","account_uuid","org","email","billing_type","billing_type_raw","seat_tier","ts"}

`billing_type` decides what `cost_usd` MEANS (§6): `subscription` (Max/Pro) → cost is notional
API-equivalent value, not cash; `metered` (console/API) → ≈ actual dollars. The OAuth token / API key
is NEVER written (the §229 no-secrets-in-shards ban).

NOT auto-activated: this is the hook SCRIPT. To enable it, register it as a SessionStart hook in your
Claude settings — left to the operator so a live-session hook is never installed autonomously.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The env-aware billing resolver lives in scripts/ (sibling of hooks/). Import best-effort so the hook
# still works if it's missing — billing then falls back to the OAuth-only classifier (#337/#339).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from usage_billing import resolve_billing_type
except Exception:  # pragma: no cover - defensive
    resolve_billing_type = None

# Identity fields copied from oauthAccount — explicitly NO token/key fields.
_OAUTH_FIELDS = {
    "accountUuid": "account_uuid",
    "organizationName": "org",
    "organizationUuid": "org_uuid",
    "emailAddress": "email",
    "seatTier": "seat_tier",
    "organizationRateLimitTier": "rate_limit_tier",
}


def classify_billing(raw) -> str | None:
    """Normalize oauthAccount.billingType → subscription | metered (raw passthrough if unrecognized).
    Exact Claude enum values are confirmed at activation; subscription vs metered is the load-bearing
    distinction (§6)."""
    r = str(raw or "").lower()
    if not r:
        return None
    if "subscription" in r or r in ("max", "pro", "team", "enterprise"):
        return "subscription"
    if r in ("console", "api", "metered", "usage_based", "pay_as_you_go"):
        return "metered"
    return raw  # unknown enum → passthrough (don't silently mislabel)


def build_entry(claude_json_path, session_id, *, now_ts: str, env: dict | None = None) -> dict:
    """Build the sidecar entry from ~/.claude.json's oauthAccount. Never includes any secret.
    `env` (defaults to the session's os.environ) lets the billing resolver see an API key — injectable
    for tests so billing detection is deterministic."""
    env = env if env is not None else os.environ
    entry = {"session_id": session_id, "ts": now_ts}
    try:
        data = json.loads(Path(claude_json_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    if not isinstance(data, dict):  # well-formed JSON but non-object → no-crash
        data = {}
    oa = data.get("oauthAccount")
    oa = oa if isinstance(oa, dict) else {}
    for src, dst in _OAUTH_FIELDS.items():
        entry[dst] = oa.get(src)
    raw = oa.get("billingType")
    entry["billing_type_raw"] = raw
    # Env API key beats a stale OAuth login (an API-key session is 'metered' even if oauthAccount says
    # subscription; #337/#339). Fall back to the OAuth-only classifier if the resolver is unavailable so
    # the hook never breaks.
    if resolve_billing_type is not None:
        try:
            entry["billing_type"] = resolve_billing_type(env, claude_json_path)
        except Exception:
            entry["billing_type"] = classify_billing(raw)
    else:
        entry["billing_type"] = classify_billing(raw)
    return entry


def append_entry(sidecar_path, entry: dict) -> None:
    p = Path(sidecar_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    # Claude Code passes hook input as JSON on stdin (incl. session_id); fall back to env.
    data = {}
    if not sys.stdin.isatty():
        try:
            data = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            data = {}
    session_id = data.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    if not session_id:
        return 0  # nothing to key on; no-op rather than write a useless entry
    # A SessionStart hook must NEVER raise or exit nonzero — a sidecar write (bad path, full disk,
    # perms) must not break or delay session start (#339). Best-effort; on any error, no-op, return 0.
    try:
        home = Path.home()
        entry = build_entry(home / ".claude.json", session_id, now_ts=_now_iso())
        append_entry(home / ".claude" / "telemetry" / "account-map.jsonl", entry)
    except Exception:
        return 0  # never surface a traceback to session start
    return 0


if __name__ == "__main__":
    sys.exit(main())
