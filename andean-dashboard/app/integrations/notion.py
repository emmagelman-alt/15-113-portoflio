"""Notion integration: tasks assigned to employees in a Notion tasks database show up on
their dashboards, and checking one off on the dashboard marks it done in Notion.

Uses an internal connection (NOTION_TOKEN) with the Read content, Update content and
"Read user information including email addresses" capabilities. Assignees map to
employees by email.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import current_employee, require_csrf
from ..config import settings
from ..db import SessionLocal
from ..models import Employee, Todo
from .common import employee_by_email, upsert_source_todo

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notion")

API_URL = "https://api.notion.com/v1"
# Latest API version (checked Oct 2026). Since 2025-09-03 a database contains one or more
# "data sources": pages are queried and parented via the data source, so the configured
# database ID is resolved to its data source first. 2026-03-11 renamed `archived` to `in_trash`.
NOTION_VERSION = "2026-03-11"
SCHEMA_TTL = 300  # seconds to cache the data source schema
MAX_RETRIES = 4

# Tests swap in an httpx.MockTransport here
transport: Optional[httpx.BaseTransport] = None
_sleep = time.sleep

_data_sources: Dict[str, str] = {}  # database id -> data source id
_schemas: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # data source id -> (fetched at, properties)
_sync_lock = threading.Lock()
_task: Optional[asyncio.Task] = None
_executor: Optional[ThreadPoolExecutor] = None


class NotionError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"Notion API {status} {code}: {message}")
        self.status, self.code = status, code


def make_client(token: Optional[str] = None) -> httpx.Client:
    return httpx.Client(base_url=API_URL, transport=transport, timeout=30, headers={
        "Authorization": f"Bearer {token or settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
    })


def api(client: httpx.Client, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
    """One API call. Waits out rate limits (429/529) per Retry-After, and retries
    server errors on reads. Raises NotionError on failure."""
    read_only = method == "GET" or path.endswith("/query")
    for attempt in range(MAX_RETRIES + 1):
        resp = client.request(method, path, **kwargs)
        body = _json(resp)
        blocked = (body.get("additional_data") or {}).get("rate_limit_reason") == "public_api_request_blocked"
        retry = (resp.status_code in (429, 529) and not blocked) or (read_only and resp.status_code in (500, 502, 503, 504))
        if not retry or attempt == MAX_RETRIES:
            break
        try:
            wait = float(resp.headers.get("retry-after", ""))
        except ValueError:
            wait = 2.0 ** attempt
        log.info("Notion %s %s returned %s; retrying in %.0fs", method, path, resp.status_code, wait)
        _sleep(min(wait, 60))
    if resp.is_success:
        return body
    raise NotionError(resp.status_code, body.get("code", ""), body.get("message") or resp.text[:200])


def _json(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def notion_id(value: str) -> str:
    """Accepts a bare ID (with or without dashes) or a Notion URL; returns the ID."""
    value = value.strip()
    path = value.split("?")[0].split("#")[0]
    found = re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", path) \
        or re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])", path)
    return found[-1].replace("-", "").lower() if found else value


# --- Schema -----------------------------------------------------------------------

def data_source_id(client: httpx.Client) -> str:
    """The data source holding the tasks. Accepts a database ID (from the URL) or a data source ID."""
    database_id = notion_id(settings.notion_tasks_database_id)
    if database_id not in _data_sources:
        try:
            sources = api(client, "GET", f"/databases/{database_id}").get("data_sources") or []
        except NotionError as exc:
            if exc.status not in (400, 404):
                raise
            try:  # maybe it's already a data source ID
                _schemas[database_id] = (time.monotonic(), api(client, "GET", f"/data_sources/{database_id}")["properties"])
                sources = [{"id": database_id}]
            except NotionError:
                raise NotionError(404, exc.code, "Tasks database not found. Check NOTION_TASKS_DATABASE_ID and "
                                  "share the database with the connection (••• → Connections).") from None
        if not sources:
            raise NotionError(400, "no_data_source", "The tasks database has no data source.")
        if len(sources) > 1:
            log.warning("Notion tasks database has %d data sources; syncing only the first", len(sources))
        _data_sources[database_id] = sources[0]["id"]
    return _data_sources[database_id]


def schema(client: httpx.Client, source_id: str) -> Dict[str, Any]:
    """Property definitions by name, cached briefly."""
    cached = _schemas.get(source_id)
    if cached and time.monotonic() - cached[0] < SCHEMA_TTL:
        return cached[1]
    props = api(client, "GET", f"/data_sources/{source_id}")["properties"]
    _schemas[source_id] = (time.monotonic(), props)
    return props


def _status_options(prop: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """(options, options by lowercased group name) for a status or select property."""
    config = prop.get(prop.get("type", "")) or {}
    options = config.get("options") or []
    by_id = {o.get("id"): o for o in options}
    groups = {(g.get("name") or "").lower(): [by_id[i] for i in g.get("option_ids") or [] if i in by_id]
              for g in config.get("groups") or []}
    return options, groups


def _done_names(props: Dict[str, Any]) -> Set[str]:
    """Lowercased status names that count as done: NOTION_DONE_STATUSES plus, for a
    Notion "status" property, every option in its Complete group."""
    names = set(settings.notion_done_statuses)
    prop = props.get(settings.notion_status_property) or {}
    if prop.get("type") == "status":
        names.update(o["name"].lower() for o in _status_options(prop)[1].get("complete", []))
    return names


def status_value(prop: Optional[Dict[str, Any]], done: bool) -> Optional[Dict[str, Any]]:
    """The page property value that marks a task done or not done, using the schema's own options."""
    kind = (prop or {}).get("type")
    if kind == "checkbox":
        return {"checkbox": done}
    if kind not in ("status", "select"):
        return None
    options, groups = _status_options(prop)
    done_names = settings.notion_done_statuses
    if done:
        match = next((o for o in options if o["name"].lower() in done_names), None)
        if match is None and groups.get("complete"):
            match = groups["complete"][0]
    else:
        complete = {o["name"] for o in groups.get("complete", [])}
        candidates = groups.get("to-do", []) + [o for o in options
                                                if o["name"].lower() not in done_names and o["name"] not in complete]
        match = candidates[0] if candidates else None
    return {kind: {"name": match["name"]}} if match else None


