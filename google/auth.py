"""Shared Google OAuth credentials for all agents — single source of truth.

Files (this directory, git-ignored):
    oauth_client.json  installed-app OAuth client (client_id/secret; same on every machine)
    token.json         user authorization (standard google.oauth2 format; auto-refreshed)

Every agent should obtain credentials through ``load_credentials()`` rather than
re-implementing OAuth. buddy points at ``token.json`` via a symlink (see README).

Requires the libs in requirements.txt (installed in ~/agents/.venv).
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLIENT_PATH = BASE / "oauth_client.json"
TOKEN_PATH = BASE / "token.json"

# Superset of scopes so one token serves every agent (gmail send/modify, calendar,
# tasks, contacts). gmail.modify supersedes gmail.readonly.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/contacts",
]


def load_credentials(token_path: Path | str = TOKEN_PATH):
    """Return valid Google ``Credentials``, refreshing + persisting if expired.

    Raises FileNotFoundError if no token exists (run reauth.py) or RuntimeError
    if the token is unusable (refresh token revoked/expired — run reauth.py).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    p = Path(token_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(
            f"No Google token at {p}.\nRun:  ~/agents/.venv/bin/python {BASE / 'reauth.py'}"
        )

    data = json.loads(p.read_text())
    creds = Credentials.from_authorized_user_info(data, data.get("scopes", SCOPES))

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        p.write_text(creds.to_json())  # persist the refreshed access token
        p.chmod(0o600)

    if not creds.valid:
        raise RuntimeError(
            f"Google token at {p} is invalid (likely revoked/expired refresh token).\n"
            f"Re-run:  ~/agents/.venv/bin/python {BASE / 'reauth.py'}"
        )
    return creds
