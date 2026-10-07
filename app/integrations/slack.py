"""Slack integration (stub; being built)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


async def startup() -> None:
    """Called on app startup. Starts Socket Mode when SLACK_APP_TOKEN is set."""


async def shutdown() -> None:
    """Called on app shutdown."""
