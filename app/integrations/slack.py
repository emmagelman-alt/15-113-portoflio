"""Slack integration: an @mention in a channel becomes a *suggested* to-do for the mentioned
employee, and the "Add to dashboard" message shortcut saves any message as an open to-do.

Slack reaches the app over Socket Mode when SLACK_APP_TOKEN is set (local development, no
public URL needed), otherwise over HTTP at /slack/events and /slack/interactions. Both
transports call handle_event / handle_interaction. Slack users map to employees by email.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from slack_sdk import WebClient
from slack_sdk.errors import SlackClientError
from slack_sdk.signature import SignatureVerifier
from slack_sdk.socket_mode.builtin import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.webhook import WebhookClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import Employee, Todo
from .common import employee_by_email, set_status, upsert_source_todo

logger = logging.getLogger(__name__)
router = APIRouter()

SHORTCUT_ID = "add_to_dashboard"
TITLE_LENGTH = 140
CACHE_SECONDS = 300
# Ordinary user messages. Joins, edits, bot posts, etc. carry other subtypes.
MESSAGE_SUBTYPES = (None, "thread_broadcast", "file_share")
SLACK_ERRORS = (SlackClientError, OSError)  # API errors plus network failures

_USER_REF = re.compile(r"<@([UW][A-Z0-9]+)(?:\|([^>]*))?>")
_REF = re.compile(r"<([^>|]*)(?:\|([^>]*))?>")
_FORMATTING = re.compile(r"(?<!\w)(\*|_|~|`{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)", re.S)

_cache: Dict[str, Any] = {}  # key -> (expires_at, value)
_socket: Optional[SocketModeClient] = None


# --- Slack lookups (cached briefly; failures are logged and return None) ---

def _client() -> WebClient:
    return WebClient(token=settings.slack_bot_token)


def _cached(key: str, fetch: Callable[[], Any]) -> Any:
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        value = fetch()
    except SLACK_ERRORS as e:
        logger.warning("Slack lookup %s failed: %s", key, e)
        return None
    _cache[key] = (time.monotonic() + CACHE_SECONDS, value)
    return value


def _identity(client: WebClient) -> Dict[str, Any]:
    """The bot's own user id and the workspace URL."""
    def fetch() -> Dict[str, Any]:
        resp = client.auth_test()
        return {"user_id": resp.get("user_id"), "url": resp.get("url")}
    return _cached("auth", fetch) or {}


