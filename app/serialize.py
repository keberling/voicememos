from __future__ import annotations

from app.models import Note
from app.schemas import MergeEventOut, NoteOut


def note_to_out(note: Note) -> NoteOut:
    events = [MergeEventOut.model_validate(e) for e in (note.merge_events or [])]
    return NoteOut(
        id=note.id,
        title=note.title,
        tags=list(note.tags or []),
        categories=list(note.categories or []),
        status=note.status,
        error=note.error,
        warning=note.warning,
        filename=note.filename,
        transcript=note.transcript,
        summary=note.summary,
        lists=dict(note.lists or {}),
        action_items=list(note.action_items or []),
        ideas=list(note.ideas or []),
        entities=dict(note.entities or {}),
        merged_into_id=note.merged_into_id,
        source=note.source,
        created_at=note.created_at,
        updated_at=note.updated_at,
        completed_at=note.completed_at,
        completed=bool(note.completed_at),
        merge_events=events,
        updated_from_voice=bool(events),
    )
