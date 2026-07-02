"""Mocked-Graph unit tests for todo.py — no network, no credentials.

Verify each CLI operation builds the correct Graph URL/payload and parses the
response. `get_token` and `requests` are stubbed so nothing touches Graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import todo  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"
LISTS = {"value": [{"id": "L1", "displayName": "Groceries", "wellknownListName": "defaultList"}]}


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeRequests:
    """Records calls and returns URL-routed canned responses."""

    def __init__(self, tasks: dict | None = None):
        self.tasks = tasks or {"value": []}
        self.calls: list[tuple[str, str, dict | None]] = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        if url.endswith("/me/todo/lists"):
            return _Resp(LISTS)
        return _Resp(self.tasks)

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        return _Resp({"id": "T99", "title": json.get("title", "")})

    def patch(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("PATCH", url, json))
        return _Resp({"id": "T1", "title": "Milk", "status": "completed"})


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(todo, "get_token", lambda: "FAKE_TOKEN")
    fr = _FakeRequests()
    monkeypatch.setattr(todo, "requests", fr)
    return fr


def test_get_lists_url_and_parse(fake):
    lists = todo.get_lists()
    assert fake.calls[0] == ("GET", f"{GRAPH}/me/todo/lists", None)
    assert lists[0]["displayName"] == "Groceries"


def test_resolve_list_id_matches_by_name(fake):
    assert todo._resolve_list_id("groceries") == "L1"  # case-insensitive


def test_resolve_list_id_unknown_raises(fake):
    with pytest.raises(SystemExit):
        todo._resolve_list_id("Nope")


def test_get_tasks_url_and_filters_completed(fake):
    fake.tasks = {"value": [
        {"id": "T1", "title": "Milk", "status": "notStarted"},
        {"id": "T2", "title": "Old", "status": "completed"},
    ]}
    open_tasks = todo.get_tasks("Groceries")
    # last GET is the tasks call against the resolved list id
    assert fake.calls[-1][1] == f"{GRAPH}/me/todo/lists/L1/tasks"
    assert [t["title"] for t in open_tasks] == ["Milk"]  # completed filtered out


def test_get_tasks_include_done(fake):
    fake.tasks = {"value": [
        {"id": "T1", "title": "Milk", "status": "notStarted"},
        {"id": "T2", "title": "Old", "status": "completed"},
    ]}
    all_tasks = todo.get_tasks("Groceries", include_done=True)
    assert len(all_tasks) == 2


def test_add_task_payload(fake):
    todo.add_task("Groceries", "Bread")
    method, url, body = fake.calls[-1]
    assert method == "POST"
    assert url == f"{GRAPH}/me/todo/lists/L1/tasks"
    assert body == {"title": "Bread"}  # no dueDateTime when due omitted


def test_add_task_with_due(fake):
    todo.add_task("Groceries", "Rent", due="2026-07-05")
    _, _, body = fake.calls[-1]
    assert body["title"] == "Rent"
    assert body["dueDateTime"] == {
        "dateTime": "2026-07-05T00:00:00",
        "timeZone": "Pacific Standard Time",
    }


def test_complete_task_patches_resolved_task(fake):
    fake.tasks = {"value": [{"id": "T1", "title": "Milk", "status": "notStarted"}]}
    todo.complete_task("Groceries", "milk")  # case-insensitive title match
    method, url, body = fake.calls[-1]
    assert method == "PATCH"
    assert url == f"{GRAPH}/me/todo/lists/L1/tasks/T1"
    assert body == {"status": "completed"}


def test_complete_task_not_found_raises(fake):
    fake.tasks = {"value": [{"id": "T1", "title": "Milk", "status": "notStarted"}]}
    with pytest.raises(SystemExit):
        todo.complete_task("Groceries", "Nonexistent")


def test_headers_carry_bearer_token(fake):
    assert todo._headers()["Authorization"] == "Bearer FAKE_TOKEN"
