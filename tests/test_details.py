import dataclasses
from datetime import date

import pytest

from app import details
from app.db import SessionLocal
from app.integrations import notion, slack
from app.integrations.common import employee_by_email, upsert_source_todo
from tests.conftest import login


def _synced(email, source, source_id, title="Task", url=None):
    with SessionLocal() as db:
        todo, _ = upsert_source_todo(db, owner=employee_by_email(db, email), source=source,
                                     source_id=source_id, title=title, source_url=url)
        db.commit()
        return todo.id


@pytest.fixture
def connected(monkeypatch):
    on = dataclasses.replace(details.settings, slack_bot_token="xoxb-test", slack_signing_secret="s",
                             notion_token="ntn_test", notion_tasks_database_id="db")
    monkeypatch.setattr(details, "settings", on)


def test_coworker_conversation_and_access():
    emma, sam, priya = login("emma@andean.test", "Emma G"), login("sam@andean.test", "Sam R"), login("priya@andean.test")
    emma_id = emma.get("/api/me").json()["id"]
    todo = sam.post("/api/todos", json={"title": "Review hero https://www.figma.com/design/abc123/Hero",
                                         "assignee_id": emma_id}).json()

    # Owner and sender can both see it and talk; anyone else can't see it at all
    assert emma.post(f"/api/todos/{todo['id']}/comments", json={"text": "Which frame?"}).status_code == 201
    assert sam.post(f"/api/todos/{todo['id']}/comments", json={"text": "The second one"}).status_code == 201
    assert priya.get(f"/api/todos/{todo['id']}/detail").status_code == 404
    assert priya.post(f"/api/todos/{todo['id']}/comments", json={"text": "hi"}).status_code == 404

    seen_by_emma = emma.get(f"/api/todos/{todo['id']}/detail").json()
    assert seen_by_emma["is_owner"] and [c["body"] for c in seen_by_emma["comments"]] == ["Which frame?", "The second one"]
    assert [c["is_me"] for c in seen_by_emma["comments"]] == [True, False]
    assert seen_by_emma["comments"][0]["created_at"].endswith(("+00:00", "Z"))
    [figma] = seen_by_emma["links"]
    assert figma["kind"] == "figma" and figma["embed"].startswith("https://www.figma.com/embed?")

    seen_by_sam = sam.get(f"/api/todos/{todo['id']}/detail").json()
    assert not seen_by_sam["is_owner"] and len(seen_by_sam["comments"]) == 2


def test_comments_require_csrf():
    client = login("emma@andean.test")
    todo = client.post("/api/todos", json={"title": "x"}).json()
    client.headers.pop("X-CSRF-Token")
    assert client.post(f"/api/todos/{todo['id']}/comments", json={"text": "hi"}).status_code == 403


def test_slack_thread_and_reply(connected, monkeypatch):
    client = login("emma@andean.test", "Emma G")
    todo_id = _synced("emma@andean.test", "slack", "C1:2.0", url="https://x.slack.com/archives/C1/p20")
    monkeypatch.setattr(slack, "thread", lambda todo: {"channel": "C1", "channel_name": "design", "messages": [
        {"ts": "1.0", "author": "Sam", "is_bot": False, "text": "Brief: https://docs.google.com/document/d/DOC1/edit",
         "files": [], "highlight": False},
        {"ts": "2.0", "author": "Sam", "is_bot": False, "text": "@Emma can you do it?", "files": [], "highlight": True}]})
    posted = []
    monkeypatch.setattr(slack, "post_reply", lambda todo, text, **kw: posted.append((todo.source_id, text, kw)))

    # Without a user token for Emma, replies go through the bot, signed with her name
    monkeypatch.setattr(slack, "reply_identity", lambda db: None)
    data = client.get(f"/api/todos/{todo_id}/detail").json()
    assert data["slack"]["channel_name"] == "design"
    assert data["slack"]["can_reply"] and data["slack"]["reply_as"] == "bot"
    [doc] = data["links"]
    assert doc["kind"] == "google" and doc["embed"] == "https://docs.google.com/document/d/DOC1/preview"
    assert client.post(f"/api/todos/{todo_id}/slack-reply", json={"text": "On it"}).json() == {"ok": True}
    assert posted[-1] == ("C1:2.0", "On it", {"author_name": "Emma G", "as_user": False, "files": []})
    assert client.post(f"/api/todos/{todo_id}/slack-reply", json={"text": "  "}).status_code == 400

    with SessionLocal() as db:
        emma = employee_by_email(db, "emma@andean.test")
    monkeypatch.setattr(slack, "reply_identity", lambda db: emma)
    assert client.get(f"/api/todos/{todo_id}/detail").json()["slack"]["reply_as"] == "you"
    client.post(f"/api/todos/{todo_id}/slack-reply", json={"text": "Done"})
    assert posted[-1][2]["as_user"] is True


