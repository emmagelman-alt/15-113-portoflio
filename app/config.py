"""Settings loaded from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> List[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "production"))
    session_secret: str = field(default_factory=lambda: os.getenv("SESSION_SECRET", ""))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./dashboard.db"))
    base_url: str = field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000").rstrip("/"))

    # Microsoft Entra ID (Outlook / Microsoft 365) app registration
    ms_tenant_id: str = field(default_factory=lambda: os.getenv("MS_TENANT_ID", ""))
    ms_client_id: str = field(default_factory=lambda: os.getenv("MS_CLIENT_ID", ""))
    ms_client_secret: str = field(default_factory=lambda: os.getenv("MS_CLIENT_SECRET", ""))

    # Optional extra guard on top of the tenant check, e.g. "andeansystems.com"
    allowed_email_domains: List[str] = field(default_factory=lambda: _split(os.getenv("ALLOWED_EMAIL_DOMAINS", "")))
    # Employees who get admin rights on first sign-in
    admin_emails: List[str] = field(default_factory=lambda: _split(os.getenv("ADMIN_EMAILS", "")))

    # Local-only shortcut that skips Microsoft sign-in. Never available in production.
    dev_login: bool = field(default_factory=lambda: os.getenv("DEV_LOGIN") == "1")

    # Slack app (see slack-manifest.yml). The app token enables Socket Mode for local
    # development, so Slack can reach the laptop without a public URL.
    slack_bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    slack_signing_secret: str = field(default_factory=lambda: os.getenv("SLACK_SIGNING_SECRET", ""))
    slack_app_token: str = field(default_factory=lambda: os.getenv("SLACK_APP_TOKEN", ""))

    # Notion internal integration + the tasks database it syncs from
    notion_token: str = field(default_factory=lambda: os.getenv("NOTION_TOKEN", ""))
    notion_tasks_database_id: str = field(default_factory=lambda: os.getenv("NOTION_TASKS_DATABASE_ID", ""))
    notion_assignee_property: str = field(default_factory=lambda: os.getenv("NOTION_ASSIGNEE_PROPERTY", "Assignee"))
    notion_status_property: str = field(default_factory=lambda: os.getenv("NOTION_STATUS_PROPERTY", "Status"))
    notion_due_property: str = field(default_factory=lambda: os.getenv("NOTION_DUE_PROPERTY", "Due"))
    notion_done_statuses: List[str] = field(default_factory=lambda: _split(os.getenv("NOTION_DONE_STATUSES", "Done")))
    notion_sync_seconds: int = field(default_factory=lambda: int(os.getenv("NOTION_SYNC_SECONDS", "120")))

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_bot_token and self.slack_signing_secret)

    @property
    def notion_configured(self) -> bool:
        return bool(self.notion_token and self.notion_tasks_database_id)

    @property
    def is_production(self) -> bool:
        return self.app_env != "development"

    @property
    def dev_login_enabled(self) -> bool:
        return self.dev_login and not self.is_production

    @property
    def microsoft_configured(self) -> bool:
        return bool(self.ms_tenant_id and self.ms_client_id and self.ms_client_secret)

    def validate(self) -> None:
        if len(self.session_secret) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters.")
        if self.is_production and not self.microsoft_configured:
            raise RuntimeError("Microsoft sign-in (MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET) is required in production.")
        if self.is_production and not self.base_url.startswith("https://"):
            raise RuntimeError("BASE_URL must use https:// in production.")
        if self.dev_login and self.is_production:
            raise RuntimeError("DEV_LOGIN cannot be enabled outside APP_ENV=development.")

    def email_allowed(self, email: str) -> bool:
        if not self.allowed_email_domains:
            return True
        return email.lower().rsplit("@", 1)[-1] in self.allowed_email_domains


settings = Settings()
