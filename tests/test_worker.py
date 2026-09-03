from pathlib import Path

import pytest

from app.models import Note
from app.schemas import StructureResult
from app.worker import process_note
from tests.conftest import make_note


async def test_force_merge_ignores_create(db, user_a, tmp_path, monkeypatch):
    target = make_note(db, user_a, title="Van conversion", categories=["vehicle"])
    dest = tmp_path / "add.webm"
    dest.write_bytes(b"audio")
    note = make_note(
        db,
        user_a,
        title="Van conversion",
        status="queued",
        transcript=None,
        summary=None,
        lists={},
        action_items=[],
        ideas=[],
        entities={},
        tags=[],
        categories=[],
        filename="add.webm",
        audio_path=str(dest),
        force_merge_into_id=target.id,
    )

    async def fake_transcribe(*_a, **_k):
        return "Also get a MaxxAir fan."

    async def fake_structure(*_a, **_k):
        return StructureResult(
            action="create",
            title="Random",
            summary="fan",
            lists={"Build": ["MaxxAir fan"]},
            confidence=0.9,
        )

    monkeypatch.setattr("app.worker.transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.worker.structure_dump", fake_structure)
    await process_note(note.id)
    db.expire_all()
    source = db.get(Note, note.id)
    target = db.get(Note, target.id)
    assert source.status == "merged"
    assert source.merged_into_id == target.id
    build = [x.lower() for x in (target.lists or {}).get("Build", [])]
    assert any("maxxair" in x for x in build)


async def _ingest_file(user, db, tmp_path, name="dump.m4a") -> Note:
    dest = tmp_path / name
    dest.write_bytes(b"fake-audio")
    note = make_note(
        db,
        user,
        title="Voice dump",
        status="queued",
        transcript=None,
        summary=None,
        lists={},
        action_items=[],
        ideas=[],
        entities={},
        tags=[],
        categories=[],
        filename=name,
        audio_path=str(dest),
    )
    return note


@pytest.mark.asyncio
async def test_merge_only_if_owned_and_confident(client, db, user_a, user_b, tmp_path, monkeypatch):
    target = make_note(db, user_a, title="Job interview at Northwind")
    foreign = make_note(db, user_b, title="Bob's interview notes")
    note = await _ingest_file(user_a, db, tmp_path)

    async def fake_transcribe(*_args, **_kwargs):
        return "Also ask about the signing bonus at Northwind."

    async def fake_structure(*_args, **_kwargs):
        return StructureResult(
            action="merge",
            target_note_id=foreign.id,
            title="Interview",
            summary="Signing bonus",
            categories=["job"],
            tags=["interview"],
            lists={},
            action_items=[{"text": "Ask about signing bonus", "due": None, "project": None, "checked": False}],
            ideas=[],
            entities={"names": ["Northwind"]},
            confidence=0.95,
        )

    monkeypatch.setattr("app.worker.transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.worker.structure_dump", fake_structure)

    processed = await process_note(note.id)
    db.expire_all()
    processed = db.get(Note, note.id)
    assert processed.status == "ready"
    assert processed.merged_into_id is None
    assert processed.title != ""
    # Foreign id must not merge; a new note is kept for this user.
    assert db.get(Note, foreign.id).user_id == user_b.id
    listed = client.get("/api/v1/notes", headers={"Authorization": f"Bearer {user_a.api_token}"})
    ids = {n["id"] for n in listed.json()}
    assert processed.id in ids
    assert foreign.id not in ids
    _ = target


