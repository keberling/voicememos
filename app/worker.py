from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.llm import LLMError, structure_dump, transcribe_audio
from app.merge import (
    apply_structure_to_note_fields,
    excerpt,
    merge_into_existing,
    note_search_blob,
    overlap_score,
)
from app.models import MergeEvent, Note, User, utcnow
from app.schemas import StructureResult

log = logging.getLogger("voiceportal.worker")

ACTIVE_STATUSES = ("ready",)
CANDIDATE_STATUSES = ("ready", "error")
STUCK_STATUSES = ("transcribing", "structuring")


def reset_stuck_notes(db: Session, minutes: int = 15) -> int:
    cutoff = utcnow() - timedelta(minutes=minutes)
    notes = (
        db.query(Note)
        .filter(Note.status.in_(STUCK_STATUSES), Note.updated_at < cutoff)
        .all()
    )
    for note in notes:
        note.status = "queued"
        note.error = (note.error or "") + "\nRecovered from stuck processing."
        note.updated_at = utcnow()
    if notes:
        db.commit()
    return len(notes)


def claim_next_note(db: Session) -> Note | None:
    note = (
        db.query(Note)
        .filter(Note.status == "queued")
        .order_by(Note.created_at.asc())
        .first()
    )
    if note is None:
        return None
    note.status = "transcribing" if not note.transcript else "structuring"
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    return note


def _owned_note(db: Session, user_id: str, note_id: str | None) -> Note | None:
    if not note_id:
        return None
    return (
        db.query(Note)
        .filter(Note.id == note_id, Note.user_id == user_id)
        .one_or_none()
    )


def load_candidates(db: Session, note: Note) -> list[Note]:
    transcript = note.transcript or ""
    q = (
        db.query(Note)
        .filter(
            Note.user_id == note.user_id,
            Note.id != note.id,
            Note.status.in_(("ready", "error")),
            or_(Note.merged_into_id.is_(None), Note.merged_into_id == ""),
        )
        .order_by(Note.updated_at.desc())
    )
    recent = q.limit(20).all()
    recent_ids = {n.id for n in recent}

    extras: list[Note] = []
    if transcript.strip():
        pool = (
            db.query(Note)
            .filter(
                Note.user_id == note.user_id,
                Note.id != note.id,
                Note.status.in_(("ready", "error")),
                or_(Note.merged_into_id.is_(None), Note.merged_into_id == ""),
            )
            .order_by(Note.updated_at.desc())
            .limit(200)
            .all()
        )
        scored = []
        for other in pool:
            if other.id in recent_ids:
                continue
            score = overlap_score(transcript, note_search_blob(other))
            if score >= 2:
                scored.append((score, other))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        extras = [n for _, n in scored[:20]]

    # Preserve recency first, then overlap extras.
    return recent + extras


def _candidate_payload(notes: list[Note]) -> list[dict]:
    payload = []
    for n in notes:
        payload.append(
            {
                "id": n.id,
                "title": n.title,
                "categories": n.categories or [],
                "tags": n.tags or [],
                "summary": n.summary or "",
                "lists": n.lists or {},
                "action_items": n.action_items or [],
                "ideas": n.ideas or [],
                "entities": n.entities or {},
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            }
        )
    return payload


def _mark_ingest_ok(db: Session, user_id: str) -> None:
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user:
        user.last_ingest_ok_at = utcnow()


def _append_transcript(existing: str | None, incoming: str | None) -> str:
    incoming = (incoming or "").strip()
    existing = (existing or "").strip()
    if not incoming:
        return existing
    if not existing:
        return incoming
    stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"{existing}\n\n---\nVoice dump {stamp}:\n{incoming}"


async def process_note(note_id: str, db: Session | None = None) -> Note:
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        note = db.query(Note).filter(Note.id == note_id).one_or_none()
        if note is None:
            raise RuntimeError(f"Note {note_id} not found")
        return await _process(db, note)
    finally:
        if close:
            db.close()


