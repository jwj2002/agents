#!/usr/bin/env python3
"""Google Contacts read/write on the shared ~/agents/google token (`contacts` scope).

Look up a name -> email/phone (e.g. before send_mail.py), and create/delete
contacts (e.g. add a sender after triaging a new email). People API.

    PY=~/agents/.venv/bin/python
    $PY ~/agents/google/contacts.py search "Bob Smith"
    $PY ~/agents/google/contacts.py add "Bob Smith" --email bob@x.com --phone 555-1234
    $PY ~/agents/google/contacts.py delete people/c1234567890   # resourceName from add/search
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


def create_contact(svc, name: str, emails: list[str], phones: list[str]) -> dict:
    parts = name.split()
    person = {"names": [{"givenName": parts[0], "familyName": " ".join(parts[1:])}]}
    if emails:
        person["emailAddresses"] = [{"value": e} for e in emails]
    if phones:
        person["phoneNumbers"] = [{"value": p} for p in phones]
    return svc.people().createContact(body=person).execute()


def delete_contact(svc, resource_name: str) -> None:
    svc.people().deleteContact(resourceName=resource_name).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Contacts (read/write)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--max", type=int, default=10, dest="maxn")
    pa = sub.add_parser("add")
    pa.add_argument("name")
    pa.add_argument("--email", action="append", default=[])
    pa.add_argument("--phone", action="append", default=[])
    pd = sub.add_parser("delete")
    pd.add_argument("resource_name", help="e.g. people/c123... (from add/search)")
    a = ap.parse_args()

    svc = service()
    if a.cmd == "search":
        people = search(svc, a.query, a.maxn)
        if not people:
            print(f"(no contacts match {a.query!r})")
            return 0
        for p in people:
            print(f"{_fmt(p)}  [{p.get('resourceName', '')}]")
    elif a.cmd == "add":
        created = create_contact(svc, a.name, a.email, a.phone)
        print(f"ADDED: {_fmt(created)}  [{created.get('resourceName', '')}]")
    elif a.cmd == "delete":
        delete_contact(svc, a.resource_name)
        print(f"DELETED {a.resource_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
