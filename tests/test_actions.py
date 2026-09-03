from app.models import utcnow
from tests.conftest import login, make_note


def test_toggle_action_item(client, db, user_a):
    note = make_note(
        db,
        user_a,
        title="House",
        categories=["home"],
        action_items=[{"text": "Call the painter", "due": None, "project": None, "checked": False}],
    )
    r = client.post(
        f"/api/v1/notes/{note.id}/actions/0",
        json={"checked": True},
        headers={"Authorization": f"Bearer {user_a.api_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action_items"][0]["checked"] is True
    assert body["completed"] is True


def test_complete_and_reopen_note(client, db, user_a):
    note = make_note(
        db,
        user_a,
        action_items=[
            {"text": "Buy primer", "checked": False},
            {"text": "Sand the door", "checked": False},
        ],
    )
    r = client.post(f"/api/v1/notes/{note.id}/complete", headers={"Authorization": f"Bearer {user_a.api_token}"})
    assert r.status_code == 200
    assert r.json()["completed"] is True
    assert all(i["checked"] for i in r.json()["action_items"])
    r = client.post(f"/api/v1/notes/{note.id}/reopen", headers={"Authorization": f"Bearer {user_a.api_token}"})
    assert r.json()["completed"] is False


def test_dashboard_lists_groups(client, db, user_a):
    make_note(db, user_a, title="Paint shed", categories=["home"], tags=["paint"])
    make_note(db, user_a, title="Offer letter", categories=["job"], tags=["career"])
    login(client, user_a)
    r = client.get("/")
    assert r.status_code == 200
    assert "notes-sidebar" in r.text
    assert "side-group" in r.text
    assert "workspace" in r.text
    assert "Paint shed" in r.text
    assert "Offer letter" in r.text
    assert ">home<" in r.text.lower() or "home" in r.text


def test_deleted_note_tags_disappear(client, db, user_a):
    keep = make_note(db, user_a, title="Keep me", tags=["keep-tag"], categories=["home"])
    gone = make_note(db, user_a, title="Delete me", tags=["orphan-tag"], categories=["home"])
    login(client, user_a)
    listed = client.get("/")
    assert "orphan-tag" in listed.text
    gone_id = gone.id
    r = client.post(f"/notes/{gone_id}/delete")
    assert r.status_code in {200, 303, 302}
    after = client.get("/")
    assert "orphan-tag" not in after.text
    assert "keep-tag" in after.text
    _ = keep


def test_open_view_omits_tags_from_completed_notes(client, db, user_a):
    make_note(db, user_a, title="Live", tags=["live-tag"], categories=["home"])
    make_note(
        db,
        user_a,
        title="Finished",
        tags=["done-only-tag"],
        categories=["home"],
        completed_at=utcnow(),
        action_items=[{"text": "done", "checked": True}],
    )
    login(client, user_a)
    open_page = client.get("/?show=open")
    assert "live-tag" in open_page.text
    assert "done-only-tag" not in open_page.text
    done_page = client.get("/?show=done")
    assert "done-only-tag" in done_page.text