def test_slack_reply_only_by_owner(connected, monkeypatch):
    login("emma@andean.test")
    sam = login("sam@andean.test")
    todo_id = _synced("emma@andean.test", "slack", "C1:3.0")
    monkeypatch.setattr(slack, "post_reply", lambda *a, **kw: pytest.fail("must not post"))
    with SessionLocal() as db:
        sam_employee = employee_by_email(db, "sam@andean.test")
    monkeypatch.setattr(slack, "reply_identity", lambda db: sam_employee)
    assert sam.get(f"/api/todos/{todo_id}/detail").status_code == 404
    assert sam.post(f"/api/todos/{todo_id}/slack-reply", json={"text": "x"}).status_code == 404


def test_notion_panel_edits(connected, monkeypatch):
    client = login("emma@andean.test", "Emma G")
    todo_id = _synced("emma@andean.test", "notion", "page1", url="https://app.notion.com/p/page1")
    monkeypatch.setattr(notion, "page_detail", lambda ref, with_comments=True: {
        "title": "Task", "url": "https://app.notion.com/p/page1", "status": "To do",
        "status_options": ["To do", "In progress", "Done"], "due_date": None, "assignees": ["Emma G"],
        "blocks": [{"type": "paragraph", "spans": [{"text": "Specs", "href": "https://www.figma.com/file/F1/Specs"}]}],
        "more_blocks": False, "comments": [], "comments_error": None})
    calls = []

    def update_page(page_id, **changes):
        calls.append((page_id, changes))
        return {"done": changes.get("status") == "Done", "due_date": changes.get("due_date")}

    monkeypatch.setattr(notion, "update_page", update_page)
    monkeypatch.setattr(notion, "add_comment", lambda page_id, text, name, files=(): calls.append((page_id, text, name)))

    data = client.get(f"/api/todos/{todo_id}/detail").json()
    assert data["notion"]["status_options"] == ["To do", "In progress", "Done"]
    assert [link["kind"] for link in data["links"]] == ["figma"]  # the page's own URL isn't listed

    done = client.patch(f"/api/todos/{todo_id}/notion", json={"status": "Done", "due_date": "2026-10-20"}).json()
    assert done["status"] == "done" and done["due_date"] == "2026-10-20"
    assert calls[-1] == ("page1", {"status": "Done", "due_date": date(2026, 10, 20)})

    cleared = client.patch(f"/api/todos/{todo_id}/notion", json={"due_date": None}).json()
    assert cleared["due_date"] is None and calls[-1] == ("page1", {"due_date": None})

    assert client.post(f"/api/todos/{todo_id}/notion-comments", json={"text": "Uploaded v2"}).status_code == 201
    assert calls[-1] == ("page1", "Uploaded v2", "Emma G")


def test_notion_status_must_be_an_option(connected, monkeypatch):
    client = login("emma@andean.test")
    todo_id = _synced("emma@andean.test", "notion", "page2")

    def reject(page_id, **changes):
        raise notion.NotionError(400, "bad_status", "'Nope' isn't an option for Status.")

    monkeypatch.setattr(notion, "update_page", reject)
    assert client.patch(f"/api/todos/{todo_id}/notion", json={"status": "Nope"}).status_code == 400


def test_link_detection():
    links = details.find_links([
        "See https://www.figma.com/design/K1/Name?node-id=1-2, and https://docs.google.com/spreadsheets/d/S1/edit#gid=0.",
        "Spec: https://app.notion.com/p/Spec-abc (also https://example.com/brief)",
        "dupe https://example.com/brief",
    ])
    assert [(item["kind"], item["label"]) for item in links] == [
        ("figma", "Figma file"), ("google", "Google Sheet"), ("notion", "Notion page"), ("link", "example.com")]
    assert links[0]["url"].endswith("node-id=1-2")
    assert links[1]["embed"] == "https://docs.google.com/spreadsheets/d/S1/preview"
    assert details.link_info("https://www.figma.com/community/plugin/1")["kind"] == "link"


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _upload(client, todo_id, name="mock.png", data=PNG, content_type="image/png"):
    return client.post(f"/api/todos/{todo_id}/attachments", files={"file": (name, data, content_type)})


