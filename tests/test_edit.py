from app.edit import parse_action_items, parse_lists
from tests.conftest import login, make_note


def test_parse_lists_and_tasks():
    lists = parse_lists("Grocery:\n- milk\n- eggs\n\nPaint:\nprimer")
    assert lists["Grocery"] == ["milk", "eggs"]
    assert lists["Paint"] == ["primer"]
    items = parse_action_items("[x] Call painter\nBuy primer")
    assert items[0]["checked"] is True
    assert items[1]["text"] == "Buy primer"


def test_edit_requeues_note(client, db, user_a):
    note = make_note(db, user_a, title="Old title", transcript="buy milk", status="ready")
    login(client, user_a)
    r = client.post(
        f"/notes/{note.id}/edit",
        data={
            "title": "Groceries",
            "summary": "Need milk",
            "transcript": "Also get eggs and butter",
            "tags": "grocery, home",
            "categories": "shopping",
            "lists": "Grocery:\n- milk\n- eggs",
            "action_items": "Get butter",
            "ideas": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.refresh(note)
    assert note.status == "queued"
    assert note.source == "edit"
    assert note.title == "Groceries"
    assert "eggs" in (note.transcript or "")
    assert note.categories == ["shopping"]
    assert note.lists["Grocery"] == ["milk", "eggs"]
    assert note.action_items[0]["text"] == "Get butter"
