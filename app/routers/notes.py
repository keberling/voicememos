from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Note, User, utcnow
from app.notes_query import get_owned_note, search_notes
from app.schemas import NoteOut, NotePatch
from app.serialize import note_to_out

router = APIRouter(tags=["notes"])


@router.get("/api/v1/notes", response_model=list[NoteOut])
def list_notes(
    q: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    category: str | None = Query(default=None),
    include_merged: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notes = search_notes(db, user.id, q=q, tag=tag, category=category, include_merged=include_merged)
    return [note_to_out(n) for n in notes]


@router.get("/api/v1/notes/{note_id}", response_model=NoteOut)
def get_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note_to_out(note)


@router.patch("/api/v1/notes/{note_id}", response_model=NoteOut)
def patch_note(
    note_id: str,
    body: NotePatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(note, key, value)
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    return note_to_out(note)


@router.delete("/api/v1/notes/{note_id}", status_code=204)
def delete_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    audio_path = note.audio_path
    db.delete(note)
    db.commit()
    if audio_path:
        path = Path(audio_path)
        try:
            if path.is_file():
                path.unlink()
            parent = path.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
    return None


@router.post("/api/v1/notes/{note_id}/retry", response_model=NoteOut)
def retry_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.status == "merged":
        raise HTTPException(status_code=400, detail="Merged notes cannot be retried")
    note.status = "queued"
    note.error = None
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    return note_to_out(note)


@router.get("/api/v1/notes/{note_id}/audio")
def note_audio(
    note_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None or not note.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    path = Path(note.audio_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    media = {
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".caf": "audio/x-caf",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=note.filename or path.name)
