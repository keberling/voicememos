from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.merge import coerce_action_item
from app.models import Note, User, utcnow
from app.notes_query import get_owned_note, search_notes
from app.schemas import ActionCheckIn, NoteOut, NotePatch
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
    completed = data.pop("completed", None)
    for key, value in data.items():
        setattr(note, key, value)
    if completed is True:
        _mark_complete(note)
    elif completed is False:
        note.completed_at = None
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    return note_to_out(note)


def _mark_complete(note: Note) -> None:
    items = [coerce_action_item(x) for x in (note.action_items or [])]
    for item in items:
        item["checked"] = True
    note.action_items = items
    note.completed_at = utcnow()


@router.post("/api/v1/notes/{note_id}/actions/{index}", response_model=NoteOut)
def toggle_action(
    note_id: str,
    index: int,
    body: ActionCheckIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    items = [coerce_action_item(x) for x in (note.action_items or [])]
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="Action item not found")
    items[index]["checked"] = bool(body.checked)
    note.action_items = items
    if items and all(i.get("checked") for i in items):
        note.completed_at = utcnow()
    else:
        note.completed_at = None
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    return note_to_out(note)


@router.post("/api/v1/notes/{note_id}/complete", response_model=NoteOut)
def complete_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    _mark_complete(note)
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    return note_to_out(note)


@router.post("/api/v1/notes/{note_id}/reopen", response_model=NoteOut)
def reopen_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    note.completed_at = None
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


class AdoptIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/api/v1/notes/{note_id}/review", response_model=NoteOut)
async def refresh_review(
    note_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.worker import _reviewing_payload, run_review

    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    prev = note.suggestions if isinstance(note.suggestions, dict) else {}
    note.suggestions = _reviewing_payload(prev)
    note.updated_at = utcnow()
    db.commit()
    db.refresh(note)
    background_tasks.add_task(run_review, note.id)
    return note_to_out(note)


@router.post("/api/v1/notes/{note_id}/suggestions/adopt", response_model=NoteOut)
def adopt_suggestion(
    note_id: str,
    body: AdoptIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    items = [coerce_action_item(x) for x in (note.action_items or [])]
    text = body.text.strip()
    if text and not any((i.get("text") or "").strip().lower() == text.lower() for i in items):
        items.append({"text": text, "due": None, "project": None, "checked": False})
        note.action_items = items
        note.completed_at = None
        note.updated_at = utcnow()
        db.commit()
        db.refresh(note)
    return note_to_out(note)


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
