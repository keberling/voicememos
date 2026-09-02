from __future__ import annotations

import json
import os
import tempfile
from base64 import b64encode
from pathlib import Path

import itsdangerous

TEST_ROOT = Path(tempfile.mkdtemp(prefix="voiceportal-"))
os.environ.update(
    {
        "APP_NAME": "Voice Portal",
        "APP_BASE_URL": "http://testserver",
        "SECRET_KEY": "test-secret-key-voiceportal",
        "DATABASE_URL": "sqlite:///" + (TEST_ROOT / "test.db").as_posix(),
        "UPLOAD_DIR": str(TEST_ROOT / "uploads"),
        "MAX_UPLOAD_MB": "2",
        "DISABLE_WORKER": "true",
        "LLM_BASE_URL": "http://llm.test/v1",
        "LLM_API_KEY": "test-llm-key",
        "LLM_MODEL": "test-model",
        "STT_MODEL": "whisper-1",
        "AZURE_AD_CLIENT_ID": "",
        "AZURE_AD_CLIENT_SECRET": "",
        "AZURE_AD_TENANT_ID": "common",
        "SHORTCUT_ICLOUD_URL": "https://www.icloud.com/shortcuts/abc123",
        "SHORTCUT_FILE_URL": "https://example.com/VoiceDump.shortcut",
        "SIGN_SHORTCUTS": "false",
        "ALLOWED_EMAILS": "",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import MergeEvent, Note, User, new_api_token, new_id, utcnow  # noqa: E402

get_settings.cache_clear()
init_db()
Path(os.environ["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)


def make_user(db: Session, email: str, name: str | None = None, token: str | None = None) -> User:
    user = User(
        id=new_id(),
        oid=f"oid-{email}",
        email=email.lower(),
        name=name or email.split("@")[0],
        api_token=token or new_api_token(),
        created_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_note(db: Session, user: User, **kwargs) -> Note:
    now = utcnow()
    note = Note(
        id=kwargs.pop("id", new_id()),
        user_id=user.id,
        title=kwargs.pop("title", "Existing note"),
        tags=kwargs.pop("tags", ["home"]),
        categories=kwargs.pop("categories", ["home"]),
        status=kwargs.pop("status", "ready"),
        filename=kwargs.pop("filename", None),
        audio_path=kwargs.pop("audio_path", None),
        transcript=kwargs.pop("transcript", "Old transcript about the house project."),
        summary=kwargs.pop("summary", "House project"),
        lists=kwargs.pop("lists", {"Paint": ["primer"]}),
        action_items=kwargs.pop("action_items", [{"text": "Call the painter", "due": None, "project": None, "checked": False}]),
        ideas=kwargs.pop("ideas", ["Maybe a skylight"]),
        entities=kwargs.pop("entities", {"names": ["Sam"], "places": [], "vendors": [], "tickets": []}),
        source=kwargs.pop("source", "ios-shortcut"),
        created_at=kwargs.pop("created_at", now),
        updated_at=kwargs.pop("updated_at", now),
        **kwargs,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def quiet_review(monkeypatch):
    async def fake_review(note, settings=None):
        return {
            "appropriate": False,
            "reason": "test",
            "review": "",
            "next_steps": [],
            "questions": [],
        }

    monkeypatch.setattr("app.worker.review_note", fake_review)


@pytest.fixture(autouse=True)
def clean_db():
    session = SessionLocal()
    try:
        session.query(MergeEvent).delete()
        session.query(Note).delete()
        session.query(User).delete()
        session.commit()
        yield
        session.query(MergeEvent).delete()
        session.query(Note).delete()
        session.query(User).delete()
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def session_cookie(user_id: str) -> str:
    signer = itsdangerous.TimestampSigner(os.environ["SECRET_KEY"])
    payload = b64encode(json.dumps({"user_id": user_id}).encode("utf-8"))
    return signer.sign(payload).decode("utf-8")


def login(client: TestClient, user: User) -> None:
    client.cookies.set("vp_session", session_cookie(user.id))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def user_a(db):
    return make_user(db, "ada@example.com", "Ada", token="vnp_user_a_token_aaaaaaaa")


@pytest.fixture
def user_b(db):
    return make_user(db, "bob@example.com", "Bob", token="vnp_user_b_token_bbbbbbbb")
