import base64
import dataclasses
from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from app import sherpa
from app.main import app
from tests.conftest import login

FILES = {"": [{"type": "dir", "name": "typography", "path": "typography"},
              {"type": "dir", "name": "color palletes and info ", "path": "color palletes and info "},
              {"type": "file", "name": ".DS_Store", "path": ".DS_Store"}],
         "color palletes and info ": [{"type": "file", "name": "color-reference.md", "path": "color palletes and info /color-reference.md"}],
         "logos/logomark/GRADIENT/Primary Logo Mark - Gradient-500.png": {
             "type": "file", "path": "logos/logomark/GRADIENT/Primary Logo Mark - Gradient-500.png", "size": 48213,
             "content": base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00").decode()},
         "typography/type-rules.md": {"type": "file", "path": "typography/type-rules.md", "size": 40,
                                      "content": base64.b64encode(b"Headlines: Paralucent Medium, all caps.").decode()}}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(sherpa, "settings", dataclasses.replace(
        sherpa.settings, anthropic_api_key="test-key", github_token="test-token",
        github_repo="andean/brand-library", github_branch="main"))
    requests = []

    def github(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = unquote(request.url.raw_path.decode().split("?")[0].split("/contents/", 1)[1])
        if request.headers["authorization"] != "Bearer test-token" or path not in FILES:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=FILES[path])

    monkeypatch.setattr(sherpa, "transport", httpx.MockTransport(github))
    return requests


def fake_claude(monkeypatch, *responses):
    """Each call to Claude returns the next canned response; records what was sent."""
    sent = []
    queue = list(responses)

    def claude(messages):
        sent.append([dict(m) for m in messages])
        return queue.pop(0)

    monkeypatch.setattr(sherpa, "_claude", claude)
    return sent


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(name, path, id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input={"path": path}, id=id)


def test_requires_sign_in_and_csrf(configured, monkeypatch):
    sent = fake_claude(monkeypatch)
    assert TestClient(app).post("/api/sherpa", json={"ping": True}).status_code in (401, 403)
    client = login("emma@andean.test")
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/sherpa", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 403
    assert sent == []


def test_not_configured():
    client = login("emma@andean.test")
    for body in ({"ping": True}, {"messages": [{"role": "user", "content": "hi"}]}):
        r = client.post("/api/sherpa", json=body)
        assert r.status_code == 503 and r.json()["detail"] == "sherpa.ai isn't connected yet."


def test_ping_checks_github(configured, monkeypatch):
    client = login("emma@andean.test")
    assert client.post("/api/sherpa", json={"ping": True}).json() == {
        "configured": True, "repo": "andean/brand-library", "branch": "main"}
    monkeypatch.setattr(sherpa, "settings", dataclasses.replace(sherpa.settings, github_token="wrong"))
    assert client.post("/api/sherpa", json={"ping": True}).status_code == 503


def test_answers_from_files_it_reads(configured, monkeypatch):
    sent = fake_claude(monkeypatch,
                       SimpleNamespace(stop_reason="tool_use", content=[text("Checking."), tool_use("read_file", "typography/type-rules.md")]),
                       SimpleNamespace(stop_reason="end_turn", content=[text("Headlines are Paralucent Medium in all caps.")]))
    client = login("emma@andean.test")
    r = client.post("/api/sherpa", json={"messages": [
        {"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "What font are headlines?"}]})
    assert r.json() == {"reply": "Headlines are Paralucent Medium in all caps.", "files": ["typography/type-rules.md"]}
    # The whole conversation went to Claude, then the file's text came back as a tool result
    assert [m["role"] for m in sent[0]] == ["user", "assistant", "user"]
    result = sent[1][-1]["content"][0]
    assert result["tool_use_id"] == "t1" and "Paralucent" in result["content"] and result["is_error"] is False


def test_blocked_and_missing_paths_are_errors_not_crashes(configured):
    files = set()
    for path in ("../secrets", "config/.env", ".env.local", None):
        assert sherpa.run_tool("read_file", {"path": path}, files) == "Error: that path is not allowed."
    assert sherpa.run_tool("read_file", {"path": "nope.md"}, files).startswith("Error: GitHub returned 404")
    assert sherpa.run_tool("list_files", {"path": "typography/type-rules.md"}, files) == "Error: that path is a file, not a folder."
    # .DS_Store files are hidden from listings
    assert sherpa.run_tool("list_files", {"path": "/"}, files) == "[folder] typography\n[folder] color palletes and info "
    assert files == set()
    # Nothing that was refused ever reached GitHub
    assert all(".." not in str(r.url) and ".env" not in str(r.url) for r in configured)


def test_refusal_and_runaway_loops(configured, monkeypatch):
    client = login("emma@andean.test")
    ask = {"messages": [{"role": "user", "content": "?"}]}
    fake_claude(monkeypatch, SimpleNamespace(stop_reason="refusal", content=[]))
    assert client.post("/api/sherpa", json=ask).json()["reply"] == "I can't help with that one."
    loop = SimpleNamespace(stop_reason="tool_use", content=[tool_use("list_files", "")])
    fake_claude(monkeypatch, *[loop] * sherpa.MAX_ROUNDS)
    assert client.post("/api/sherpa", json=ask).json()["reply"].startswith("I couldn't finish")


def test_last_message_must_be_from_the_user(configured, monkeypatch):
    fake_claude(monkeypatch)
    client = login("emma@andean.test")
    assert client.post("/api/sherpa", json={"messages": []}).status_code == 400
    assert client.post("/api/sherpa", json={"messages": [{"role": "assistant", "content": "x"}]}).status_code == 400
    assert client.post("/api/sherpa", json={"messages": [{"role": "system", "content": "x"}]}).status_code == 422


def test_folder_names_ending_in_a_space(configured):
    # The asset library has a folder named "color palletes and info " (trailing space)
    assert sherpa.run_tool("list_files", {"path": "color palletes and info "}, set()) == \
        "[file] color palletes and info /color-reference.md"


def test_images_are_attached_not_read(configured):
    files = set()
    result = sherpa.run_tool("read_file", {"path": "logos/logomark/GRADIENT/Primary Logo Mark - Gradient-500.png"}, files)
    assert result.startswith("This is a .png file (48,213 bytes)") and "PNG" not in result
    assert files == {"logos/logomark/GRADIENT/Primary Logo Mark - Gradient-500.png"}
