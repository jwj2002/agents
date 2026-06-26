"""Microsoft To Do CLI (personal account) via Graph delegated token.

Usage:
    PY=~/agents/.venv/bin/python
    $PY ~/agents/m365-todo/todo.py lists
    $PY ~/agents/m365-todo/todo.py tasks "Tasks"            # list name (default list is "Tasks")
    $PY ~/agents/m365-todo/todo.py add "Tasks" "Buy milk"
    $PY ~/agents/m365-todo/todo.py complete "Tasks" "Buy milk"
"""

from __future__ import annotations

import argparse
import sys

import requests

from auth import get_token

GRAPH = "https://graph.microsoft.com/v1.0"


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}


def _get(url: str) -> dict:
    r = requests.get(url, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def get_lists() -> list[dict]:
    return _get(f"{GRAPH}/me/todo/lists").get("value", [])


def _resolve_list_id(name: str) -> str:
    for lst in get_lists():
        if lst.get("displayName", "").lower() == name.lower():
            return lst["id"]
    names = [x["displayName"] for x in get_lists()]
    raise SystemExit(f"List not found: {name!r}. Available: {names}")


def get_tasks(list_name: str, include_done: bool = False) -> list[dict]:
    lid = _resolve_list_id(list_name)
    items = _get(f"{GRAPH}/me/todo/lists/{lid}/tasks").get("value", [])
    if not include_done:
        items = [t for t in items if t.get("status") != "completed"]
    return items


def add_task(list_name: str, title: str) -> dict:
    lid = _resolve_list_id(list_name)
    r = requests.post(
        f"{GRAPH}/me/todo/lists/{lid}/tasks",
        headers=_headers(),
        json={"title": title},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def complete_task(list_name: str, title: str) -> dict:
    lid = _resolve_list_id(list_name)
    match = next((t for t in get_tasks(list_name) if t["title"].lower() == title.lower()), None)
    if not match:
        raise SystemExit(f"Open task not found in {list_name!r}: {title!r}")
    r = requests.patch(
        f"{GRAPH}/me/todo/lists/{lid}/tasks/{match['id']}",
        headers=_headers(),
        json={"status": "completed"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser(description="Microsoft To Do CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lists")
    p_tasks = sub.add_parser("tasks")
    p_tasks.add_argument("list")
    p_tasks.add_argument("--all", action="store_true", help="include completed")
    p_add = sub.add_parser("add")
    p_add.add_argument("list")
    p_add.add_argument("title")
    p_done = sub.add_parser("complete")
    p_done.add_argument("list")
    p_done.add_argument("title")
    a = ap.parse_args()

    if a.cmd == "lists":
        for lst in get_lists():
            flag = " (default)" if lst.get("wellknownListName") == "defaultList" else ""
            print(f"{lst['displayName']}{flag}  [{lst['id']}]")
    elif a.cmd == "tasks":
        for t in get_tasks(a.list, include_done=a.all):
            mark = "x" if t.get("status") == "completed" else " "
            print(f"[{mark}] {t['title']}")
    elif a.cmd == "add":
        t = add_task(a.list, a.title)
        print(f"ADDED: {t['title']}  [{t['id']}]")
    elif a.cmd == "complete":
        t = complete_task(a.list, a.title)
        print(f"COMPLETED: {t['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
