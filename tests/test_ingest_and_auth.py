from tests.conftest import make_note


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ingest_requires_token(client, user_a):
    r = client.post(
        "/api/v1/ingest",
        files={"file": ("memo.m4a", b"RIFF....fake", "audio/mp4")},
        data={"source": "ios-shortcut"},
    )
    assert r.status_code == 401


def test_ingest_rejects_bad_token(client, user_a):
    r = client.post(
        "/api/v1/ingest",
        files={"file": ("memo.m4a", b"RIFF....fake", "audio/mp4")},
        data={"token": "vnp_wrong", "source": "ios-shortcut"},
    )
    assert r.status_code == 401


def test_ingest_accepts_form_token(client, user_a):
    r = client.post(
        "/api/v1/ingest",
        files={"file": ("memo.m4a", b"RIFF....fake-audio", "audio/mp4")},
        data={"token": user_a.api_token, "source": "ios-shortcut", "title": "Quick thought"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["title"] == "Quick thought"
    assert body["id"]


def test_ingest_accepts_bearer(client, user_a):
    r = client.post(
        "/api/v1/ingest",
        files={"file": ("memo.m4a", b"audio-bytes", "audio/mp4")},
        data={"source": "ios-shortcut"},
        headers={"Authorization": f"Bearer {user_a.api_token}"},
    )
    assert r.status_code == 202


def test_ingest_accepts_raw_audio_body(client, user_a):
    """Shortcuts Request Body: File sends the recording as the raw POST body."""
    r = client.post(
        "/api/v1/ingest",
        content=b"raw-m4a-bytes",
        headers={
            "Authorization": f"Bearer {user_a.api_token}",
            "Content-Type": "audio/mp4",
        },
    )
    assert r.status_code == 202
    assert r.json()["status"] == "queued"


def test_ingest_accepts_query_token_with_raw_body(client, user_a):
    r = client.post(
        f"/api/v1/ingest?token={user_a.api_token}&source=ios-shortcut",
        content=b"raw-m4a-bytes",
        headers={"Content-Type": "audio/x-m4a"},
    )
    assert r.status_code == 202


def test_ingest_413(client, user_a):
    huge = b"x" * (3 * 1024 * 1024)
    r = client.post(
        "/api/v1/ingest",
        files={"file": ("memo.m4a", huge, "audio/mp4")},
        data={"token": user_a.api_token},
    )
    assert r.status_code == 413


def test_rotate_kills_old_token(client, user_a):
    old = user_a.api_token
    r = client.post("/api/v1/me/token/rotate", headers={"Authorization": f"Bearer {old}"})
    assert r.status_code == 200
    new = r.json()["api_token"]
    assert new != old
    assert new.startswith("vnp_")
    dead = client.get("/api/v1/me", headers={"Authorization": f"Bearer {old}"})
    assert dead.status_code == 401
    ok = client.get("/api/v1/me", headers={"Authorization": f"Bearer {new}"})
    assert ok.status_code == 200
    assert ok.json()["api_token"] == new
    assert ok.json()["ingest_url"].endswith("/api/v1/ingest")


def test_users_never_see_each_other(client, db, user_a, user_b):
    note_a = make_note(db, user_a, title="Ada private")
    note_b = make_note(db, user_b, title="Bob private")
    listed = client.get("/api/v1/notes", headers={"Authorization": f"Bearer {user_a.api_token}"})
    assert listed.status_code == 200
    titles = {n["title"] for n in listed.json()}
    assert "Ada private" in titles
    assert "Bob private" not in titles
    stolen = client.get(f"/api/v1/notes/{note_b.id}", headers={"Authorization": f"Bearer {user_a.api_token}"})
    assert stolen.status_code == 404
    audio = client.get(f"/api/v1/notes/{note_b.id}/audio", headers={"Authorization": f"Bearer {user_a.api_token}"})
    assert audio.status_code == 404
    _ = note_a
