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


def collect_filters(notes: list[Note]) -> tuple[list[str], list[str]]:
    tags: list[str] = []
    cats: list[str] = []
    seen_t: set[str] = set()
    seen_c: set[str] = set()
    for note in notes:
        for tag in note.tags or []:
            key = str(tag).lower()
            if key not in seen_t:
                seen_t.add(key)
                tags.append(str(tag))
        for cat in note.categories or []:
            key = str(cat).lower()
            if key not in seen_c:
                seen_c.add(key)
                cats.append(str(cat))
    return tags, cats
