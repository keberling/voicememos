from __future__ import annotations

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session, selectinload

from app.models import Note


def user_notes_query(db: Session, user_id: str, *, include_merged: bool = False):
    q = (
        db.query(Note)
        .options(selectinload(Note.merge_events))
        .filter(Note.user_id == user_id)
    )
    if not include_merged:
        q = q.filter(Note.status != "merged")
    return q


def search_notes(
    db: Session,
    user_id: str,
    *,
    q: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    include_merged: bool = False,
) -> list[Note]:
    query = user_notes_query(db, user_id, include_merged=include_merged)
    if q:
        like = f"%{q.strip()}%"
        blob = cast(Note.lists, String)
        actions = cast(Note.action_items, String)
        ideas = cast(Note.ideas, String)
        entities = cast(Note.entities, String)
        tags_s = cast(Note.tags, String)
        cats = cast(Note.categories, String)
        query = query.filter(
            or_(
                Note.title.ilike(like),
                Note.transcript.ilike(like),
                Note.summary.ilike(like),
                Note.error.ilike(like),
                blob.ilike(like),
                actions.ilike(like),
                ideas.ilike(like),
                entities.ilike(like),
                tags_s.ilike(like),
                cats.ilike(like),
            )
        )
    notes = query.order_by(Note.updated_at.desc()).all()
    if tag:
        needle = tag.strip().lower()
        notes = [n for n in notes if needle in {str(t).lower() for t in (n.tags or [])}]
    if category:
        needle = category.strip().lower()
        notes = [n for n in notes if needle in {str(c).lower() for c in (n.categories or [])}]
    return notes


def get_owned_note(db: Session, user_id: str, note_id: str) -> Note | None:
    return (
        db.query(Note)
        .options(selectinload(Note.merge_events))
        .filter(Note.id == note_id, Note.user_id == user_id)
        .one_or_none()
    )


def collect_filters(notes: list) -> tuple[list[str], list[str]]:
    """Tags/categories only from notes that still exist in this list.

    Merged dumps and deleted notes are not passed in. Empty labels are ignored.
    """
    tags: list[str] = []
    cats: list[str] = []
    seen_t: set[str] = set()
    seen_c: set[str] = set()
    for note in notes:
        status = getattr(note, "status", None) or (note.get("status") if isinstance(note, dict) else "")
        if status == "merged":
            continue
        for tag in getattr(note, "tags", None) or (note.get("tags") if isinstance(note, dict) else None) or []:
            text = str(tag).strip()
            key = text.lower()
            if not text or key in seen_t:
                continue
            seen_t.add(key)
            tags.append(text)
        for cat in getattr(note, "categories", None) or (note.get("categories") if isinstance(note, dict) else None) or []:
            text = str(cat).strip()
            key = text.lower()
            if not text or key in seen_c:
                continue
            seen_c.add(key)
            cats.append(text)
    return tags, cats
