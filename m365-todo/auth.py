"""Delegated Microsoft Graph auth for a personal Microsoft account — Microsoft To Do.

Device-code flow, public client (no client secret). The refresh token is cached
at ``token.json`` next to this file — git-ignored, this-machine-only (mirrors the
``~/agents/google`` pattern). Any agent that needs Microsoft To Do imports
``get_token()``.
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path

import msal

CLIENT_ID = "d9df9a09-f0ee-4093-90ab-2dbb319b4570"
AUTHORITY = "https://login.microsoftonline.com/consumers"  # personal MS account
SCOPES = ["Tasks.ReadWrite"]
ACCOUNT_HINT = "jasonwadejob@gmail.com"

_DIR = Path(__file__).resolve().parent
TOKEN_PATH = _DIR / "token.json"


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
    return msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=cache or _load_cache()
    )


def get_token() -> str:
    """Return a valid access token via silent refresh. Raises if not yet authorized."""
    cache = _load_cache()
    app = build_app(cache)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]
    raise RuntimeError(
        "Microsoft To Do not authorized on this machine — run "
        "`~/agents/.venv/bin/python ~/agents/m365-todo/authorize.py start` (and `finish`)."
    )
