from app.db import SessionLocal
from app.integrations.common import employee_by_email, upsert_source_todo
from tests.conftest import login


def test_upsert_creates_refreshes_and_respects_dismissal():
    client = login("emma@andean.test", "Emma G")
    with SessionLocal() as db:
        emma = employee_by_email(db, "EMMA@andean.test")
        todo, created = upsert_source_todo(db, owner=emma, source="slack", source_id="C1:1.0",
                                           title="Make a design tool", initial_status="suggested")
        db.commit()
        assert created and todo.status == "suggested"

        again, created = upsert_source_todo(db, owner=emma, source="slack", source_id="C1:1.0", title="Edited")
        db.commit()
        assert not created and again.id == todo.id and again.title == "Edited" and again.status == "suggested"

    [item] = client.get("/api/todos").json()
    assert item["status"] == "suggested"

    # Dismissing a synced to-do leaves a tombstone, hidden from the list and never re-imported
    assert client.delete(f"/api/todos/{item['id']}").status_code == 204
    assert client.get("/api/todos").json() == []
    with SessionLocal() as db:
        emma = employee_by_email(db, "emma@andean.test")
        todo, created = upsert_source_todo(db, owner=emma, source="slack", source_id="C1:1.0",
                                           title="Make a design tool", status="open")
        db.commit()
        assert not created and todo.status == "dismissed"


def test_accept_suggested():
    client = login("emma@andean.test")
    with SessionLocal() as db:
        upsert_source_todo(db, owner=employee_by_email(db, "emma@andean.test"), source="slack",
                           source_id="x", title="Review copy", initial_status="suggested")
        db.commit()
    [item] = client.get("/api/todos").json()
    assert client.patch(f"/api/todos/{item['id']}", json={"status": "open"}).json()["status"] == "open"
