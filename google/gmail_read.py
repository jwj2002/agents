#!/usr/bin/env python3
"""Gmail read/search CLI on the shared ~/agents/google token.

Uses the token's existing `gmail.modify` scope (which includes read) — no extra
auth. Mirrors send_mail.py / gcal.py. This is the token-based replacement for the
claude.ai Gmail MCP's read tools, so reading no longer depends on an MCP connector.

    PY=~/agents/.venv/bin/python
    $PY ~/agents/google/gmail_read.py unread --max 10
    $PY ~/agents/google/gmail_read.py search "from:boss@x.com newer_than:7d" --max 20
    $PY ~/agents/google/gmail_read.py read <message_id>
    $PY ~/agents/google/gmail_read.py attachments <message_id>
"""

from __future__ import annotations

import argparse
import base64
import io
import sys

sys.path.insert(0, "/Users/jasonjob/agents/google")
from auth import load_credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402


def service():
    return build("gmail", "v1", credentials=load_credentials(), cache_discovery=False)


def _hdr(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def search(svc, query: str, maxn: int) -> list[dict]:
    resp = svc.users().messages().list(userId="me", q=query, maxResults=maxn).execute()
    out = []
    for m in resp.get("messages", []):
        msg = (
            svc.users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        h = msg.get("payload", {}).get("headers", [])
        out.append(
            {
                "id": m["id"],
                "from": _hdr(h, "From"),
                "subject": _hdr(h, "Subject"),
                "date": _hdr(h, "Date"),
                "snippet": msg.get("snippet", ""),
            }
        )
    return out


def _extract_body(payload: dict) -> str:
    """Walk MIME parts for text/plain; fall back to the top-level body."""
    def walk(p: dict) -> str:
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", "replace")
        for sub in p.get("parts", []) or []:
            found = walk(sub)
            if found:
                return found
        return ""

    body = walk(payload)
    if not body and payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    return body


def read_msg(svc, mid: str) -> dict:
    msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
    h = msg.get("payload", {}).get("headers", [])
    return {
        "from": _hdr(h, "From"),
        "to": _hdr(h, "To"),
        "subject": _hdr(h, "Subject"),
        "date": _hdr(h, "Date"),
        "body": _extract_body(msg.get("payload", {})),
    }


def _iter_attachments(payload: dict):
    """Yield attachment descriptors from a full-format message payload.

    A MIME part is treated as an attachment when it carries a non-empty
    ``filename``. Small attachments arrive inline as ``body.data``; larger ones
    only carry ``body.attachmentId`` and must be fetched separately.
    """
    def walk(p: dict):
        body = p.get("body", {}) or {}
        if p.get("filename"):
            yield {
                "filename": p["filename"],
                "mime": p.get("mimeType", ""),
                "size": body.get("size", 0),
                "data": body.get("data"),
                "attachment_id": body.get("attachmentId"),
            }
        for sub in p.get("parts", []) or []:
            yield from walk(sub)

    yield from walk(payload)


def _download_attachment(svc, mid: str, att: dict) -> bytes:
    """Return the decoded bytes for an attachment (inline or fetched by id)."""
    raw = att.get("data")
    if not raw:
        resp = (
            svc.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=mid, id=att["attachment_id"])
            .execute()
        )
        raw = resp.get("data", "")
    return base64.urlsafe_b64decode(raw)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf. Pure/testable — no Gmail."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def list_attachments(svc, mid: str) -> list[dict]:
    msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
    return list(_iter_attachments(msg.get("payload", {})))


def main() -> int:
    ap = argparse.ArgumentParser(description="Gmail read/search CLI (shared token)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("search")
    ps.add_argument("query", help="Gmail search query (same syntax as the Gmail search box)")
    ps.add_argument("--max", type=int, default=10, dest="maxn")
    pu = sub.add_parser("unread")
    pu.add_argument("--max", type=int, default=10, dest="maxn")
    pr = sub.add_parser("read")
    pr.add_argument("id")
    pa = sub.add_parser("attachments")
    pa.add_argument("id")
    a = ap.parse_args()

    svc = service()
    if a.cmd in ("search", "unread"):
        q = a.query if a.cmd == "search" else "is:unread"
        rows = search(svc, q, a.maxn)
        if not rows:
            print("(no matching messages)")
        for m in rows:
            print(f"[{m['id']}] {m['date']}")
            print(f"  From: {m['from']}")
            print(f"  Subj: {m['subject']}")
            print(f"  {m['snippet'][:160]}\n")
    elif a.cmd == "read":
        m = read_msg(svc, a.id)
        print(f"From: {m['from']}\nTo: {m['to']}\nDate: {m['date']}\nSubject: {m['subject']}\n")
        print(m["body"][:4000])
    elif a.cmd == "attachments":
        atts = list_attachments(svc, a.id)
        if not atts:
            print("(no attachments)")
            return 0
        for i, att in enumerate(atts, 1):
            print(f"[{i}] {att['filename']}  ({att['mime']}, {att['size']} bytes)")
        for att in atts:
            if att["mime"] == "application/pdf" or att["filename"].lower().endswith(".pdf"):
                print(f"\n--- PDF text: {att['filename']} ---")
                try:
                    text = extract_pdf_text(_download_attachment(svc, a.id, att))
                except Exception as exc:  # noqa: BLE001 - report, keep other attachments
                    print(f"(failed to extract text: {exc})")
                    continue
                print(text.strip() or "(no extractable text — likely a scanned image)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
