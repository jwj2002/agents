#!/usr/bin/env python3
"""Google Calendar CLI (read/write) for all agents, on the central ~/agents/google token.

Named gcal.py (NOT calendar.py) on purpose — a module named `calendar` shadows the
Python stdlib `calendar` that email/http libraries import, breaking the Google client.

Mirrors send_mail.py: uses the shared auto-refreshing credentials (calendar scope
already authorized). Any agent can `from gcal import service` or shell out.

    PY=~/agents/.venv/bin/python
    $PY ~/agents/google/gcal.py calendars
    $PY ~/agents/google/gcal.py agenda --days 7 --max 20
    $PY ~/agents/google/gcal.py add --title "Lunch" --start "2026-06-27 12:30" --end "2026-06-27 13:30"
    $PY ~/agents/google/gcal.py add --all-day --title "Trip" --start 2026-07-01 --end 2026-07-03
    $PY ~/agents/google/gcal.py quickadd --text "Dentist Thursday 3pm"
    $PY ~/agents/google/gcal.py delete --event-id <id>
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/Users/jasonjob/agents/google")
from auth import load_credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402


def service():
    return build("calendar", "v3", credentials=load_credentials(), cache_discovery=False)


def _cal_tz(svc, calendar_id: str) -> str:
    """Default to the calendar's own timezone so naive datetimes land correctly."""
    try:
        return svc.calendars().get(calendarId=calendar_id).execute().get("timeZone", "UTC")
    except Exception:  # noqa: BLE001 — fail-open: tz lookup is best-effort, default UTC
        return "UTC"


def _parse_dt(value: str) -> str:
    """Accept 'YYYY-MM-DD HH:MM' or ISO; return an RFC3339 local-naive string."""
    return datetime.fromisoformat(value).isoformat()


def list_calendars(svc) -> list[dict]:
    return svc.calendarList().list(maxResults=100).execute().get("items", [])


def agenda(svc, calendar_id: str, days: int, maxn: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    return (
        svc.events()
        .list(
            calendarId=calendar_id,
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=maxn,
        )
        .execute()
        .get("items", [])
    )


def add_event(svc, calendar_id, title, start, end, all_day, tz, location, desc, attendees) -> dict:
    if all_day:
        s = start
        e = end or (datetime.fromisoformat(start) + timedelta(days=1)).date().isoformat()
        body = {"summary": title, "start": {"date": s}, "end": {"date": e}}
    else:
        tz = tz or _cal_tz(svc, calendar_id)
        s = _parse_dt(start)
        e = _parse_dt(end) if end else (datetime.fromisoformat(start) + timedelta(hours=1)).isoformat()
        body = {
            "summary": title,
            "start": {"dateTime": s, "timeZone": tz},
            "end": {"dateTime": e, "timeZone": tz},
        }
    if location:
        body["location"] = location
    if desc:
        body["description"] = desc
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    return svc.events().insert(calendarId=calendar_id, body=body).execute()


def quick_add(svc, calendar_id: str, text: str) -> dict:
    return svc.events().quickAdd(calendarId=calendar_id, text=text).execute()


def delete_event(svc, calendar_id: str, event_id: str) -> None:
    svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def _fmt(ev: dict) -> str:
    start = ev.get("start", {})
    when = start.get("dateTime") or start.get("date") or "?"
    return f"{when}  {ev.get('summary', '(no title)')}  [{ev.get('id')}]"


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Calendar CLI (read/write)")
    ap.add_argument("--calendar", default="primary", help="calendar id (default: primary)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("calendars")
    p_ag = sub.add_parser("agenda")
    p_ag.add_argument("--days", type=int, default=7)
    p_ag.add_argument("--max", type=int, default=20, dest="maxn")

    p_add = sub.add_parser("add")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--start", required=True, help="'YYYY-MM-DD HH:MM' (or YYYY-MM-DD with --all-day)")
    p_add.add_argument("--end")
    p_add.add_argument("--all-day", action="store_true")
    p_add.add_argument("--tz", help="IANA tz (default: the calendar's timezone)")
    p_add.add_argument("--location")
    p_add.add_argument("--desc")
    p_add.add_argument("--attendee", action="append", default=[])

    p_q = sub.add_parser("quickadd")
    p_q.add_argument("--text", required=True)

    p_del = sub.add_parser("delete")
    p_del.add_argument("--event-id", required=True)

    a = ap.parse_args()
    svc = service()
    cal = a.calendar

    if a.cmd == "calendars":
        for c in list_calendars(svc):
            flag = " (primary)" if c.get("primary") else ""
            print(f"{c.get('summary')}{flag}  [{c.get('id')}]")
    elif a.cmd == "agenda":
        items = agenda(svc, cal, a.days, a.maxn)
        if not items:
            print(f"(no events in the next {a.days} days)")
        for ev in items:
            print(_fmt(ev))
    elif a.cmd == "add":
        ev = add_event(svc, cal, a.title, a.start, a.end, a.all_day, a.tz, a.location, a.desc, a.attendee)
        print(f"CREATED: {_fmt(ev)}")
        if ev.get("htmlLink"):
            print(ev["htmlLink"])
    elif a.cmd == "quickadd":
        ev = quick_add(svc, cal, a.text)
        print(f"CREATED: {_fmt(ev)}")
    elif a.cmd == "delete":
        delete_event(svc, cal, a.event_id)
        print(f"DELETED event {a.event_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
