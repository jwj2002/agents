"""Send email via Microsoft Graph using app-only auth.

Reads credentials from ~/.claude/m365/jason-agent.json:
    {"tenant_id": ..., "client_id": ..., "client_secret": ..., "sender_upn": ...}

Token cache: ~/.claude/m365/token-cache.bin (managed by msal).

Usage:
    python3 send_mail.py --to paul@example.com --subject "..." \
        --body "Hello" [--content-type Text|HTML|Markdown] [--cc a@b.com,c@d.com]
    python3 send_mail.py --to ... --subject ... --body-file path.md \
        --content-type Markdown
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import msal
import requests


CREDS_PATH = Path.home() / ".claude" / "m365" / "jason-agent.json"
CACHE_PATH = Path.home() / ".claude" / "m365" / "token-cache.bin"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class SendMailError(Exception):
    """Raised when Graph rejects the send."""


def load_creds() -> dict:
    if not CREDS_PATH.exists():
        raise SendMailError(
            f"Missing credentials at {CREDS_PATH}. See "
            "~/projects/paul-jason/docs/jason-agent-setup.md step 6."
        )
    if (CREDS_PATH.stat().st_mode & 0o077) != 0:
        raise SendMailError(
            f"{CREDS_PATH} has loose permissions; run `chmod 600 {CREDS_PATH}`."
        )
    with CREDS_PATH.open() as f:
        creds = json.load(f)
    required = {"tenant_id", "client_id", "client_secret", "sender_upn"}
    missing = required - creds.keys()
    if missing:
        raise SendMailError(f"{CREDS_PATH} missing fields: {sorted(missing)}")
    return creds


def get_token(creds: dict) -> str:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text())

    app = msal.ConfidentialClientApplication(
        client_id=creds["client_id"],
        client_credential=creds["client_secret"],
        authority=f"https://login.microsoftonline.com/{creds['tenant_id']}",
        token_cache=cache,
    )
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise SendMailError(
            f"Token acquisition failed: {result.get('error_description', result)}"
        )
    if cache.has_state_changed:
        CACHE_PATH.write_text(cache.serialize())
        os.chmod(CACHE_PATH, 0o600)
    return result["access_token"]


def build_message(
    *,
    subject: str,
    body: str,
    content_type: str,
    to: list[str],
    cc: list[str],
) -> dict:
    # Graph only knows Text and HTML. For Markdown we send as Text — the
    # recipient agent parses raw markdown; this preserves the digest header
    # comment and tables verbatim.
    graph_content_type = "HTML" if content_type.lower() == "html" else "Text"
    return {
        "message": {
            "subject": subject,
            "body": {"contentType": graph_content_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
        },
        "saveToSentItems": True,
    }


def send_mail(
    *,
    subject: str,
    body: str,
    to: list[str],
    cc: list[str] | None = None,
    content_type: str = "Text",
) -> None:
    creds = load_creds()
    token = get_token(creds)
    payload = build_message(
        subject=subject,
        body=body,
        content_type=content_type,
        to=to,
        cc=cc or [],
    )
    url = f"https://graph.microsoft.com/v1.0/users/{creds['sender_upn']}/sendMail"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code != 202:
        raise SendMailError(
            f"Graph returned {response.status_code}: {response.text}"
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--to", required=True, help="Comma-separated recipients")
    p.add_argument("--cc", default="", help="Comma-separated cc addresses")
    p.add_argument("--subject", required=True)
    body_group = p.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Inline body text")
    body_group.add_argument("--body-file", help="Path to a file with body text")
    p.add_argument(
        "--content-type",
        default="Text",
        choices=["Text", "HTML", "Markdown"],
        help="Markdown is sent as Text (Graph has no Markdown type)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    body = args.body if args.body is not None else Path(args.body_file).read_text()
    to = [a.strip() for a in args.to.split(",") if a.strip()]
    cc = [a.strip() for a in args.cc.split(",") if a.strip()]
    try:
        send_mail(
            subject=args.subject,
            body=body,
            to=to,
            cc=cc,
            content_type=args.content_type,
        )
    except SendMailError as e:
        print(f"send_mail: {e}", file=sys.stderr)
        return 1
    print(f"sent: {args.subject} -> {', '.join(to)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
