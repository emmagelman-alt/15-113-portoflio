import asyncio
import dataclasses
import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.integrations import notion
from app.main import app
from app.models import Todo
from tests.conftest import login

DB_ID = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"
DS_ID = "d5000000-0000-0000-0000-000000000001"

STATUS_SCHEMA = {"type": "status", "status": {
    "options": [{"id": "o1", "name": "Not started"}, {"id": "o2", "name": "In progress"},
                {"id": "o3", "name": "Shipped"}, {"id": "o4", "name": "Done"}],
    "groups": [{"name": "To-do", "option_ids": ["o1"]}, {"name": "In progress", "option_ids": ["o2"]},
               {"name": "Complete", "option_ids": ["o3", "o4"]}]}}
SELECT_SCHEMA = {"type": "select", "select": {"options": [{"name": "Done"}, {"name": "To do"}, {"name": "Doing"}]}}


def person(email=None, uid=None):
    user = {"object": "user", "id": uid or f"user-{email}", "type": "person"}
    if email:
        user["person"] = {"email": email}
    return user


def page(pid, title, people=(), status="Not started", due=None, kind="status"):
    status_value = {"checkbox": status} if kind == "checkbox" else {kind: {"name": status} if status else None}
    return {"object": "page", "id": pid, "url": f"https://www.notion.so/{pid}", "in_trash": False, "properties": {
        "Task name": {"id": "title", "type": "title", "title": [{"plain_text": part} for part in title.split("|")]},
        "Assignee": {"type": "people", "people": [p if isinstance(p, dict) else person(p) for p in people]},
        "Status": {"type": kind, **status_value},
        "Due": {"type": "date", "date": {"start": due} if due else None},
    }}


class FakeNotion:
    """Just enough of the Notion API for the integration."""

    def __init__(self):
        self.status_schema = STATUS_SCHEMA
        self.pages = []
        self.users = {}
        self.calls = []
        self.patches = []
        self.queries = []
        self.fail = {}  # (method, path) -> status code, returned once
        self.on_query = None
        self.hide_trashed = True  # as the real API does

    def __call__(self, request):
        path = request.url.path[len("/v1"):]
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, path))
        assert request.headers["Notion-Version"] == notion.NOTION_VERSION
        assert request.headers["Authorization"] == "Bearer secret_test"
        if (request.method, path) in self.fail:
            code = self.fail.pop((request.method, path))
            return httpx.Response(code, headers={"Retry-After": "2"}, json={"code": "x", "message": "nope"})
        if request.method == "GET" and path == f"/databases/{DB_ID}":
            return httpx.Response(200, json={"object": "database", "data_sources": [{"id": DS_ID, "name": "Tasks"}]})
        if request.method == "GET" and path == f"/data_sources/{DS_ID}":
            return httpx.Response(200, json={"object": "data_source", "properties": {
                "Task name": {"type": "title", "title": {}}, "Assignee": {"type": "people", "people": {}},
                "Status": self.status_schema, "Due": {"type": "date", "date": {}}}})
        if request.method == "POST" and path == f"/data_sources/{DS_ID}/query":
            self.queries.append(body)
            if self.on_query:
                self.on_query()
            start = int(body.get("start_cursor") or 0)
            batch = [p for p in self.pages if p["properties"]["Assignee"]["people"]
                     and not (p["in_trash"] and self.hide_trashed)]
            more = start + 2 < len(batch)  # two per response, to exercise pagination
            return httpx.Response(200, json={"results": batch[start:start + 2], "has_more": more,
                                             "next_cursor": str(start + 2) if more else None})
        if request.method == "GET" and path.startswith("/users/") and path[7:] in self.users:
            return httpx.Response(200, json=person(self.users[path[7:]], path[7:]))
        if request.method == "PATCH" and path.startswith("/pages/"):
            self.patches.append((path[7:], body))
            return httpx.Response(200, json={"object": "page"})
        return httpx.Response(404, json={"code": "object_not_found", "message": "Not found"})


@pytest.fixture
def fake(monkeypatch):
    fake = FakeNotion()
    monkeypatch.setattr(notion, "settings", dataclasses.replace(
        notion.settings, notion_token="secret_test", notion_tasks_database_id=DB_ID,
        notion_assignee_property="Assignee", notion_status_property="Status",
        notion_due_property="Due", notion_done_statuses=["done"]))
    monkeypatch.setattr(notion, "transport", httpx.MockTransport(fake))
    monkeypatch.setattr(notion, "_sleep", lambda seconds: fake.calls.append(("sleep", seconds)))
    notion._data_sources.clear()
    notion._schemas.clear()
    yield fake
    if notion._executor:  # let queued pushes finish before the real settings come back
        notion._executor.submit(lambda: None).result(timeout=5)
    notion._data_sources.clear()
    notion._schemas.clear()


def notion_todos(client):
    return {t["source_url"].rsplit("/", 1)[-1]: t for t in client.get("/api/todos").json() if t["source"] == "notion"}


