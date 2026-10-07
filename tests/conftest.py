import os
import tempfile

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.update({
    "APP_ENV": "development",
    "SESSION_SECRET": "x" * 48,
    "DATABASE_URL": f"sqlite:///{_db.name}",
    "DEV_LOGIN": "1",
    "MS_TENANT_ID": "",
    "MS_CLIENT_ID": "",
    "MS_CLIENT_SECRET": "",
    "ALLOWED_EMAIL_DOMAINS": "andean.test",
    "SLACK_BOT_TOKEN": "",
    "SLACK_SIGNING_SECRET": "",
    "SLACK_APP_TOKEN": "",
    "NOTION_TOKEN": "",
    "NOTION_TASKS_DATABASE_ID": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def login(email: str, name: str = "") -> TestClient:
    client = TestClient(app)
    client.get("/auth/dev-login", params={"email": email, "name": name})
    client.headers["X-CSRF-Token"] = client.get("/api/me").json()["csrf_token"]
    return client
