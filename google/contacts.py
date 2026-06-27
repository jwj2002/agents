#!/usr/bin/env python3
"""Google Contacts lookup (read-only) on the shared ~/agents/google token.

Resolve a name -> email / phone (e.g. before sending mail with send_mail.py).
Uses the token's existing `contacts.readonly` scope — no re-auth. People API.

    PY=~/agents/.venv/bin/python
    $PY ~/agents/google/contacts.py search "Bob Smith"
    $PY ~/agents/google/contacts.py search bob --max 5
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/Users/jasonjob/agents/google")
from auth import load_credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

READ_MASK = "names,emailAddresses,phoneNumbers"


def service():
    return build("people", "v1", credentials=load_credentials(), cache_discovery=False)


def _fmt(person: dict) -> str:
    name = (person.get("names") or [{}])[0].get("displayName", "(no name)")
    emails = [e["value"] for e in person.get("emailAddresses", []) if e.get("value")]
    phones = [p["value"] for p in person.get("phoneNumbers", []) if p.get("value")]
    line = name
    if emails:
        line += "  <" + ", ".join(emails) + ">"
    if phones:
        line += "  tel " + ", ".join(phones)
    return line


def search(svc, query: str, maxn: int) -> list[dict]:
    # People API recommends a warmup request before searchContacts.
    try:
        svc.people().searchContacts(query="", readMask="names").execute()
    except Exception:  # noqa: BLE001 — warmup is best-effort; ignore failures
        pass
    resp = svc.people().searchContacts(query=query, readMask=READ_MASK, pageSize=maxn).execute()
    return [r.get("person", {}) for r in resp.get("results", [])]


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Contacts lookup (read-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--max", type=int, default=10, dest="maxn")
    a = ap.parse_args()

    svc = service()
    people = search(svc, a.query, a.maxn)
    if not people:
        print(f"(no contacts match {a.query!r})")
        return 0
    for p in people:
        print(_fmt(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
