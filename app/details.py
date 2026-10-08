"""Task panel API: everything behind a to-do (its Slack thread, Notion page, or the
conversation with the coworker who sent it) and the actions you can take from the panel."""
from __future__ import annotations

import logging
import mimetypes
import os
import re
from datetime import date, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from slack_sdk.errors import SlackApiError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_employee, require_csrf, signed_in_id
from .config import settings
from .db import get_db
from .integrations import notion, slack
from .integrations.common import set_status
from .models import Attachment, Employee, Todo, TodoComment
from .todos import _out as todo_out

log = logging.getLogger(__name__)
router = APIRouter()

URL = re.compile(r"https?://[^\s<>\"'`|]+")
GOOGLE = re.compile(r"^/(document|spreadsheets|presentation|forms)/d/([\w-]+)")
DRIVE = re.compile(r"^/file/d/([\w-]+)")


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Shown in the browser; everything else downloads. (SVG and HTML can carry scripts.)
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


class MessageIn(BaseModel):
    text: str = Field(default="", max_length=4000)
    attachment_ids: List[int] = Field(default_factory=list, max_length=10)


class NotionEdit(BaseModel):
    status: Optional[str] = Field(default=None, max_length=100)
    due_date: Optional[date] = None


# --- Access ---------------------------------------------------------------------------

def _visible(db: Session, todo_id: int, me: Employee) -> Todo:
    """The owner sees any of their to-dos; whoever sent a dashboard to-do can see it too."""
    todo = db.get(Todo, todo_id)
    if todo is None or not (todo.owner_id == me.id or (todo.source == "internal" and todo.created_by_id == me.id)):
        raise HTTPException(status_code=404, detail="To-do not found.")
    return todo


def _owned(db: Session, todo_id: int, me: Employee, source: str) -> Todo:
    todo = db.get(Todo, todo_id)
    if todo is None or todo.owner_id != me.id or todo.source != source:
        raise HTTPException(status_code=404, detail="To-do not found.")
    return todo


# --- Linked documents ------------------------------------------------------------------