def stored(source_id):
    with SessionLocal() as db:
        return {t.owner.email: t.status for t in db.query(Todo).filter_by(source="notion", source_id=source_id)}


def test_property_parsing(fake):
    p = page("p1", "Design |mockup", status="Done", due="2026-10-10T09:00:00.000-04:00")
    assert notion.page_title(p) == "Design mockup"
    assert notion.page_due(p) == date(2026, 10, 10)
    assert notion.page_due(page("p2", "x")) is None
    assert notion.page_done(p) and notion.page_done(page("p", "x", status="DONE"))
    assert not notion.page_done(page("p", "x", status="In progress"))
    assert not notion.page_done(page("p", "x", status=None))
    assert notion.page_done(page("p", "x", status="Done", kind="select"))
    assert not notion.page_done(page("p", "x", status="To do", kind="select"))
    assert notion.page_done(page("p", "x", status=True, kind="checkbox"))
    assert not notion.page_done(page("p", "x", status=False, kind="checkbox"))
    # Options in a status property's Complete group count as done too
    done_names = notion._done_names({"Status": STATUS_SCHEMA})
    assert done_names == {"done", "shipped"} and notion.page_done(page("p", "x", status="Shipped"), done_names)
    assert notion.notion_id(f"https://www.notion.so/acme/Add-feed-{DB_ID}?v=ffffffffffffffffffffffffffffffff") == DB_ID


def test_sync_creates_todos_for_mapped_assignees(fake):
    emma, sam = login("emma@andean.test", "Emma"), login("sam@andean.test", "Sam")
    fake.users["u-sam"] = "Sam@andean.test"
    fake.pages = [
        page("p1", "Design mockup", ["emma@andean.test"], "In progress", "2026-10-10"),
        page("p2", "Ship beta", ["emma@andean.test", "sam@andean.test"], "Done"),
        page("p3", "Outside work", ["someone@else.com"]),
        page("p4", "Partial user", [person(uid="u-sam")]),  # page values without an email
        page("p5", "Nobody's"),
    ]
    counts = notion.sync()
    assert counts == {"pages": 4, "todos": 4, "created": 4, "removed": 0, "unmatched": 1}
    assert len(fake.queries) == 2 and fake.queries[1]["start_cursor"] == "2"
    assert fake.queries[0]["filter"] == {"property": "Assignee", "people": {"is_not_empty": True}}

    mine = notion_todos(emma)
    assert set(mine) == {"p1", "p2"}
    assert mine["p1"]["title"] == "Design mockup" and mine["p1"]["due_date"] == "2026-10-10"
    assert mine["p1"]["status"] == "open" and mine["p2"]["status"] == "done"
    assert mine["p1"]["source_url"] == "https://www.notion.so/p1"
    assert set(notion_todos(sam)) == {"p2", "p4"}


def test_resync_updates_and_removes(fake):
    emma, sam = login("emma@andean.test"), login("sam@andean.test")
    fake.pages = [page("p1", "Draft", ["emma@andean.test"], due="2026-10-10"),
                  page("p2", "Shared", ["emma@andean.test", "sam@andean.test"]),
                  page("p3", "Old", ["sam@andean.test"])]
    notion.sync()

    fake.pages[0] = page("p1", "Final", ["emma@andean.test"], "Shipped", "2026-11-01")
    fake.pages[1]["properties"]["Assignee"]["people"].pop(0)  # emma unassigned
    fake.pages[2]["in_trash"] = True
    counts = notion.sync()
    assert counts["created"] == 0 and counts["removed"] == 2

    mine = notion_todos(emma)
    assert set(mine) == {"p1"}
    assert mine["p1"]["title"] == "Final" and mine["p1"]["due_date"] == "2026-11-01" and mine["p1"]["status"] == "done"
    assert set(notion_todos(sam)) == {"p2"}

    fake.pages[0] = page("p1", "Final", ["emma@andean.test"], "In progress", "2026-11-01")
    fake.hide_trashed = False  # a trashed page in the results is still skipped
    notion.sync()
    assert notion_todos(emma)["p1"]["status"] == "open" and set(notion_todos(sam)) == {"p2"}


def test_dismissed_stays_dismissed(fake):
    emma = login("emma@andean.test")
    fake.pages = [page("p1", "Not for me", ["emma@andean.test"])]
    notion.sync()
    assert emma.delete(f"/api/todos/{notion_todos(emma)['p1']['id']}").status_code == 204

    fake.pages[0] = page("p1", "Not for me (edited)", ["emma@andean.test"], "Done")
    notion.sync()
    assert notion_todos(emma) == {} and stored("p1") == {"emma@andean.test": "dismissed"}
    # Unassigning and reassigning doesn't bring it back either
    fake.pages[0]["properties"]["Assignee"]["people"] = []
    notion.sync()
    fake.pages[0] = page("p1", "Not for me", ["emma@andean.test"])
    notion.sync()
    assert notion_todos(emma) == {}


