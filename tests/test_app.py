import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from tests.conftest import login


def test_dashboard_requires_sign_in():
    client = TestClient(app)
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/api/todos").status_code == 401


def test_dev_login_rejects_outside_domain():
    client = TestClient(app)
    assert client.get("/auth/dev-login", params={"email": "x@gmail.com"}).status_code == 400


def test_mutations_require_csrf():
    client = login("emma@andean.test")
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/todos", json={"title": "x"}).status_code == 403
    assert client.post("/api/todos", json={"title": "x"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/api/todos", json={"title": "x"}, headers={"X-CSRF-Token": token}).status_code == 201


def test_personal_todo_lifecycle():
    client = login("emma@andean.test", "Emma G")
    todo = client.post("/api/todos", json={"title": "  Draft deck  ", "due_date": "2026-10-10"}).json()
    assert todo["title"] == "Draft deck" and todo["source"] == "internal" and todo["status"] == "open"

    done = client.patch(f"/api/todos/{todo['id']}", json={"status": "done"}).json()
    assert done["status"] == "done"
    assert client.get("/api/todos", params={"status": "open"}).json() == []

    assert client.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert client.get("/api/todos").json() == []


def test_send_todo_to_coworker():
    emma = login("emma@andean.test", "Emma G")
    sam = login("sam@andean.test", "Sam R")
    sam_id = sam.get("/api/me").json()["id"]

    emma.post("/api/todos", json={"title": "Design tool mockup", "assignee_id": sam_id})

    received = sam.get("/api/todos").json()
    assert [t["title"] for t in received] == ["Design tool mockup"]
    assert received[0]["created_by"]["name"] == "Emma G"
    assert emma.get("/api/todos").json() == []
    assert [t["owner"]["name"] for t in emma.get("/api/todos/sent").json()] == ["Sam R"]

    # Only the owner can change or delete it
    todo_id = received[0]["id"]
    assert emma.patch(f"/api/todos/{todo_id}", json={"status": "done"}).status_code == 404
    assert emma.delete(f"/api/todos/{todo_id}").status_code == 404


def test_cannot_assign_to_unknown_employee():
    client = login("emma@andean.test")
    assert client.post("/api/todos", json={"title": "x", "assignee_id": 999}).status_code == 400


def test_production_settings_are_strict(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "x" * 48)
    monkeypatch.setenv("BASE_URL", "https://dash.example.com")
    monkeypatch.setenv("MS_TENANT_ID", "")
    with pytest.raises(RuntimeError, match="Microsoft"):
        Settings().validate()
    for key in ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET"):
        monkeypatch.setenv(key, "set")
    monkeypatch.setenv("DEV_LOGIN", "1")
    with pytest.raises(RuntimeError, match="DEV_LOGIN"):
        Settings().validate()
    assert Settings().dev_login_enabled is False