def _user(client: WebClient, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    return _cached(f"user:{user_id}", lambda: client.users_info(user=user_id)["user"])


def _channel_name(client: WebClient, channel_id: str) -> Optional[str]:
    info = _cached(f"channel:{channel_id}", lambda: client.conversations_info(channel=channel_id)["channel"])
    return (info or {}).get("name")


def _name(user: Optional[Dict[str, Any]], full: bool = False) -> str:
    profile = (user or {}).get("profile") or {}
    first, second = ("real_name", "display_name") if full else ("display_name", "real_name")
    return profile.get(first) or profile.get(second) or (user or {}).get("name") or "someone"


def _employee(db: Session, client: WebClient, user_id: Optional[str]) -> Optional[Employee]:
    user = _user(client, user_id)
    if not user or user.get("is_bot") or user.get("deleted"):
        return None
    return employee_by_email(db, (user.get("profile") or {}).get("email"))


def _permalink(client: WebClient, channel: str, ts: str, thread_ts: Optional[str] = None) -> Optional[str]:
    try:
        return client.chat_getPermalink(channel=channel, message_ts=ts)["permalink"]
    except SLACK_ERRORS as e:
        logger.warning("chat.getPermalink failed for %s/%s: %s", channel, ts, e)
    base = _identity(client).get("url")
    if not base:
        return None
    url = f"{base.rstrip('/')}/archives/{channel}/p{ts.replace('.', '')}"
    return url + f"?thread_ts={thread_ts}&cid={channel}" if thread_ts and thread_ts != ts else url


# --- Turning a message into a to-do ---

def _ref(match: re.Match) -> str:
    """<#C1|general>, <!here>, <!subteam^S1|@design>, <https://x|label>, <mailto:a@b|a@b>."""
    target, label = match.group(1), match.group(2)
    if target.startswith("#"):
        return "#" + (label or "channel")
    if target.startswith("!"):
        keyword = target[1:].split("^")[0]
        return label or (f"@{keyword}" if keyword in ("here", "channel", "everyone") else "")
    return label or target.replace("mailto:", "", 1)


def _title(client: WebClient, text: Optional[str]) -> str:
    """Readable one-line title: mentions become @names and Slack markup is removed."""
    def mention(m: re.Match) -> str:
        user = _user(client, m.group(1))
        return "@" + (_name(user) if user else m.group(2) or "someone")

    text = _REF.sub(_ref, _USER_REF.sub(mention, text or ""))
    text = html.unescape(text)
    for _ in range(2):  # nested formatting like *_this_*
        text = _FORMATTING.sub(r"\2", text)
    text = " ".join(re.sub(r"(?m)^>\s?", "", text).split())
    if len(text) > TITLE_LENGTH:
        cut = text[:TITLE_LENGTH - 1]
        if " " in cut[TITLE_LENGTH // 2:]:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(" ,.;:-") + "…"
    return text


def _notes(client: WebClient, channel: str, author_id: Optional[str], created_by: Optional[Employee],
           channel_name: Optional[str] = None) -> str:
    """Meta line such as "#design" or "#design · from Gus Guest". When the author is an
    employee the dashboard already shows "From <name>", so it isn't repeated here."""
    if channel.startswith("D") or (channel_name or "").startswith(("directmessage", "mpdm-")):
        parts = ["Direct message"]
    else:
        # Shortcut payloads carry the name, except "privategroup" for private channels
        name = channel_name if channel_name and channel_name != "privategroup" else _channel_name(client, channel)
        parts = [f"#{name}" if name else ""]
    if created_by is None and author_id:
        parts.append("from " + _name(_user(client, author_id), full=True))
    return " · ".join(p for p in parts if p)


def _save(db: Session, owner: Employee, source_id: str, *, notes: str, accept: bool = False, **fields: Any) -> Todo:
    """upsert_source_todo, keeping any due date the employee set on the dashboard.
    `accept` (an explicit click) also opens a suggestion or restores a dismissed to-do."""
    existing = db.scalar(select(Todo).where(
        Todo.owner_id == owner.id, Todo.source == "slack", Todo.source_id == source_id))
    if existing is not None and accept and existing.status in ("suggested", "dismissed"):
        set_status(existing, "open")
    todo, _ = upsert_source_todo(db, owner=owner, source="slack", source_id=source_id,
                                 due_date=existing.due_date if existing else None, **fields)
    if todo.status != "dismissed":
        todo.notes = notes
    return todo


def _message(event: Dict[str, Any]) -> None:
    author_id, channel, ts = event.get("user"), event.get("channel"), event.get("ts")
    text = event.get("text") or ""
    mentioned = [uid for uid in dict.fromkeys(m.group(1) for m in _USER_REF.finditer(text)) if uid != author_id]
    if not (author_id and channel and ts and mentioned):
        return
    client = _client()
    bot_id = _identity(client).get("user_id")
    with SessionLocal() as db:
        owners = {e.id: e for e in (_employee(db, client, uid) for uid in mentioned if uid != bot_id) if e}
        if not owners:
            return
        created_by = _employee(db, client, author_id)
        fields = dict(
            title=_title(client, text) or f"Slack message from {_name(_user(client, author_id), full=True)}",
            source_url=_permalink(client, channel, ts, event.get("thread_ts")),
            notes=_notes(client, channel, author_id, created_by),
            created_by=created_by,
            initial_status="suggested",
        )
        for owner in owners.values():
            _save(db, owner, f"{channel}:{ts}", **fields)
        _commit(db)


def _message_changed(event: Dict[str, Any]) -> None:
    """An edited message refreshes the title of to-dos already made from it."""
    message = event.get("message") or {}
    source_id = f"{event.get('channel')}:{message.get('ts')}"
    with SessionLocal() as db:
        todos = db.scalars(select(Todo).where(
            Todo.source == "slack", Todo.source_id == source_id, Todo.status != "dismissed")).all()
        title = _title(_client(), message.get("text")) if todos else ""
        if not title:
            return
        for todo in todos:
            todo.title = title
        _commit(db)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:  # the same event processed concurrently (a Slack retry); the other copy won
        db.rollback()
        logger.info("Skipped a duplicate Slack to-do")


def handle_event(payload: Dict[str, Any]) -> None:
    """Events API callback from either transport. Safe to repeat (Slack retries)."""
    event = payload.get("event") or {}
    if payload.get("type") != "event_callback" or event.get("type") != "message":
        return
    try:
        if event.get("subtype") == "message_changed":
            _message_changed(event)
        elif (event.get("subtype") in MESSAGE_SUBTYPES and not event.get("bot_id")
              and event.get("channel_type") in ("channel", "group")):
            _message(event)
    except Exception:
        logger.exception("Slack event %s failed", payload.get("event_id"))


# --- "Add to dashboard" message shortcut ---

def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _reply(client: WebClient, payload: Dict[str, Any], text: str) -> None:
    """Ephemeral message to whoever clicked. response_url works even where the bot isn't a member."""
    url = payload.get("response_url") or ""
    try:
        if url.startswith("https://hooks.slack.com/"):
            resp = WebhookClient(url).send(text=text, response_type="ephemeral")
            if resp.status_code != 200:
                logger.warning("Slack response_url returned %s: %s", resp.status_code, resp.body)
        else:
            client.chat_postEphemeral(channel=(payload.get("channel") or {}).get("id"),
                                      user=(payload.get("user") or {}).get("id"), text=text)
    except SLACK_ERRORS as e:
        logger.warning("Could not send Slack confirmation: %s", e)


def _add_to_dashboard(client: WebClient, payload: Dict[str, Any]) -> None:
    channel = payload.get("channel") or {}
    message = payload.get("message") or {}
    ts = payload.get("message_ts") or message.get("ts")
    dashboard = f"<{settings.base_url}|Andean Dashboard>"
    with SessionLocal() as db:
        owner = _employee(db, client, (payload.get("user") or {}).get("id"))
        if owner is None:
            _reply(client, payload, f"Sign in to the {dashboard} with your work email first, then try again.")
            return
        author_id = message.get("user")
        created_by = _employee(db, client, author_id)
        title = _title(client, message.get("text")) or "Slack message"
        _save(db, owner, f"{channel.get('id')}:{ts}", title=title, accept=True, created_by=created_by,
              source_url=_permalink(client, channel.get("id"), ts, message.get("thread_ts")),
              notes=_notes(client, channel.get("id"), author_id, created_by, channel.get("name")))
        _commit(db)
    _reply(client, payload, f"Saved to your {dashboard}: {_escape(title)}")


def handle_interaction(payload: Dict[str, Any]) -> None:
    """Interactivity payload from either transport."""
    if payload.get("type") != "message_action" or payload.get("callback_id") != SHORTCUT_ID:
        return
    client = _client()
    try:
        _add_to_dashboard(client, payload)
    except Exception:
        logger.exception("Slack shortcut failed")
        _reply(client, payload, "Sorry, that message couldn't be added to your dashboard. Please try again.")


# --- Task panel: read the thread, reply as the employee ---

def _readable(client: WebClient, text: Optional[str]) -> str:
    """Full message text for the panel: @names, plain URLs, Slack markup removed, newlines kept."""
    def mention(m: re.Match) -> str:
        user = _user(client, m.group(1))
        return "@" + (_name(user) if user else m.group(2) or "someone")

    def ref(m: re.Match) -> str:
        target, label = m.group(1), m.group(2)
        if target.startswith(("http://", "https://")):
            return target if not label or label in target else f"{label} ({target})"
        return _ref(m)

    text = html.unescape(_REF.sub(ref, _USER_REF.sub(mention, text or "")))
    for _ in range(2):
        text = _FORMATTING.sub(r"\2", text)
    return text.strip()


def _split(todo: Todo) -> Tuple[str, str]:
    channel, _, ts = (todo.source_id or "").partition(":")
    if not channel or not ts:
        raise ValueError("This to-do isn't linked to a Slack message.")
    return channel, ts


def _replies(client: WebClient, channel: str, ts: str) -> List[Dict[str, Any]]:
    messages = client.conversations_replies(channel=channel, ts=ts, limit=100)["messages"]
    root = messages[0].get("thread_ts") or messages[0]["ts"] if messages else ts
    if messages and messages[0]["ts"] != root:  # ts was a reply; fetch from the top of the thread
        messages = client.conversations_replies(channel=channel, ts=root, limit=100)["messages"]
    return messages


def thread(todo: Todo) -> Dict[str, Any]:
    """The Slack thread a to-do came from, oldest first, with the request itself highlighted."""
    channel, ts = _split(todo)
    client = _client()
    messages = _replies(client, channel, ts)
    out = []
    for m in messages:
        bot_name = (m.get("bot_profile") or {}).get("name") or m.get("username")
        user = None if bot_name else _user(client, m.get("user"))
        out.append({
            "ts": m["ts"],
            "author": bot_name or _name(user, full=True),
            "is_bot": bool(bot_name),
            "text": _readable(client, m.get("text")),
            "files": [{"name": f.get("name") or f.get("title") or "file", "url": f.get("permalink")}
                      for f in m.get("files") or [] if f.get("permalink")],
            "highlight": m["ts"] == ts,
        })
    return {"channel": channel, "channel_name": _channel_name(client, channel), "messages": out}


def reply_identity(db: Session) -> Optional[Employee]:
    """The employee whose Slack user token is configured, if any."""
    if not settings.slack_user_token:
        return None
    ident = _cached("user-token", lambda: WebClient(token=settings.slack_user_token).auth_test().data)
    return _employee(db, _client(), (ident or {}).get("user_id"))


def post_reply(todo: Todo, text: str) -> None:
    """Reply in the to-do's thread as the person who owns the user token. Raises SlackApiError."""
    channel, ts = _split(todo)
    messages = _replies(_client(), channel, ts)
    root = messages[0]["ts"] if messages else ts
    WebClient(token=settings.slack_user_token).chat_postMessage(channel=channel, thread_ts=root, text=text)


# --- HTTP transport ---

async def _verified_body(request: Request) -> bytes:
    """Raw body of a genuine Slack request: valid signature, timestamp within 5 minutes."""
    if not settings.slack_configured:
        raise HTTPException(status_code=404)
    body = await request.body()
    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")
    if not timestamp.isdigit() or not SignatureVerifier(settings.slack_signing_secret).is_valid(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")
    return body


def _json(raw: Any) -> Dict[str, Any]:
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload.")
    return payload


@router.post("/slack/events")
async def slack_events(request: Request, background: BackgroundTasks):
    payload = _json(await _verified_body(request))
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    background.add_task(handle_event, payload)  # ack now; Slack retries after 3 seconds
    return Response(status_code=200)


@router.post("/slack/interactions")
async def slack_interactions(request: Request, background: BackgroundTasks):
    form = parse_qs((await _verified_body(request)).decode("utf-8", "replace"))
    background.add_task(handle_interaction, _json(form.get("payload", [""])[0]))
    return Response(status_code=200)


# --- Socket Mode transport ---

def _on_socket_request(client: SocketModeClient, request: SocketModeRequest) -> None:
    client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
    if request.type == "events_api":
        handle_event(request.payload)
    elif request.type == "interactive":
        handle_interaction(request.payload)


async def startup() -> None:
    """Called on app startup. Starts Socket Mode when SLACK_APP_TOKEN is set."""
    global _socket
    if not settings.slack_app_token:
        return
    if not settings.slack_bot_token:
        logger.error("SLACK_APP_TOKEN is set but SLACK_BOT_TOKEN is not; Slack Socket Mode is off.")
        return
    client = SocketModeClient(app_token=settings.slack_app_token, web_client=_client())
    client.socket_mode_request_listeners.append(_on_socket_request)
    try:
        await asyncio.to_thread(client.connect)
    except Exception:
        logger.exception("Could not connect to Slack Socket Mode")
        await asyncio.to_thread(client.close)
        return
    _socket = client
    logger.info("Connected to Slack over Socket Mode")


async def shutdown() -> None:
    """Called on app shutdown."""
    global _socket
    if _socket is not None:
        client, _socket = _socket, None
        await asyncio.to_thread(client.close)
