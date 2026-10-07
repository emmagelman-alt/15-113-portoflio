import asyncio
import dataclasses
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode.request import SocketModeRequest

from app.integrations import slack
from app.main import app
from tests.conftest import login

SECRET = "test-signing-secret"
PERMALINK = "https://andean-sandbox.slack.com/archives/C1/p1700000000000100"
USERS = {
    "UBOT": {"id": "UBOT", "is_bot": True, "profile": {"display_name": "Andean Dashboard"}},
    "UEMMA": {"id": "UEMMA", "profile": {"display_name": "Emma", "real_name": "Emma Gelman", "email": "Emma@andean.test"}},
    "USAM": {"id": "USAM", "profile": {"display_name": "sam", "real_name": "Sam Rivera", "email": "sam@andean.test"}},
    "UGUS": {"id": "UGUS", "profile": {"display_name": "gus", "real_name": "Gus Guest", "email": "gus@elsewhere.test"}},
}


class FakeSlack:
    """Stands in for both WebClient and WebhookClient; records what would have been sent."""

    def __init__(self):
        self.calls = []
        self.replies = []
        self.permalink_fails = False
        self.thread = []
        self.posted = []

    def auth_test(self):
        return {"user_id": "UBOT", "url": "https://andean-sandbox.slack.com/"}

    def users_info(self, user):
        self.calls.append(("users.info", user))
        if user not in USERS:
            raise SlackApiError("user_not_found", {"ok": False, "error": "user_not_found"})
        return {"user": USERS[user]}

    def conversations_info(self, channel):
        return {"channel": {"id": channel, "name": "design"}}

    def chat_getPermalink(self, channel, message_ts):
        self.calls.append(("chat.getPermalink", message_ts))
        if self.permalink_fails:
            raise SlackApiError("channel_not_found", {"ok": False, "error": "channel_not_found"})
        return {"permalink": f"https://andean-sandbox.slack.com/archives/{channel}/p{message_ts.replace('.', '')}"}

    def conversations_replies(self, channel, ts, limit):
        self.calls.append(("conversations.replies", ts))
        return {"messages": self.thread}

    def chat_postMessage(self, **kwargs):
        self.posted.append(kwargs)

    def chat_postEphemeral(self, **kwargs):
        self.replies.append(kwargs["text"])

    def send(self, text, response_type):
        assert response_type == "ephemeral"
        self.replies.append(text)
        return type("Resp", (), {"status_code": 200, "body": "ok"})()


@pytest.fixture
def fake(monkeypatch):
    api = FakeSlack()
    monkeypatch.setattr(slack, "WebClient", lambda token=None, **_: api)
    monkeypatch.setattr(slack, "WebhookClient", lambda url, **_: api)
    monkeypatch.setattr(slack, "settings", dataclasses.replace(
        slack.settings, slack_bot_token="xoxb-test", slack_signing_secret=SECRET, slack_app_token="",
        base_url="https://dashboard.andean.test"))
    monkeypatch.setattr(slack, "_cache", {})
    return api


def signed_post(path, body, *, secret=SECRET, timestamp=None, content_type="application/json"):
    ts = str(int(time.time()) if timestamp is None else timestamp)
    signature = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return TestClient(app).post(path, content=body, headers={
        "Content-Type": content_type, "X-Slack-Request-Timestamp": ts, "X-Slack-Signature": signature})


def send_event(event, **kwargs):
    body = json.dumps({"type": "event_callback", "event_id": "Ev1", "event": event}).encode()
    return signed_post("/slack/events", body, **kwargs)


def message(text, user="USAM", ts="1700000000.000100", **extra):
    return {"type": "message", "channel": "C1", "channel_type": "channel", "user": user, "text": text, "ts": ts, **extra}


def shortcut(user="UEMMA", text="Please review the <https://andean.test/copy|launch copy>", author="USAM"):
    payload = {
        "type": "message_action", "callback_id": "add_to_dashboard",
        "user": {"id": user}, "channel": {"id": "C1", "name": "design"},
        "message": {"type": "message", "user": author, "text": text, "ts": "1700000000.000100"},
        "message_ts": "1700000000.000100", "response_url": "https://hooks.slack.com/actions/T1/1/abc",
    }
    body = urlencode({"payload": json.dumps(payload)}).encode()
    return signed_post("/slack/interactions", body, content_type="application/x-www-form-urlencoded")


def test_rejects_bad_or_missing_signature(fake):
    emma = login("emma@andean.test")
    body = json.dumps({"type": "event_callback", "event": message("<@UEMMA> hi")}).encode()
    assert signed_post("/slack/events", body, secret="wrong").status_code == 401
    assert TestClient(app).post("/slack/events", content=body).status_code == 401
    assert TestClient(app).post("/slack/interactions", content=b"payload=%7B%7D").status_code == 401
    assert emma.get("/api/todos").json() == []