def link_info(url: str) -> Dict[str, Any]:
    """How the panel can show a link: an embeddable preview, a Notion page it can render, or just a link."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    info: Dict[str, Any] = {"url": url, "kind": "link", "label": host.removeprefix("www."), "embed": None}
    if host.endswith("figma.com") and parsed.path.split("/")[1:2] in (["file"], ["design"], ["proto"], ["board"], ["slides"]):
        info.update(kind="figma", label="Figma file",
                    embed=f"https://www.figma.com/embed?embed_host=andean-dashboard&url={quote(url, safe='')}")
    elif host == "docs.google.com" and GOOGLE.match(parsed.path):
        kind, doc_id = GOOGLE.match(parsed.path).groups()
        label = {"document": "Google Doc", "spreadsheets": "Google Sheet", "presentation": "Google Slides",
                 "forms": "Google Form"}[kind]
        info.update(kind="google", label=label, embed=f"https://docs.google.com/{kind}/d/{doc_id}/preview")
    elif host == "drive.google.com" and DRIVE.match(parsed.path):
        info.update(kind="google", label="Google Drive file",
                    embed=f"https://drive.google.com/file/d/{DRIVE.match(parsed.path).group(1)}/preview")
    elif host in ("notion.so", "www.notion.so", "app.notion.com") or host.endswith(".notion.site"):
        info.update(kind="notion", label="Notion page")
    return info


def find_links(texts: Iterable[Optional[str]], exclude: Iterable[Optional[str]] = ()) -> List[Dict[str, Any]]:
    skip = {u for u in exclude if u}
    seen: Dict[str, Dict[str, Any]] = {}
    for text in texts:
        for url in URL.findall(text or ""):
            url = url.rstrip(".,;:!?)]}")
            if url not in skip and url not in seen:
                seen[url] = link_info(url)
    return list(seen.values())


# --- Panel ------------------------------------------------------------------------------

def _file(a: Attachment) -> Dict[str, Any]:
    return {"id": a.id, "name": a.filename, "size": a.size, "content_type": a.content_type,
            "is_image": a.content_type.startswith("image/") and a.content_type in INLINE_TYPES,
            "url": f"/files/{a.id}/{quote(a.filename)}"}


def _comment(c: TodoComment, me: Employee, files: List[Attachment]) -> Dict[str, Any]:
    return {"id": c.id, "author": c.author.name if c.author else "Former employee",
            "is_me": c.author_id == me.id, "body": c.body, "files": [_file(a) for a in files],
            # SQLite drops the timezone; timestamps are stored in UTC
            "created_at": c.created_at.replace(tzinfo=c.created_at.tzinfo or timezone.utc)}


@router.get("/api/todos/{todo_id}/detail")
def detail(todo_id: int, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _visible(db, todo_id, me)
    owner = todo.owner_id == me.id
    out: Dict[str, Any] = {"todo": todo_out(todo), "is_owner": owner, "slack": None, "notion": None, "comments": None}
    texts: List[Optional[str]] = [todo.title, todo.notes]

    if todo.source == "internal":
        comments = db.scalars(select(TodoComment).where(TodoComment.todo_id == todo.id).order_by(TodoComment.created_at)).all()
        files: Dict[int, List[Attachment]] = {}
        for a in db.scalars(select(Attachment).where(Attachment.todo_id == todo.id, Attachment.comment_id.is_not(None))):
            files.setdefault(a.comment_id, []).append(a)
        out["comments"] = [_comment(c, me, files.get(c.id, [])) for c in comments]
        texts += [c["body"] for c in out["comments"]]

    elif todo.source == "slack":
        if not settings.slack_configured:
            out["slack"] = {"error": "This is a sample Slack request. Slack isn't connected in the demo." if settings.is_demo
                            else "Slack isn't connected."}
        else:
            try:
                out["slack"] = slack.thread(todo)
                texts += [m["text"] for m in out["slack"]["messages"]]
            except (SlackApiError, OSError, ValueError, KeyError) as exc:
                log.warning("Slack thread for to-do %s failed: %s", todo.id, exc)
                out["slack"] = {"error": "Couldn't load the Slack thread. Use Open in Slack instead."}
            replier = slack.reply_identity(db) if owner else None
            out["slack"]["can_reply"] = owner
            out["slack"]["reply_as"] = "you" if replier and replier.id == me.id else "bot"

    elif todo.source == "notion":
        if not settings.notion_configured:
            out["notion"] = {"error": "Notion isn't connected."}
        else:
            try:
                out["notion"] = page = notion.page_detail(todo.source_id or "")
                texts += [s.get("href") for b in page["blocks"] for s in b.get("spans") or []]
                texts += [b.get("url") for b in page["blocks"]]
                texts += [s["text"] for b in page["blocks"] for s in b.get("spans") or []]
                texts += [s.get("href") or s["text"] for c in page["comments"] or [] for s in c["spans"]]
            except (notion.NotionError, httpx.HTTPError) as exc:
                log.warning("Notion page for to-do %s failed: %s", todo.id, exc)
                out["notion"] = {"error": "Couldn't load the Notion page. Use Open in Notion instead."}

    own_files = f"{settings.base_url}/files/"
    out["links"] = [link for link in find_links(texts, exclude=[todo.source_url]) if not link["url"].startswith(own_files)]
    return out


# --- Attachments ------------------------------------------------------------------------

def _clean_name(name: Optional[str]) -> str:
    name = os.path.basename((name or "").replace("\\", "/"))
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>')
    return name.strip(" .")[:200] or "file"


@router.post("/api/todos/{todo_id}/attachments", status_code=201, dependencies=[Depends(require_csrf)])
async def upload(todo_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                 me: Employee = Depends(current_employee)):
    todo = _visible(db, todo_id, me)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Files can be up to 10 MB.")
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    name = _clean_name(file.filename)
    content_type = (file.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream")[:100]
    attachment = Attachment(todo_id=todo.id, uploader_id=me.id, filename=name, content_type=content_type,
                            size=len(data), data=data)
    db.add(attachment)
    db.commit()
    return _file(attachment)


def _take(db: Session, todo: Todo, me: Employee, ids: List[int], limit: int = 10) -> List[Attachment]:
    """The caller's unsent uploads for this to-do, in the order given."""
    if len(ids) > limit:
        raise HTTPException(status_code=400, detail=f"Attach up to {limit} files.")
    found = {a.id: a for a in db.scalars(select(Attachment).where(
        Attachment.id.in_(ids), Attachment.todo_id == todo.id, Attachment.uploader_id == me.id,
        Attachment.sent.is_(False)))} if ids else {}
    if len(found) != len(set(ids)):
        raise HTTPException(status_code=400, detail="One of the attachments is no longer available. Attach it again.")
    return [found[i] for i in dict.fromkeys(ids)]


def _require_content(body: MessageIn) -> str:
    text = body.text.strip()
    if not text and not body.attachment_ids:
        raise HTTPException(status_code=400, detail="Write a message or attach a file.")
    return text


