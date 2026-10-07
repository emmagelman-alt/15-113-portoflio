from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

SOURCES = ("internal", "slack", "notion")
STATUSES = ("suggested", "open", "done")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Microsoft Entra object id: the stable identity key (emails can change)
    ms_oid: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Filled in later so Slack mentions / Notion assignees map to the right person
    slack_user_id: Mapped[Optional[str]] = mapped_column(String(32), unique=True)
    notion_user_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Todo(Base):
    __tablename__ = "todos"
    __table_args__ = (UniqueConstraint("owner_id", "source", "source_id", name="uq_todo_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="internal")
    # Slack message ts / Notion page id, used to avoid duplicate imports
    source_id: Mapped[Optional[str]] = mapped_column(String(200))
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    owner: Mapped[Employee] = relationship(foreign_keys=[owner_id])
    created_by: Mapped[Optional[Employee]] = relationship(foreign_keys=[created_by_id])
