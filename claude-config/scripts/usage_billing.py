"""Billing-type detection (cost-telemetry-v0 §D7).

Decides whether a session is `metered` (real $, API-key) or `subscription` (notional, projected $),
which is the ONLY signal separating real-vs-projected cost in the report. The hard part is that an
**API key in the environment beats a stale OAuth login** — a session run with `ANTHROPIC_API_KEY` set
is billed to the key regardless of any `oauthAccount` left in `~/.claude.json`.

This is a PURE helper (inject `env` + path) so it's testable. It is meant to be called by the
SessionStart account-capture hook (where `env` is the session's own environment) so each session is
tagged at capture time. ⚠ launchd does NOT inherit a shell's env — under launchd the API-key keys are
absent unless explicitly added to the plist `EnvironmentVariables`, so the env-key branch only fires in
the hook context, not in a launchd-run collector. (Wired into the live SessionStart account-capture
hook via runbook Step 7 — #337/#339 review.)
"""

from __future__ import annotations

import json
from pathlib import Path

# oauthAccount.billingType values that mean real metered billing despite being an OAuth login.
_METERED_PLANS = frozenset(
    {"console", "api", "metered", "usage_based", "pay_as_you_go"}
)


def resolve_billing_type(env: dict, claude_json_path) -> str:
    """`metered` | `subscription` | `unknown`. Precedence (cost-telemetry-v0 §D7):
    1. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` present in `env` → `metered` (env key beats OAuth).
    2. valid `oauthAccount` and no env key → `subscription` (or `metered` if its plan is console/api).
    3. `~/.claude.json` absent / malformed / no oauthAccount → `unknown` (never silently mislabel)."""
    env = env or {}
    if env.get("ANTHROPIC_API_KEY") or env.get("OPENAI_API_KEY"):
        return "metered"
    try:
        data = json.loads(Path(claude_json_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    oa = data.get("oauthAccount")
    if not isinstance(oa, dict) or not oa:
        return "unknown"
    plan = str(oa.get("billingType") or "").lower()
    if plan in _METERED_PLANS:
        return "metered"
    return "subscription"  # an OAuth login that isn't a console/api plan = subscription
