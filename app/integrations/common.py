"""Helpers shared by the Slack and Notion integrations."""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Employee, Todo, utcnow


def employee_by_email(db: Session, email: Optional[str]) -> Optional[Employee]:
    """Slack and Notion both expose emails; that's how their users map to employees."""
    if not email:
        return None
    employee = db.scalar(select(Employee).where(func.lower(Employee.email) == email.lower()))
    return employee if employee and employee.is_active else None


def set_status(todo: Todo, status: str) -> None:
    if todo.status == status:
        return
    todo.status = status
    todo.completed_at = utcnow() if status == "done" else None


def upsert_source_todo(
    db: Session,
    *,
    owner: Employee,
    source: str,
    source_id: str,
    title: str,
    source_url: Optional[str] = None,
    due_date: Optional[date] = None,
    created_by: Optional[Employee] = None,
    initial_status: str = "open",
    status: Optional[str] = None,
) -> Tuple[Todo, bool]:
    """Create or refresh the to-do for (owner, source, source_id). Returns (todo, created).

    - `initial_status` applies only when the to-do is new (Slack uses "suggested").
    - `status`, if given, is applied to new and existing to-dos (Notion passes its own status).
    - Dismissed to-dos are never brought back or changed.
    Flushes but does not commit; the caller commits.
    """
    todo = db.scalar(select(Todo).where(
        Todo.owner_id == owner.id, Todo.source == source, Todo.source_id == source_id))
    created = todo is None
    if created:
        todo = Todo(owner_id=owner.id, source=source, source_id=source_id, title="",
                    created_by_id=created_by.id if created_by else None, status=status or initial_status)
        db.add(todo)
    elif todo.status == "dismissed":
        return todo, False
    elif status is not None:
        set_status(todo, status)
    todo.title = title.strip()[:300] or "(untitled)"
    todo.source_url = source_url
    todo.due_date = due_date
    db.flush()
    return todo, created