async def _process(db: Session, note: Note) -> Note:
    settings = get_settings()

    # 1. Transcribe if needed. Never discard the audio.
    if not (note.transcript or "").strip():
        note.status = "transcribing"
        note.error = None
        note.updated_at = utcnow()
        db.commit()
        if not note.audio_path or not Path(note.audio_path).is_file():
            note.status = "error"
            note.error = "Audio file is missing. The note was kept; re-upload or retry after restoring storage."
            note.updated_at = utcnow()
            db.commit()
            return note
        try:
            note.transcript = await transcribe_audio(note.audio_path, note.filename, settings)
        except Exception as exc:
            log.exception("Transcription failed for %s", note.id)
            note.status = "error"
            note.error = f"Transcription failed: {exc}"
            note.updated_at = utcnow()
            db.commit()
            return note

    # 2. Structure. If this fails, keep transcript and audio.
    note.status = "structuring"
    note.error = None
    note.updated_at = utcnow()
    db.commit()

    candidates = load_candidates(db, note)
    try:
        result = await structure_dump(
            note.transcript or "",
            _candidate_payload(candidates),
            extra_title=None if note.title in {"Voice dump", "Untitled voice dump"} else note.title,
            extra_tags=list(note.tags or []),
            settings=settings,
        )
    except Exception as exc:
        log.exception("Structuring failed for %s", note.id)
        note.status = "error"
        note.error = f"Structuring failed: {exc}"
        note.updated_at = utcnow()
        db.commit()
        return note

    note.raw_ai = result.raw if result.raw is not None else result.model_dump()

    if result.parse_warning:
        _finalize_create(
            db,
            note,
            StructureResult(
                action="create",
                title=note.title or "Voice dump",
                ideas=[note.transcript or ""],
                parse_warning=result.parse_warning,
                raw=result.raw,
            ),
            warning=result.parse_warning,
        )
        return note

    should_merge = (
        result.action == "merge"
        and result.confidence >= 0.6
        and bool(result.target_note_id)
    )
    target = _owned_note(db, note.user_id, result.target_note_id) if should_merge else None
    if should_merge and target is None:
        # Invalid or cross-user id → create. Never mix users.
        should_merge = False

    if should_merge and target is not None:
        _finalize_merge(db, source=note, target=target, result=result)
    else:
        _finalize_create(db, note, result, warning=None)
    return note


def _finalize_create(db: Session, note: Note, result: StructureResult, warning: str | None) -> None:
    fields = apply_structure_to_note_fields(result)
    for key, value in fields.items():
        setattr(note, key, value)
    if warning:
        note.warning = warning
        if not note.ideas:
            note.ideas = [note.transcript or ""]
    note.status = "ready"
    note.error = None
    note.merged_into_id = None
    note.updated_at = utcnow()
    _mark_ingest_ok(db, note.user_id)
    db.commit()


def _finalize_merge(db: Session, source: Note, target: Note, result: StructureResult) -> None:
    existing = {
        "title": target.title,
        "summary": target.summary,
        "categories": target.categories or [],
        "tags": target.tags or [],
        "lists": target.lists or {},
        "action_items": target.action_items or [],
        "ideas": target.ideas or [],
        "entities": target.entities or {},
    }
    merged = merge_into_existing(existing, result)
    for key, value in merged.items():
        setattr(target, key, value)
    target.transcript = _append_transcript(target.transcript, source.transcript)
    target.status = "ready"
    target.error = None
    target.warning = None
    target.updated_at = utcnow()
    target.merge_events.append(
        MergeEvent(
            source=source.source or "voice",
            source_note_id=source.id,
            excerpt=excerpt(source.transcript or source.title or ""),
            created_at=utcnow(),
        )
    )

    source.status = "merged"
    source.merged_into_id = target.id
    source.title = source.title or result.title or "Voice dump"
    source.summary = result.summary or source.summary
    source.transcript = source.transcript
    source.error = None
    source.updated_at = utcnow()

    _mark_ingest_ok(db, source.user_id)
    db.commit()


async def worker_loop() -> None:
    settings = get_settings()
    log.info("Voice Portal worker started")
    while True:
        claimed_id = None
        try:
            db = SessionLocal()
            try:
                reset_stuck_notes(db)
                note = claim_next_note(db)
                claimed_id = note.id if note else None
            finally:
                db.close()
            if claimed_id:
                await process_note(claimed_id)
            else:
                await asyncio.sleep(settings.WORKER_POLL_SECONDS)
        except asyncio.CancelledError:
            log.info("Voice Portal worker stopped")
            raise
        except Exception:
            log.exception("Worker loop error (note=%s)", claimed_id)
            await asyncio.sleep(2.0)