def test_rejects_stale_timestamp(fake):
    login("emma@andean.test")
    assert send_event(message("<@UEMMA> hi"), timestamp=int(time.time()) - 600).status_code == 401
    assert send_event(message("<@UEMMA> hi"), timestamp="not-a-number").status_code == 401


def test_url_verification(fake):
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    resp = signed_post("/slack/events", body)
    assert resp.status_code == 200 and resp.json() == {"challenge": "abc123"}


def test_unconfigured_returns_404(fake, monkeypatch):
    monkeypatch.setattr(slack, "settings", dataclasses.replace(slack.settings, slack_bot_token="", slack_signing_secret=""))
    assert TestClient(app).post("/slack/events", content=b"{}").status_code == 404
    assert TestClient(app).post("/slack/interactions", content=b"").status_code == 404


def test_mention_creates_suggested_todo(fake):
    emma = login("emma@andean.test", "Emma Gelman")
    sam = login("sam@andean.test", "Sam Rivera")
    text = "<@UEMMA> can you make a *design* for the <https://andean.test/tools|tools page>? &amp; thanks"
    assert send_event(message(text)).status_code == 200

    [todo] = emma.get("/api/todos").json()
    assert todo["status"] == "suggested" and todo["source"] == "slack"
    assert todo["title"] == "@Emma can you make a design for the tools page? & thanks"
    assert todo["source_url"] == PERMALINK
    assert todo["created_by"]["name"] == "Sam Rivera"
    assert todo["notes"] == "#design"  # the dashboard already shows "From Sam Rivera"
    assert sam.get("/api/todos").json() == []


def test_thread_reply_from_non_employee(fake):
    emma = login("emma@andean.test")
    fake.permalink_fails = True
    send_event(message("<@UEMMA> could you look at this?", user="UGUS", ts="1700000001.000200",
                       thread_ts="1700000000.000100"))
    [todo] = emma.get("/api/todos").json()
    assert todo["created_by"] is None and todo["notes"] == "#design · from Gus Guest"
    # Falls back to building the link from the workspace URL
    assert todo["source_url"] == ("https://andean-sandbox.slack.com/archives/C1/p1700000001000200"
                                  "?thread_ts=1700000000.000100&cid=C1")


def test_unmapped_users_ignored(fake):
    emma = login("emma@andean.test")
    assert send_event(message("<@UGUS> and <@UNOBODY> please check")).status_code == 200
    assert emma.get("/api/todos").json() == []
    assert ("chat.getPermalink", "1700000000.000100") not in fake.calls


def test_bot_and_system_messages_ignored(fake):
    emma = login("emma@andean.test")
    send_event(message("<@UEMMA> deploy finished", subtype="bot_message", bot_id="B1"))
    send_event(message("<@UEMMA> deploy finished", bot_id="B1"))
    send_event(message("<@UEMMA> has joined the channel", subtype="channel_join"))
    send_event(message("<@UBOT> what's on my list?"))
    send_event(dict(message("<@UEMMA> in a DM"), channel_type="im"))
    assert emma.get("/api/todos").json() == []


def test_self_mention_ignored(fake):
    emma = login("emma@andean.test")
    send_event(message("note to <@UEMMA>: buy coffee", user="UEMMA"))
    assert emma.get("/api/todos").json() == []
    assert fake.calls == []  # nothing to do, so no Slack calls either


def test_duplicate_event_is_idempotent(fake):
    emma = login("emma@andean.test")
    send_event(message("<@UEMMA> can you review the deck?"))
    [todo] = emma.get("/api/todos").json()
    emma.patch(f"/api/todos/{todo['id']}", json={"status": "open", "due_date": "2026-10-20"})

    send_event(message("<@UEMMA> can you review the deck?"))  # Slack retry
    [again] = emma.get("/api/todos").json()
    assert again["id"] == todo["id"] and again["status"] == "open" and again["due_date"] == "2026-10-20"


def test_message_changed_updates_title(fake):
    emma = login("emma@andean.test")
    send_event(message("<@UEMMA> can you review the deck?"))
    edited = message("<@UEMMA> can you review the *final* deck by Friday?")
    send_event({"type": "message", "subtype": "message_changed", "channel": "C1", "channel_type": "channel",
                "hidden": True, "ts": "1700000099.000000", "message": edited})
    [todo] = emma.get("/api/todos").json()
    assert todo["title"] == "@Emma can you review the final deck by Friday?" and todo["status"] == "suggested"