def test_attachments_in_coworker_conversation():
    emma, sam, priya = login("emma@andean.test", "Emma G"), login("sam@andean.test", "Sam R"), login("priya@andean.test")
    emma_id = emma.get("/api/me").json()["id"]
    todo = sam.post("/api/todos", json={"title": "Hero", "assignee_id": emma_id}).json()

    up = _upload(emma, todo["id"], name="../../hero v2.png").json()
    assert up["name"] == "hero v2.png" and up["is_image"] and up["url"] == f"/files/{up['id']}/hero%20v2.png"
    doc = _upload(emma, todo["id"], name="notes.svg", data=b"<svg onload=alert(1)>", content_type="image/svg+xml").json()
    assert not doc["is_image"]

    sent = emma.post(f"/api/todos/{todo['id']}/comments", json={"text": "", "attachment_ids": [up["id"], doc["id"]]}).json()
    assert [f["name"] for f in sent["files"]] == ["hero v2.png", "notes.svg"]
    # Can't reuse a sent file, or someone else's upload
    assert emma.post(f"/api/todos/{todo['id']}/comments", json={"text": "again", "attachment_ids": [up["id"]]}).status_code == 400
    other = _upload(sam, todo["id"]).json()
    assert emma.post(f"/api/todos/{todo['id']}/comments", json={"text": "x", "attachment_ids": [other["id"]]}).status_code == 400

    [comment] = sam.get(f"/api/todos/{todo['id']}/detail").json()["comments"]
    assert [f["id"] for f in comment["files"]] == [up["id"], doc["id"]]

    image = sam.get(up["url"])  # the sender can open it
    assert image.status_code == 200 and image.content == PNG and image.headers["content-type"] == "image/png"
    assert image.headers["content-disposition"].startswith("inline") and "sandbox" in image.headers["content-security-policy"]
    svg = emma.get(doc["url"])  # risky types always download
    assert svg.headers["content-disposition"].startswith("attachment")
    assert svg.headers["content-type"] == "application/octet-stream"
    assert priya.get(up["url"]).status_code == 404
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get(up["url"], follow_redirects=False).headers["location"] == "/login"


def test_upload_limits():
    client = login("emma@andean.test")
    todo = client.post("/api/todos", json={"title": "x"}).json()
    assert _upload(client, todo["id"], data=b"").status_code == 400
    big = b"0" * (details.MAX_UPLOAD_BYTES + 1)
    assert _upload(client, todo["id"], name="big.bin", data=big, content_type="application/octet-stream").status_code == 413
    other = login("sam@andean.test")
    assert _upload(other, todo["id"]).status_code == 404
    client.headers.pop("X-CSRF-Token")
    assert _upload(client, todo["id"]).status_code == 403


def test_slack_reply_files_are_shared_links(connected, monkeypatch):
    client = login("emma@andean.test", "Emma G")
    priya = login("priya@andean.test")
    todo_id = _synced("emma@andean.test", "slack", "C1:4.0")
    monkeypatch.setattr(slack, "reply_identity", lambda db: None)
    posted = []
    monkeypatch.setattr(slack, "post_reply", lambda todo, text, **kw: posted.append(kw["files"]))
    up = _upload(client, todo_id, name="mock.png").json()
    assert priya.get(up["url"]).status_code == 404  # private until it's posted to Slack
    assert client.post(f"/api/todos/{todo_id}/slack-reply", json={"text": "Here", "attachment_ids": [up["id"]]}).status_code == 200
    [[f]] = posted
    assert f.name == "mock.png" and f.data == PNG and f.url.endswith(f"/files/{up['id']}/mock.png")
    assert priya.get(up["url"]).status_code == 200  # anyone at Andean following the Slack link can open it


def test_notion_comment_files_limit(connected, monkeypatch):
    client = login("emma@andean.test", "Emma G")
    todo_id = _synced("emma@andean.test", "notion", "page3")
    sent = []
    monkeypatch.setattr(notion, "add_comment", lambda page_id, text, name, files=(): sent.append(files))
    ids = [_upload(client, todo_id, name=f"f{i}.png").json()["id"] for i in range(4)]
    assert client.post(f"/api/todos/{todo_id}/notion-comments", json={"text": "", "attachment_ids": ids}).status_code == 400
    assert client.post(f"/api/todos/{todo_id}/notion-comments", json={"text": "", "attachment_ids": ids[:3]}).status_code == 201
    assert [name for name, _, _ in sent[0]] == ["f0.png", "f1.png", "f2.png"]