@pytest.mark.asyncio
async def test_follow_up_merges_any_topic(db, user_a, tmp_path, monkeypatch):
    target = make_note(
        db,
        user_a,
        title="Van conversion",
        categories=["vehicle", "travel"],
        tags=["van"],
        lists={"Build": ["insulation"]},
        transcript="Notes about the van conversion.",
    )
    note = await _ingest_file(user_a, db, tmp_path)

    async def fake_transcribe(*_a, **_k):
        return "For the van, also get MaxxAir fan and a second house battery."

    async def fake_structure(*_a, **_k):
        return StructureResult(
            action="merge",
            target_note_id=target.id,
            title="Van conversion",
            summary="Add MaxxAir fan and a second house battery.",
            categories=["vehicle"],
            tags=["electrical"],
            lists={"Build": ["MaxxAir fan", "second house battery"]},
            action_items=[],
            ideas=[],
            entities={"vendors": ["MaxxAir"]},
            confidence=0.88,
        )

    monkeypatch.setattr("app.worker.transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.worker.structure_dump", fake_structure)

    await process_note(note.id)
    db.expire_all()
    target = db.get(Note, target.id)
    source = db.get(Note, note.id)
    assert source.status == "merged"
    assert source.merged_into_id == target.id
    build = [x.lower() for x in target.lists["Build"]]
    assert "insulation" in build
    assert any("maxxair" in x for x in build)
    assert any("battery" in x for x in build)
    assert target.merge_events
    assert "van" in (target.transcript or "").lower()


@pytest.mark.asyncio
async def test_low_confidence_creates(db, user_a, tmp_path, monkeypatch):
    target = make_note(db, user_a, title="Dentist")
    note = await _ingest_file(user_a, db, tmp_path)

    async def fake_transcribe(*_a, **_k):
        return "I want to learn rust this summer."

    async def fake_structure(*_a, **_k):
        return StructureResult(
            action="merge",
            target_note_id=target.id,
            title="Learn Rust",
            summary="Summer rust plan",
            categories=["tech"],
            tags=["rust"],
            confidence=0.2,
            ideas=["learn rust this summer"],
        )

    monkeypatch.setattr("app.worker.transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.worker.structure_dump", fake_structure)
    await process_note(note.id)
    db.expire_all()
    source = db.get(Note, note.id)
    assert source.status == "ready"
    assert source.merged_into_id is None
    assert "rust" in source.title.lower() or "rust" in " ".join(source.tags).lower()


@pytest.mark.asyncio
async def test_parse_fail_keeps_note_ready(db, user_a, tmp_path, monkeypatch):
    note = await _ingest_file(user_a, db, tmp_path)

    async def fake_transcribe(*_a, **_k):
        return "Remember the garden hose timer."

    async def fake_structure(*_a, **_k):
        return StructureResult(
            action="create",
            parse_warning="Could not parse AI response; kept raw transcript in ideas.",
            raw="not json",
        )

    monkeypatch.setattr("app.worker.transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.worker.structure_dump", fake_structure)
    await process_note(note.id)
    db.expire_all()
    source = db.get(Note, note.id)
    assert source.status == "ready"
    assert source.warning
    assert source.transcript
    assert any("garden hose" in str(x).lower() for x in (source.ideas or [source.transcript]))


@pytest.mark.asyncio
async def test_structuring_fail_keeps_transcript(db, user_a, tmp_path, monkeypatch):
    note = await _ingest_file(user_a, db, tmp_path)

    async def fake_transcribe(*_a, **_k):
        return "Buy mulch for the side yard."

    async def fake_structure(*_a, **_k):
        raise RuntimeError("router down")

    monkeypatch.setattr("app.worker.transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.worker.structure_dump", fake_structure)
    await process_note(note.id)
    db.expire_all()
    source = db.get(Note, note.id)
    assert source.status == "error"
    assert "router down" in (source.error or "")
    assert source.transcript == "Buy mulch for the side yard."
    assert Path(source.audio_path).is_file()


@pytest.mark.asyncio
async def test_retry_requeues(client, db, user_a, tmp_path):
    dest = tmp_path / "x.m4a"
    dest.write_bytes(b"a")
    note = make_note(
        db,
        user_a,
        status="error",
        error="boom",
        transcript="kept",
        audio_path=str(dest),
        filename="x.m4a",
    )
    r = client.post(f"/api/v1/notes/{note.id}/retry", headers={"Authorization": f"Bearer {user_a.api_token}"})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
