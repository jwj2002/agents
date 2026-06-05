#!/usr/bin/env python3
"""Re-authorize Google for every agent — one browser consent → token.json.

Usage:
    ~/agents/.venv/bin/python ~/agents/google/reauth.py

Writes ~/agents/google/token.json, which all agents (and buddy, via symlink) share.

On a NEW machine you can skip the browser entirely and instead COPY token.json
from a machine that is already authorized — the refresh token is portable for the
same OAuth client. See README.md ("Enabling email on another machine").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auth import CLIENT_PATH, SCOPES, TOKEN_PATH  # noqa: E402

# Installed-app clients use a loopback redirect; Google accepts any localhost port.
REDIRECT_PORT = 8098


def main() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_PATH.exists():
        raise SystemExit(
            f"Missing OAuth client at {CLIENT_PATH}.\n"
            "Copy it from an authorized machine, or download the *installed-app* "
            "OAuth client JSON from Google Cloud Console and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
    creds = flow.run_local_server(port=REDIRECT_PORT, prompt="consent")

    TOKEN_PATH.write_text(creds.to_json())
    TOKEN_PATH.chmod(0o600)
    print(f"Authorized. Token written to {TOKEN_PATH}")
    print("Account:", getattr(creds, "account", "") or "(authorized Google account)")
    print("Scopes :", ", ".join(s.split("/")[-1] for s in SCOPES))


if __name__ == "__main__":
    main()
