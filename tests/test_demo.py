import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import demo, details, main
from app.config import Settings
from app.main import app

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def demo_mode(monkeypatch):
    on = dataclasses.replace(demo.settings, app_env="demo", demo_password=PASSWORD, allowed_email_domains=["andean.test"])
    monkeypatch.setattr(demo, "settings", on)
    monkeypatch.setattr(main, "settings", on)
    monkeypatch.setattr(details, "settings", on)
    demo._failures.clear()
    yield
    demo._failures.clear()


def sign_in(client, email="grader@andean.test", password=PASSWORD, remember=False):
    data = {"email": email, "password": password}
    if remember:
        data["remember"] = "1"
    return client.post("/auth/demo-login", data=data, follow_redirects=False)


def test_demo_settings_must_be_protected(monkeypatch):
    for key, value in {"APP_ENV": "demo", "SESSION_SECRET": "x" * 48, "BASE_URL": "https://demo.onrender.com",
                       "MS_TENANT_ID": "", "DEV_LOGIN": "", "ALLOWED_EMAIL_DOMAINS": "andean.test"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DEMO_PASSWORD", "abc12")
    with pytest.raises(RuntimeError, match="DEMO_PASSWORD"):
        Settings().validate()
    monkeypatch.setenv("DEMO_PASSWORD", "AB3CDE")
    Settings().validate()  # six characters is enough; no Microsoft needed in demo mode
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "")
    with pytest.raises(RuntimeError, match="ALLOWED_EMAIL_DOMAINS"):
        Settings().validate()
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "andean.test")
    monkeypatch.setenv("DEV_LOGIN", "1")
    with pytest.raises(RuntimeError, match="DEV_LOGIN"):
        Settings().validate()
    monkeypatch.setenv("BASE_URL", "http://demo.onrender.com")
    monkeypatch.setenv("DEV_LOGIN", "")
    with pytest.raises(RuntimeError, match="https"):
        Settings().validate()


def test_wrong_password_and_rate_limit(demo_mode):
    client = TestClient(app)
    assert sign_in(client, password="nope").headers["location"] == "/login?error=password"
    assert client.get("/api/me").status_code == 401
    for _ in range(demo.MAX_FAILURES_PER_IP):
        sign_in(client, password="nope")
    # Locked out for a while, even with the right password
    assert sign_in(client).headers["location"] == "/login?error=slow"


def test_only_demo_emails(demo_mode):
    client = TestClient(app)
    assert sign_in(client, email="emma@andean.systems").headers["location"] == "/login?error=demo_domain"
    assert client.get("/api/me").status_code == 401


def test_sign_in_gets_starter_todos_once(demo_mode):
    client = TestClient(app)
    r = sign_in(client, remember=True)
    assert r.status_code == 303 and r.headers["location"] == "/"
    me = client.get("/api/me").json()
    assert me["email"] == "grader@andean.test"
    todos = client.get("/api/todos").json()
    assert len(todos) == 6
    [suggestion] = [t for t in todos if t["status"] == "suggested"]
    assert suggestion["source"] == "slack" and suggestion["title"].startswith("@grader can you")
    todos = [t for t in todos if t["status"] == "open"]
    assert {t["created_by"]["name"] for t in todos} == {"Priya Shah", "Sam Rivera", "Grader"}
    priya_todo = next(t for t in todos if t["created_by"]["name"] == "Priya Shah")
    client.headers["X-CSRF-Token"] = me["csrf_token"]
    assert client.get(f"/api/todos/{priya_todo['id']}/detail").json()["comments"][0]["author"] == "Priya Shah"
    # The sample Slack request opens in the panel with an explanation, and can be accepted
    panel = client.get(f"/api/todos/{suggestion['id']}/detail").json()
    assert "sample Slack request" in panel["slack"]["error"]
    assert client.patch(f"/api/todos/{suggestion['id']}", json={"status": "open"}).json()["status"] == "open"

    again = TestClient(app)
    sign_in(again)
    assert len(again.get("/api/todos").json()) == 6  # not duplicated on the next visit


def test_demo_login_is_off_outside_demo_mode():
    client = TestClient(app)
    r = sign_in(client)
    assert r.headers["location"] == "/login" and client.get("/api/me").status_code == 401


def test_login_page_config(demo_mode):
    cfg = TestClient(app).get("/auth/config").json()
    assert cfg["demo"] is True and cfg["demo_domain"] == "andean.test" and cfg["dev_login"] is False
