"""Password-protected demo (APP_ENV=demo), e.g. for the class portfolio.

Visitors sign in on the normal login page with any allowed demo email (ALLOWED_EMAIL_DOMAINS,
e.g. @andean.test) plus the shared DEMO_PASSWORD. New visitors get a few starter to-dos from
sample coworkers so the dashboard isn't empty. Real company accounts never exist here.
"""
from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Deque, Dict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .auth import EMAIL, _login_error, _start_session, _upsert_employee
from .config import settings
from .db import get_db
from .models import Employee, Todo, TodoComment

router = APIRouter()

WINDOW_SECONDS = 300
MAX_FAILURES_PER_IP = 8
MAX_FAILURES_TOTAL = 60
_failures: Dict[str, Deque[float]] = defaultdict(deque)


def _too_many(ip: str) -> bool:
    now = time.monotonic()
    for q in (_failures[ip], _failures["*"]):
        while q and q[0] < now - WINDOW_SECONDS:
            q.popleft()
    return len(_failures[ip]) >= MAX_FAILURES_PER_IP or len(_failures["*"]) >= MAX_FAILURES_TOTAL


def _coworker(db: Session, local: str, name: str) -> Employee:
    email = f"{local}@{settings.allowed_email_domains[0]}"
    return db.scalar(select(Employee).where(Employee.email == email)) or _upsert_employee(db, oid=None, email=email, name=name)


def starter_todos(db: Session, me: Employee) -> None:
    """A few sample to-dos for a brand-new demo visitor."""
    has_any = db.scalar(select(func.count()).select_from(Todo).where(or_(Todo.owner_id == me.id, Todo.created_by_id == me.id)))
    if has_any:
        return
    priya, sam = _coworker(db, "priya", "Priya Shah"), _coworker(db, "sam", "Sam Rivera")
    today = date.today()
    rows = [
        (priya, 'Pick a color for the new "Suggested" badge', 1),
        (sam, "Review the homepage hero illustration before Friday's sync", 2),
        (sam, "Add alt text to the Q4 launch graphics", 5),
        (me, "Draft the onboarding deck", -1),
        (me, "Brand guidelines one-pager for new hires", None),
    ]
    for creator, title, days in rows:
        todo = Todo(owner_id=me.id, created_by_id=creator.id, title=title, source="internal",
                    due_date=today + timedelta(days=days) if days is not None else None)
        db.add(todo)
        if creator is priya:
            db.flush()
            db.add(TodoComment(todo_id=todo.id, author_id=priya.id,
                               body="Its own accent, I think. Light Bronze? Let me know what you pick."))
    db.commit()


@router.post("/auth/demo-login")
def demo_login(request: Request, email: str = Form(""), password: str = Form(""), remember: bool = Form(False),
               db: Session = Depends(get_db)):
    if not settings.is_demo:
        return RedirectResponse("/login", status_code=303)
    ip = request.client.host if request.client else "unknown"
    if _too_many(ip):
        return RedirectResponse("/login?error=slow", status_code=303)
    ok = secrets.compare_digest(password.encode(), settings.demo_password.encode())
    if not ok:
        _failures[ip].append(time.monotonic())
        _failures["*"].append(time.monotonic())
        return RedirectResponse("/login?error=password", status_code=303)
    email = email.strip().lower()[:320]
    if not EMAIL.match(email) or not settings.email_allowed(email):
        return RedirectResponse("/login?error=demo_domain", status_code=303)
    me = _upsert_employee(db, oid=None, email=email, name=email.split("@")[0].replace(".", " ").title())
    if not me.is_active:
        return _login_error("inactive")
    starter_todos(db, me)
    _start_session(request, me, remember)
    return RedirectResponse("/", status_code=303)
