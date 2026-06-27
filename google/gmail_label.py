#!/usr/bin/env python3
"""Gmail label management on the shared ~/agents/google token (gmail.modify scope).

Add / remove labels on a message (e.g. triage a new email) — no re-auth needed.

    PY=~/agents/.venv/bin/python
    $PY ~/agents/google/gmail_label.py list
    $PY ~/agents/google/gmail_label.py add <message_id> "Follow up" [--create]
    $PY ~/agents/google/gmail_label.py remove <message_id> "Follow up"
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/Users/jasonjob/agents/google")
from auth import load_credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402


def service():
    return build("gmail", "v1", credentials=load_credentials(), cache_discovery=False)


def _labels(svc) -> list[dict]:
    return svc.users().labels().list(userId="me").execute().get("labels", [])


def _resolve(svc, name: str, create: bool = False) -> str:
    for label in _labels(svc):
        if label["name"].lower() == name.lower():
            return label["id"]
    if create:
        made = (
            svc.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        return made["id"]
    existing = [label["name"] for label in _labels(svc) if label.get("type") == "user"]
    raise SystemExit(f"Label not found: {name!r} (pass --create to make it). Existing: {existing}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gmail label management (shared token)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    pa = sub.add_parser("add")
    pa.add_argument("message_id")
    pa.add_argument("label")
    pa.add_argument("--create", action="store_true", help="create the label if it doesn't exist")
    pr = sub.add_parser("remove")
    pr.add_argument("message_id")
    pr.add_argument("label")
    a = ap.parse_args()

    svc = service()
    if a.cmd == "list":
        for label in sorted(_labels(svc), key=lambda x: x["name"].lower()):
            tag = "" if label.get("type") == "user" else "  (system)"
            print(f"{label['name']}{tag}")
    elif a.cmd == "add":
        lid = _resolve(svc, a.label, create=a.create)
        svc.users().messages().modify(
            userId="me", id=a.message_id, body={"addLabelIds": [lid]}
        ).execute()
        print(f"ADDED label {a.label!r} to message {a.message_id}")
    elif a.cmd == "remove":
        lid = _resolve(svc, a.label)
        svc.users().messages().modify(
            userId="me", id=a.message_id, body={"removeLabelIds": [lid]}
        ).execute()
        print(f"REMOVED label {a.label!r} from message {a.message_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