def test_shortcut_creates_open_todo(fake):
    emma = login("emma@andean.test", "Emma Gelman")
    login("sam@andean.test", "Sam Rivera")
    assert shortcut().status_code == 200
    [todo] = emma.get("/api/todos").json()
    assert todo["status"] == "open" and todo["title"] == "Please review the launch copy"
    assert todo["source_url"] == PERMALINK and todo["created_by"]["name"] == "Sam Rivera"
    assert fake.replies == ["Saved to your <https://dashboard.andean.test|Andean Dashboard>: Please review the launch copy"]

    # Clicking again doesn't duplicate it
    shortcut()
    assert len(emma.get("/api/todos").json()) == 1


def test_shortcut_accepts_suggestion_and_restores_dismissed(fake):
    emma = login("emma@andean.test")
    send_event(message("<@UEMMA> Please review the launch copy"))
    [todo] = emma.get("/api/todos").json()
    emma.delete(f"/api/todos/{todo['id']}")
    shortcut(text="<@UEMMA> Please review the launch copy")
    [again] = emma.get("/api/todos").json()
    assert again["id"] == todo["id"] and again["status"] == "open"


def test_shortcut_from_unknown_user_asks_them_to_sign_in(fake):
    emma = login("emma@andean.test")
    shortcut(user="UGUS")
    assert emma.get("/api/todos").json() == []
    assert len(fake.replies) == 1 and "Sign in to the" in fake.replies[0]


def test_title_cleanup(fake):
    long = "<@UEMMA> " + "please update the pricing table " * 10
    title = slack._title(fake, long)
    assert len(title) <= slack.TITLE_LENGTH and title.endswith("…") and title.startswith("@Emma please")
    assert slack._title(fake, "<!here> see <#C9|launch>, `api_v2` and <mailto:a@andean.test|a@andean.test>") == \
        "@here see #launch, api_v2 and a@andean.test"


def test_socket_mode_acks_then_dispatches(fake, monkeypatch):
    events = []

    class FakeSocket:
        def __init__(self, app_token, web_client):
            self.app_token, self.socket_mode_request_listeners, self.sent = app_token, [], []
            self.connected = self.closed = False

        def connect(self):
            self.connected = True

        def close(self):
            self.closed = True

        def send_socket_mode_response(self, response):
            self.sent.append(response.envelope_id)
            events.append("ack")

    monkeypatch.setattr(slack, "SocketModeClient", FakeSocket)
    monkeypatch.setattr(slack, "settings", dataclasses.replace(slack.settings, slack_app_token="xapp-test"))
    monkeypatch.setattr(slack, "handle_event", lambda payload: events.append("event"))
    monkeypatch.setattr(slack, "handle_interaction", lambda payload: events.append("interaction"))

    asyncio.run(slack.startup())
    client = slack._socket
    assert client.connected and client.app_token == "xapp-test"
    [listener] = client.socket_mode_request_listeners
    listener(client, SocketModeRequest(type="events_api", envelope_id="e1", payload={"type": "event_callback"}))
    listener(client, SocketModeRequest(type="interactive", envelope_id="e2", payload={"type": "message_action"}))
    assert client.sent == ["e1", "e2"] and events == ["ack", "event", "ack", "interaction"]

    asyncio.run(slack.shutdown())
    assert client.closed and slack._socket is None


def test_thread_for_task_panel(fake):
    from app.models import Todo
    fake.thread = [
        {"ts": "1.0", "thread_ts": "1.0", "user": "USAM", "text": "Kickoff: *brief* in <https://docs.google.com/document/d/D1/edit|the doc>"},
        {"ts": "2.0", "thread_ts": "1.0", "user": "USAM", "text": "<@UEMMA> can you do\nthe banners?",
         "files": [{"name": "ref.png", "permalink": "https://files.test/ref"}]},
        {"ts": "3.0", "thread_ts": "1.0", "bot_id": "B1", "bot_profile": {"name": "Andean Dashboard"}, "text": "Saved"},
    ]
    data = slack.thread(Todo(source="slack", source_id="C1:2.0"))
    assert data["channel_name"] == "design"
    first, request, bot = data["messages"]
    assert first["text"] == "Kickoff: brief in the doc (https://docs.google.com/document/d/D1/edit)"
    assert request["highlight"] and request["text"] == "@Emma can you do\nthe banners?"
    assert request["author"] == "Sam Rivera" and request["files"] == [{"name": "ref.png", "url": "https://files.test/ref"}]
    assert bot["is_bot"] and bot["author"] == "Andean Dashboard"


def test_reply_posts_in_thread_as_user(fake, monkeypatch):
    from app.models import Todo
    monkeypatch.setattr(slack, "settings", dataclasses.replace(slack.settings, slack_user_token="xoxp-test"))
    fake.thread = [{"ts": "1.0", "thread_ts": "1.0", "user": "USAM", "text": "root"}]
    slack.post_reply(Todo(source="slack", source_id="C1:2.0"), "On it")
    assert fake.posted == [{"channel": "C1", "thread_ts": "1.0", "text": "On it"}]
