"""Notion integration (stub; being built)."""
from __future__ import annotations

from fastapi import APIRouter

from ..models import Todo

router = APIRouter()


async def startup() -> None:
    """Called on app startup. Starts the periodic Notion sync when configured."""


async def shutdown() -> None:
    """Called on app shutdown."""


def push_status(todo: Todo) -> None:
    """Called after an employee changes a Notion to-do's status on the dashboard."""
