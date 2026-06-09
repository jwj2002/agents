#!/usr/bin/env python3
"""Send email as the authorized Google account — shared helper for all agents.

Mirrors ~/agents/m365/send_mail.py, but sends from the Google identity in
token.json (auto-refreshes). Used by any agent that needs to send Gmail.

Examples:
    ~/agents/.venv/bin/python ~/agents/google/send_mail.py \\
        --to someone@example.com --subject "Hi" --body "Hello there"

    # body from stdin, with attachments:
    cat note.md | ~/agents/.venv/bin/python ~/agents/google/send_mail.py \\
        --to a@b.com --subject "Notes" --body - --attach note.md --attach chart.png
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import sys
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auth import load_credentials  # noqa: E402


def send_mail(to, subject, body, attach=None, cc=None, bcc=None, token_path=None):
    """Send one email; returns (sender_address, message_id).

    token_path selects which Google account to send as (default: the shared
    google/token.json). Lets callers pick a specific account per machine.
    """
    from googleapiclient.discovery import build

    creds = load_credentials(token_path) if token_path else load_credentials()
    svc = build("gmail", "v1", credentials=creds)

    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    msg.set_content(body)

    for f in attach or []:
        p = Path(f).expanduser()
        if not p.exists():
            raise SystemExit(f"Attachment not found: {p}")
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = (
            ctype.split("/", 1) if ctype else ("application", "octet-stream")
        )
        msg.add_attachment(
            p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name
        )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    sender = svc.users().getProfile(userId="me").execute().get("emailAddress")
    return sender, sent.get("id")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Send email from the shared Google identity."
    )
    ap.add_argument(
        "--to", required=True, action="append", help="recipient (repeatable)"
    )
    ap.add_argument("--cc", action="append", help="cc (repeatable)")
    ap.add_argument("--bcc", action="append", help="bcc (repeatable)")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True, help="body text, or '-' to read stdin")
    ap.add_argument(
        "--attach", action="append", default=[], help="file path (repeatable)"
    )
    ap.add_argument(
        "--token",
        help="path to a Google token.json (default: shared google/token.json) — selects the send account",
    )
    a = ap.parse_args()

    body = sys.stdin.read() if a.body == "-" else a.body
    sender, mid = send_mail(a.to, a.subject, body, a.attach, a.cc, a.bcc, token_path=a.token)
    print(f"SENT from {sender} -> {', '.join(a.to)} (id {mid})")


if __name__ == "__main__":
    main()
