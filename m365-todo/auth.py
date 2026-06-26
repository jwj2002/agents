"""Delegated Microsoft Graph auth for Microsoft To Do — per-machine profile.

Identity (client_id / authority / scopes / account) is read from a git-ignored
``config.json`` next to this file, NOT hardcoded — so the SAME committed code runs
as a personal profile on personal machines and a work profile on work machines.
Copy ``config.example.json`` → ``config.json`` and fill it in to activate.

The refresh token is cached at ``token.json`` (git-ignored, 0600, this-machine-only).
Capability is active only where BOTH config.json and token.json exist; otherwise it
fails closed. Any agent that needs Microsoft To Do imports ``get_token()``.
"""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

import msal

_DIR = Path(__file__).resolve().parent
CONFIG_PATH = _DIR / "config.json"
TOKEN_PATH = _DIR / "token.json"


def _config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            "Microsoft To Do not configured on this machine — copy "
            "`config.example.json` → `config.json` and fill in client_id / authority "
            "/ account for this machine's profile (see rules/ms-todo.md)."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def scopes() -> list[str]:
    return _config().get("scopes", ["Tasks.ReadWrite"])


def account_hint() -> str:
    return _config().get("account", "")


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_PATH.exists():
        cache.deserialize(TOKEN_PATH.read_text(encoding="utf-8"))
    atexit.register(lambda: _save_cache(cache))
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        TOKEN_PATH.write_text(cache.serialize(), encoding="utf-8")
        os.chmod(TOKEN_PATH, 0o600)


def build_app(cache: msal.SerializableTokenCache | None = None) -> msal.PublicClientApplication:
    cfg = _config()
    return msal.PublicClientApplication(
        cfg["client_id"], authority=cfg["authority"], token_cache=cache or _load_cache()
    )


def get_token() -> str:
    """Return a valid access token via silent refresh. Raises if not yet authorized."""
    cache = _load_cache()
    app = build_app(cache)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes(), account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]
    raise RuntimeError(
        "Microsoft To Do not authorized on this machine — run "
        "`~/agents/.venv/bin/python ~/agents/m365-todo/authorize.py start` (then `finish`)."
    )