def test_sync_waits_out_rate_limits_and_reports_errors(fake):
    emma = login("emma@andean.test")
    fake.pages = [page("p1", "Task", ["emma@andean.test"])]
    fake.fail[("POST", f"/data_sources/{DS_ID}/query")] = 429
    assert notion.sync()["todos"] == 1
    assert ("sleep", 2.0) in fake.calls

    # A failed sync changes nothing, and the next one re-reads the schema
    fake.pages = []
    fake.fail[("POST", f"/data_sources/{DS_ID}/query")] = 400
    with pytest.raises(notion.NotionError):
        notion.sync()
    assert set(notion_todos(emma)) == {"p1"} and notion._schemas == {}


def test_dashboard_checkoff_during_sync_is_kept(fake):
    emma = login("emma@andean.test")
    fake.pages = [page("p1", "Task", ["emma@andean.test"])]
    notion.sync()
    todo_id = notion_todos(emma)["p1"]["id"]
    # Emma checks it off after the sync has read Notion but before it writes
    fake.on_query = lambda: emma.patch(f"/api/todos/{todo_id}", json={"status": "done"})
    notion.sync()
    assert notion_todos(emma)["p1"]["status"] == "done"


def push(status, source_id="page-1"):
    future = notion.push_status(Todo(source="notion", source_id=source_id, status=status, title="x"))
    return future.result(timeout=5) if future else "skipped"


def test_push_status_payloads(fake):
    push("done")
    push("open")
    assert fake.patches == [("page-1", {"properties": {"Status": {"status": {"name": "Done"}}}}),
                            ("page-1", {"properties": {"Status": {"status": {"name": "Not started"}}}})]
    assert fake.calls.count(("GET", f"/data_sources/{DS_ID}")) == 1  # schema is cached

    # No option named like NOTION_DONE_STATUSES: use the first one in the Complete group
    fake.status_schema = {"type": "status", "status": {**STATUS_SCHEMA["status"], "options": STATUS_SCHEMA["status"]["options"][:3]}}
    notion._schemas.clear()
    fake.patches.clear()
    push("done")
    assert fake.patches[-1][1] == {"properties": {"Status": {"status": {"name": "Shipped"}}}}

    fake.status_schema = SELECT_SCHEMA
    notion._schemas.clear()
    push("done")
    push("open")
    assert [p[1]["properties"]["Status"] for p in fake.patches[-2:]] == [{"select": {"name": "Done"}}, {"select": {"name": "To do"}}]

    fake.status_schema = {"type": "checkbox", "checkbox": {}}
    notion._schemas.clear()
    push("done")
    push("open")
    assert [p[1]["properties"]["Status"] for p in fake.patches[-2:]] == [{"checkbox": True}, {"checkbox": False}]


def test_push_status_never_raises(fake, monkeypatch):
    fake.fail[("PATCH", "/pages/page-1")] = 500
    assert push("done") is None and fake.patches == []
    fake.status_schema = {"type": "select", "select": {"options": [{"name": "Backlog"}]}}  # no done option
    notion._schemas.clear()
    assert push("done") is None and fake.patches == []
    assert push("suggested") == "skipped"
    assert notion.push_status(Todo(source="slack", source_id="x", status="done")) is None
    monkeypatch.setattr(notion, "settings", dataclasses.replace(notion.settings, notion_token=""))
    assert push("done") == "skipped"


def test_checking_off_on_dashboard_updates_notion(fake):
    emma = login("emma@andean.test")
    fake.pages = [page("p1", "Task", ["emma@andean.test"])]
    notion.sync()
    todo = notion_todos(emma)["p1"]
    assert emma.patch(f"/api/todos/{todo['id']}", json={"status": "done"}).json()["status"] == "done"
    notion._executor.submit(lambda: None).result(timeout=5)  # wait for the queued push
    assert fake.patches == [("p1", {"properties": {"Status": {"status": {"name": "Done"}}}})]


def test_sync_endpoint_requires_login_and_csrf(fake):
    assert TestClient(app).post("/api/notion/sync").status_code in (401, 403)
    emma = login("emma@andean.test")
    token = emma.headers.pop("X-CSRF-Token")
    assert emma.post("/api/notion/sync").status_code == 403
    fake.pages = [page("p1", "Task", ["emma@andean.test"])]
    resp = emma.post("/api/notion/sync", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200 and resp.json()["created"] == 1

    fake.fail[("GET", f"/data_sources/{DS_ID}")] = 403
    notion._schemas.clear()
    assert emma.post("/api/notion/sync", headers={"X-CSRF-Token": token}).status_code == 502


def test_background_loop_survives_errors(fake):
    fake.fail[("GET", f"/databases/{DB_ID}")] = 404

    async def run():
        await notion.startup()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if ("GET", f"/data_sources/{DB_ID}") in fake.calls:
                break
        assert notion._task is not None and not notion._task.done()
        await notion.shutdown()
        assert notion._task is None

    asyncio.run(run())
    assert ("GET", f"/databases/{DB_ID}") in fake.calls