@router.get("/files/{attachment_id}/{filename}")
def download(attachment_id: int, request: Request, db: Session = Depends(get_db)):
    employee_id = signed_in_id(request)
    me = db.get(Employee, employee_id) if employee_id else None
    if me is None or not me.is_active:
        return RedirectResponse("/login", status_code=302)
    a = db.get(Attachment, attachment_id)
    todo = db.get(Todo, a.todo_id) if a else None
    allowed = a is not None and todo is not None and (
        a.shared or me.id in (a.uploader_id, todo.owner_id) or (todo.source == "internal" and todo.created_by_id == me.id))
    if not allowed:
        raise HTTPException(status_code=404, detail="File not found.")
    inline = a.content_type in INLINE_TYPES
    headers = {
        "Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(a.filename)}",
        "Cache-Control": "private, max-age=3600",
    }
    if a.content_type.startswith("image/"):
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
    return Response(content=a.data, media_type=a.content_type if inline else "application/octet-stream", headers=headers)


@router.post("/api/todos/{todo_id}/comments", status_code=201, dependencies=[Depends(require_csrf)])
def add_comment(todo_id: int, body: MessageIn, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _visible(db, todo_id, me)
    if todo.source != "internal":
        raise HTTPException(status_code=400, detail="Comments are for to-dos sent on the dashboard.")
    text = _require_content(body)
    files = _take(db, todo, me, body.attachment_ids)
    comment = TodoComment(todo_id=todo.id, author_id=me.id, body=text)
    db.add(comment)
    db.flush()
    for a in files:
        a.comment_id, a.sent = comment.id, True
    db.commit()
    return _comment(comment, me, files)


@router.post("/api/todos/{todo_id}/slack-reply", dependencies=[Depends(require_csrf)])
def slack_reply(todo_id: int, body: MessageIn, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _owned(db, todo_id, me, "slack")
    text = _require_content(body)
    files = _take(db, todo, me, body.attachment_ids)
    replier = slack.reply_identity(db)
    try:
        slack.post_reply(todo, text, author_name=me.name, as_user=bool(replier and replier.id == me.id),
                         files=[slack.ReplyFile(a.filename, a.content_type, a.data,
                                                f"{settings.base_url}/files/{a.id}/{quote(a.filename)}") for a in files])
    except SlackApiError as exc:
        error = exc.response.get("error", "unknown_error")
        hint = {"not_in_channel": "You aren't in that channel.",
                "missing_scope": "The Slack app is missing a permission; reinstall it from the manifest."}.get(error, error)
        raise HTTPException(status_code=502, detail=f"Slack didn't accept the reply: {hint}")
    for a in files:
        a.sent = a.shared = True  # people following the Slack link need to open it
    db.commit()
    return {"ok": True}


@router.patch("/api/todos/{todo_id}/notion", dependencies=[Depends(require_csrf)])
def notion_edit(todo_id: int, body: NotionEdit, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _owned(db, todo_id, me, "notion")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    try:
        result = notion.update_page(todo.source_id or "", **changes)
    except notion.NotionError as exc:
        raise HTTPException(status_code=400 if exc.status == 400 else 502, detail=str(exc))
    set_status(todo, "done" if result["done"] else "open")
    todo.due_date = result["due_date"]
    db.commit()
    return todo_out(todo)


@router.post("/api/todos/{todo_id}/notion-comments", status_code=201, dependencies=[Depends(require_csrf)])
def notion_comment(todo_id: int, body: MessageIn, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _owned(db, todo_id, me, "notion")
    text = _require_content(body)
    files = _take(db, todo, me, body.attachment_ids, limit=notion.MAX_COMMENT_FILES)
    try:
        notion.add_comment(todo.source_id or "", text, me.name, [(a.filename, a.content_type, a.data) for a in files])
    except notion.NotionError as exc:
        detail = ("Turn on the connection's Insert comments capability in Notion." if exc.status == 403 else str(exc))
        raise HTTPException(status_code=502, detail=detail)
    for a in files:
        a.sent = True
    db.commit()
    return {"ok": True}


@router.get("/api/notion-preview")
def notion_preview(url: str, me: Employee = Depends(current_employee)):
    """Render a linked Notion page in the panel, if it's shared with the dashboard's connection."""
    if not settings.notion_token:
        raise HTTPException(status_code=503, detail="Notion isn't connected.")
    try:
        return notion.page_detail(url, with_comments=False)
    except notion.NotionError as exc:
        if exc.status in (400, 404):
            raise HTTPException(status_code=404, detail="That page isn't shared with the dashboard. Open it in Notion.")
        raise HTTPException(status_code=502, detail=str(exc))