# --- Page properties ----------------------------------------------------------------

def page_title(page: Dict[str, Any]) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(part.get("plain_text", "") for part in prop.get("title") or [])
    return ""


def page_done(page: Dict[str, Any], done_names: Optional[Set[str]] = None) -> bool:
    prop = (page.get("properties") or {}).get(settings.notion_status_property) or {}
    kind = prop.get("type")
    if kind == "checkbox":
        return bool(prop.get("checkbox"))
    if kind in ("status", "select"):
        name = ((prop.get(kind) or {}).get("name") or "").lower()
        return name in (done_names if done_names is not None else settings.notion_done_statuses)
    return False


def page_due(page: Dict[str, Any]) -> Optional[date]:
    prop = (page.get("properties") or {}).get(settings.notion_due_property) or {}
    start = (prop.get("date") or {}).get("start") if prop.get("type") == "date" else None
    try:
        return date.fromisoformat(start[:10]) if start else None
    except ValueError:
        return None


def page_assignees(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    prop = (page.get("properties") or {}).get(settings.notion_assignee_property) or {}
    return [p for p in prop.get("people") or [] if p.get("type") != "bot"] if prop.get("type") == "people" else []


def _email(client: httpx.Client, person: Dict[str, Any], cache: Dict[str, Optional[str]]) -> Optional[str]:
    email = (person.get("person") or {}).get("email")
    if email or not person.get("id"):
        return email
    if person["id"] not in cache:  # page values can be partial users; look the person up
        try:
            cache[person["id"]] = (api(client, "GET", f"/users/{person['id']}").get("person") or {}).get("email")
        except NotionError as exc:
            log.warning("Notion: couldn't look up user %s: %s", person["id"], exc)
            cache[person["id"]] = None
    return cache[person["id"]]


# --- Sync ---------------------------------------------------------------------------

def _query_pages(client: httpx.Client, source_id: str) -> Tuple[List[Dict[str, Any]], bool]:
    """All pages with an assignee (trashed pages are never returned). Returns (pages, complete)."""
    body: Dict[str, Any] = {"page_size": 100, "filter": {
        "property": settings.notion_assignee_property, "people": {"is_not_empty": True}}}
    pages: List[Dict[str, Any]] = []
    complete = True
    while True:
        data = api(client, "POST", f"/data_sources/{source_id}/query", json=body)
        pages += [r for r in data.get("results") or [] if r.get("object") == "page"]
        if (data.get("request_status") or {}).get("type") == "incomplete":
            complete = False
        if not data.get("has_more") or not data.get("next_cursor"):
            return pages, complete
        body["start_cursor"] = data["next_cursor"]


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def sync() -> Dict[str, int]:
    """Pull every assigned task from the Notion database into its assignees' dashboards."""
    with _sync_lock, make_client() as client:
        try:
            return _sync(client)
        except NotionError:
            # Re-read the database next time, in case it was moved or its properties changed
            _data_sources.clear()
            _schemas.clear()
            raise


def _sync(client: httpx.Client) -> Dict[str, int]:
    started = datetime.now(timezone.utc)
    source_id = data_source_id(client)
    props = schema(client, source_id)
    if (props.get(settings.notion_assignee_property) or {}).get("type") != "people":
        raise NotionError(400, "bad_schema", f"The tasks database needs a people property named "
                          f"'{settings.notion_assignee_property}' (set NOTION_ASSIGNEE_PROPERTY).")
    for name, kinds in ((settings.notion_status_property, ("status", "select", "checkbox")),
                        (settings.notion_due_property, ("date",))):
        if (props.get(name) or {}).get("type") not in kinds:
            log.warning("Notion: no %s property named '%s' in the tasks database", "/".join(kinds), name)
    done_names = _done_names(props)
    pages, complete = _query_pages(client, source_id)

    counts = {"pages": len(pages), "todos": 0, "created": 0, "removed": 0, "unmatched": 0}
    emails: Dict[str, Optional[str]] = {}
    missing_email = 0
    seen: Set[Tuple[int, str]] = set()
    with SessionLocal() as db:
        local = {(t.owner_id, t.source_id): t for t in db.scalars(select(Todo).where(Todo.source == "notion"))}
        for page in pages:
            if page.get("in_trash") or page.get("archived"):
                continue
            title, due, done = page_title(page), page_due(page), page_done(page, done_names)
            for person in page_assignees(page):
                email = _email(client, person, emails)
                missing_email += not email
                employee = employee_by_email(db, email)
                if employee is None:
                    counts["unmatched"] += 1
                    continue
                if (employee.id, page["id"]) in seen:
                    continue
                seen.add((employee.id, page["id"]))
                # Don't undo a check-off made on the dashboard while this sync was running
                existing = local.get((employee.id, page["id"]))
                edited = existing is not None and (_utc(existing.updated_at) or started) > started
                _, created = upsert_source_todo(
                    db, owner=employee, source="notion", source_id=page["id"], title=title,
                    source_url=page.get("url"), due_date=due,
                    status=None if edited else ("done" if done else "open"))
                counts["todos"] += 1
                counts["created"] += created
        if complete:  # a truncated query can't tell us what was unassigned
            for key, todo in local.items():
                if key not in seen and todo.status != "dismissed":
                    db.delete(todo)
                    counts["removed"] += 1
        db.commit()
    if missing_email:
        log.warning("Notion returned no email for %d assignee(s); enable the connection's "
                    "'Read user information including email addresses' capability", missing_email)
    log.info("Notion sync: %(pages)d pages, %(todos)d to-dos (%(created)d new), %(removed)d removed, "
             "%(unmatched)d unmatched assignees", counts)
    return counts


async def _loop() -> None:
    while True:
        try:
            await asyncio.to_thread(sync)
        except (NotionError, httpx.HTTPError) as exc:
            log.warning("Notion sync failed: %s", exc)
        except Exception:
            log.exception("Notion sync failed")
        await asyncio.sleep(max(settings.notion_sync_seconds, 10))


@router.post("/sync", dependencies=[Depends(require_csrf)])
async def sync_now(me: Employee = Depends(current_employee)):
    if not settings.notion_configured:
        raise HTTPException(status_code=503, detail="Notion isn't configured.")
    try:
        return await asyncio.to_thread(sync)
    except (NotionError, httpx.HTTPError) as exc:
        log.warning("Notion sync failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Notion sync failed: {exc}")


async def startup() -> None:
    """Called on app startup. Starts the periodic Notion sync when configured."""
    global _task
    if settings.notion_configured and _task is None:
        _task = asyncio.create_task(_loop(), name="notion-sync")
        log.info("Notion sync every %ss", settings.notion_sync_seconds)


async def shutdown() -> None:
    """Called on app shutdown."""
    global _task, _executor
    if _task is not None:
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
        _task = None
    if _executor is not None:
        _executor.shutdown(wait=False)
        _executor = None


# --- Task panel: page content, comments, edits ---------------------------------------

TEXT_BLOCKS = ("paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item",
               "numbered_list_item", "to_do", "quote", "callout", "toggle", "code")
LINK_BLOCKS = ("bookmark", "embed", "link_preview", "video", "pdf", "file")
_UNSET: Any = object()


def spans(rich_text: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Rich text as [{text, href}] for the front end to render safely."""
    return [{"text": rt.get("plain_text", ""), "href": rt.get("href")} for rt in rich_text or []]


def _block(block: Dict[str, Any]) -> Dict[str, Any]:
    kind = block.get("type", "")
    data = block.get(kind) or {}
    if kind in TEXT_BLOCKS:
        return {"type": kind, "spans": spans(data.get("rich_text")), "checked": data.get("checked")}
    if kind in LINK_BLOCKS or kind == "image":
        url = data.get("url") or (data.get(data.get("type", "")) or {}).get("url")
        return {"type": "image" if kind == "image" else "link", "url": url, "spans": spans(data.get("caption"))}
    if kind == "child_page":
        return {"type": "paragraph", "spans": [{"text": "📄 " + data.get("title", ""), "href": None}]}
    if kind == "divider":
        return {"type": "divider"}
    return {"type": "unsupported", "name": kind.replace("_", " ")}


def _user_name(client: httpx.Client, user_id: Optional[str], cache: Dict[str, str]) -> str:
    if not user_id:
        return "Someone"
    if user_id not in cache:
        try:
            cache[user_id] = api(client, "GET", f"/users/{user_id}").get("name") or "Someone"
        except NotionError:
            cache[user_id] = "Someone"
    return cache[user_id]


def _status_choices(prop: Optional[Dict[str, Any]]) -> List[str]:
    kind = (prop or {}).get("type")
    if kind == "checkbox":
        return ["Not done", "Done"]
    return [o["name"] for o in _status_options(prop)[0]] if kind in ("status", "select") else []


def _status_name(page: Dict[str, Any]) -> Optional[str]:
    prop = (page.get("properties") or {}).get(settings.notion_status_property) or {}
    if prop.get("type") == "checkbox":
        return "Done" if prop.get("checkbox") else "Not done"
    return ((prop.get(prop.get("type", "")) or {}).get("name")) if prop.get("type") in ("status", "select") else None


def page_detail(page_ref: str, with_comments: bool = True) -> Dict[str, Any]:
    """A Notion page for the task panel: properties, top-level content, and comments."""
    page_id = notion_id(page_ref)
    with make_client() as client:
        page = api(client, "GET", f"/pages/{page_id}")
        blocks = api(client, "GET", f"/blocks/{page_id}/children", params={"page_size": 100})
        props: Dict[str, Any] = {}
        parent = page.get("parent") or {}
        if parent.get("data_source_id") or parent.get("database_id"):
            with suppress(NotionError):
                props = schema(client, data_source_id(client))
        names: Dict[str, str] = {}
        out: Dict[str, Any] = {
            "title": page_title(page), "url": page.get("url"),
            "status": _status_name(page), "status_options": _status_choices(props.get(settings.notion_status_property)),
            "due_date": page_due(page),
            "assignees": [p.get("name") or _user_name(client, p.get("id"), names) for p in page_assignees(page)],
            "blocks": [_block(b) for b in blocks.get("results") or []],
            "more_blocks": bool(blocks.get("has_more")),
            "comments": None, "comments_error": None,
        }
        if with_comments:
            try:
                data = api(client, "GET", "/comments", params={"block_id": page_id, "page_size": 100})
                out["comments"] = [{
                    "author": (c.get("display_name") or {}).get("resolved_name")
                              or _user_name(client, (c.get("created_by") or {}).get("id"), names),
                    "spans": spans(c.get("rich_text")),
                    "files": [{"name": f"{(a.get('category') or 'file').title()} {i}", "url": (a.get("file") or {}).get("url")}
                              for i, a in enumerate(c.get("attachments") or [], 1) if (a.get("file") or {}).get("url")],
                    "created_at": c.get("created_time"),
                } for c in data.get("results") or []]
            except NotionError as exc:
                out["comments_error"] = ("Turn on the connection's Read comments capability to see comments."
                                         if exc.status == 403 else str(exc))
        return out


def update_page(page_id: str, *, status: Any = _UNSET, due_date: Any = _UNSET) -> Dict[str, Any]:
    """Set a task's status (an option name) and/or due date in Notion. Returns {done, due_date}."""
    with make_client() as client:
        props = schema(client, data_source_id(client))
        changes: Dict[str, Any] = {}
        if status is not _UNSET:
            prop = props.get(settings.notion_status_property) or {}
            if status not in _status_choices(prop):
                raise NotionError(400, "bad_status", f"'{status}' isn't an option for {settings.notion_status_property}.")
            kind = prop["type"]
            changes[settings.notion_status_property] = (
                {"checkbox": status == "Done"} if kind == "checkbox" else {kind: {"name": status}})
        if due_date is not _UNSET:
            changes[settings.notion_due_property] = {"date": {"start": due_date.isoformat()} if due_date else None}
        page = api(client, "PATCH", f"/pages/{notion_id(page_id)}", json={"properties": changes})
        return {"done": page_done(page, _done_names(props)), "due_date": page_due(page)}


MAX_COMMENT_FILES = 3  # Notion's limit per comment


def add_comment(page_id: str, text: str, author_name: str,
                files: Sequence[Tuple[str, str, bytes]] = ()) -> None:
    """Comment on the page, labelled with the employee's name (needs Insert comments).
    `files` are (name, content type, bytes), uploaded to Notion and attached to the comment."""
    with make_client() as client:
        attachments = []
        for name, content_type, data in files[:MAX_COMMENT_FILES]:
            upload = api(client, "POST", "/file_uploads", json={"filename": name, "content_type": content_type})
            api(client, "POST", f"/file_uploads/{upload['id']}/send", files={"file": (name, data, content_type)})
            attachments.append({"type": "file_upload", "file_upload_id": upload["id"]})
        body: Dict[str, Any] = {
            "parent": {"page_id": notion_id(page_id)},
            "rich_text": [{"type": "text", "text": {"content": text or "📎 " + ", ".join(f[0] for f in files)}}],
            "display_name": {"type": "custom", "custom": {"name": f"{author_name} (via Dashboard)"}},
        }
        if attachments:
            body["attachments"] = attachments
        api(client, "POST", "/comments", json=body)


# --- Push ---------------------------------------------------------------------------

def _push(page_id: str, done: bool) -> None:
    try:
        with make_client() as client:
            prop = schema(client, data_source_id(client)).get(settings.notion_status_property)
            value = status_value(prop, done)
            if value is None:
                log.warning("Notion: can't mark page %s %s; no matching option on the '%s' property",
                            page_id, "done" if done else "not done", settings.notion_status_property)
                return
            api(client, "PATCH", f"/pages/{page_id}", json={"properties": {settings.notion_status_property: value}})
    except Exception as exc:
        log.warning("Notion: couldn't update page %s: %s", page_id, exc)


def push_status(todo: Todo) -> Optional[Future]:
    """Called after an employee changes a Notion to-do's status on the dashboard. Updates the
    Notion page in the background (one at a time, in order); never raises."""
    global _executor
    try:
        if not settings.notion_configured or todo.source != "notion" or not todo.source_id \
                or todo.status not in ("open", "done"):
            return None
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notion-push")
        return _executor.submit(_push, todo.source_id, todo.status == "done")
    except Exception:
        log.exception("Notion: couldn't queue status update")
        return None
