"""To-do API. Phase 1 covers personal to-dos and sending to-dos to coworkers;
Slack and Notion imports will write into the same table with their own `source`."""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .auth import current_employee, require_csrf
from .db import get_db
from .integrations import notion
from .integrations.common import set_status
from .models import Employee, Todo

router = APIRouter(prefix="/api")


class EmployeeOut(BaseModel):
    id: int
    name: str
    email: str


class TodoOut(BaseModel):
    id: int
    title: str
    notes: str
    source: str
    source_url: Optional[str]
    status: str
    due_date: Optional[date]
    created_by: Optional[EmployeeOut]
    owner: EmployeeOut


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=5000)
    due_date: Optional[date] = None
    assignee_id: Optional[int] = None


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    notes: Optional[str] = Field(default=None, max_length=5000)
    due_date: Optional[date] = None
    status: Optional[Literal["open", "done"]] = None


def _person(e: Optional[Employee]) -> Optional[EmployeeOut]:
    return EmployeeOut(id=e.id, name=e.name, email=e.email) if e else None


def _out(t: Todo) -> TodoOut:
    return TodoOut(
        id=t.id, title=t.title, notes=t.notes, source=t.source, source_url=t.source_url,
        status=t.status, due_date=t.due_date, created_by=_person(t.created_by), owner=_person(t.owner),
    )


def _owned(db: Session, todo_id: int, me: Employee) -> Todo:
    todo = db.get(Todo, todo_id)
    if todo is None or todo.owner_id != me.id:
        raise HTTPException(status_code=404, detail="To-do not found.")
    return todo


@router.get("/me")
def me(request: Request, me: Employee = Depends(current_employee)):
    return {"id": me.id, "name": me.name, "email": me.email, "is_admin": me.is_admin,
            "csrf_token": request.session.get("csrf")}


@router.get("/employees", response_model=List[EmployeeOut])
def employees(db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    rows = db.scalars(select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.name))
    return [_person(e) for e in rows]


@router.get("/todos", response_model=List[TodoOut])
def list_todos(status: Optional[str] = None, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    query = select(Todo).where(Todo.owner_id == me.id)
    if status:
        query = query.where(Todo.status == status)
    else:
        query = query.where(Todo.status != "dismissed")
    # Undated items last, then soonest due, then newest
    query = query.order_by(case((Todo.due_date.is_(None), 1), else_=0), Todo.due_date, Todo.created_at.desc())
    return [_out(t) for t in db.scalars(query)]


@router.get("/todos/sent", response_model=List[TodoOut])
def sent_todos(db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    query = (select(Todo).where(Todo.created_by_id == me.id, Todo.owner_id != me.id)
             .order_by(Todo.created_at.desc()).limit(100))
    return [_out(t) for t in db.scalars(query)]


@router.post("/todos", response_model=TodoOut, status_code=201, dependencies=[Depends(require_csrf)])
def create_todo(body: TodoCreate, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    owner = me
    if body.assignee_id and body.assignee_id != me.id:
        owner = db.get(Employee, body.assignee_id)
        if owner is None or not owner.is_active:
            raise HTTPException(status_code=400, detail="That coworker was not found.")
    todo = Todo(owner_id=owner.id, created_by_id=me.id, title=body.title.strip(),
                notes=body.notes.strip(), due_date=body.due_date, source="internal")
    db.add(todo)
    db.commit()
    return _out(todo)


@router.patch("/todos/{todo_id}", response_model=TodoOut, dependencies=[Depends(require_csrf)])
def update_todo(todo_id: int, body: TodoUpdate, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _owned(db, todo_id, me)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes:
        todo.title = changes["title"].strip()
    if "notes" in changes:
        todo.notes = changes["notes"].strip()
    if "due_date" in changes:
        todo.due_date = changes["due_date"]
    status_changed = "status" in changes and changes["status"] != todo.status
    if "status" in changes:
        set_status(todo, changes["status"])
    db.commit()
    if status_changed and todo.source == "notion":
        notion.push_status(todo)
    return _out(todo)


@router.delete("/todos/{todo_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_todo(todo_id: int, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    todo = _owned(db, todo_id, me)
    if todo.source == "internal":
        db.delete(todo)
    else:
        # Keep a tombstone so the next Slack/Notion sync doesn't re-import it
        todo.status = "dismissed"
    db.commit()
    return Response(status_code=204)
