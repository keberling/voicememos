from tests.conftest import login, make_note


def test_login_page(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Login with Microsoft" in r.text
    assert "Voice Portal" in r.text


def test_setup_page_shows_url_and_token(client, user_a):
    login(client, user_a)
    r = client.get("/setup")
    assert r.status_code == 200
    assert "Connect your iPhone" in r.text
    assert "Add iPhone Shortcut" in r.text
    assert user_a.api_token in r.text
    assert "/api/v1/ingest" in r.text
    assert "https://www.icloud.com/shortcuts/abc123" in r.text
    assert "shortcuts://import-shortcut" in r.text
    assert "Action Button" in r.text
    assert "401" in r.text
    assert "413" in r.text
    assert "Retry" in r.text


def test_notes_available_before_first_success(client, user_a):
    login(client, user_a)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "Notes" in r.text
    assert "No notes yet" in r.text


def test_queued_note_shows_on_dashboard(client, db, user_a):
    make_note(db, user_a, title="Incoming dump", status="queued", transcript=None, summary=None)
    login(client, user_a)
    r = client.get("/")
    assert r.status_code == 200
    assert "Incoming dump" in r.text
    assert "queued" in r.text
    assert "data-live-notes" in r.text


def test_dashboard_after_ingest(client, db, user_a):
    user_a.last_ingest_ok_at = make_note(db, user_a).updated_at
    db.add(user_a)
    db.commit()
    make_note(db, user_a, title="Cabin trip", categories=["travel"], tags=["cabin"])
    login(client, user_a)
    r = client.get("/")
    assert r.status_code == 200
    assert "Cabin trip" in r.text
    assert "travel" in r.text
