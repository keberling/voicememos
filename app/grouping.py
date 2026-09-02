from __future__ import annotations

from collections import defaultdict
from typing import Any


def action_items(note: Any) -> list[dict]:
    items = getattr(note, "action_items", None) or (note.get("action_items") if isinstance(note, dict) else None) or []
    out = []
    for item in items:
        if isinstance(item, str):
            out.append({"text": item, "due": None, "project": None, "checked": False})
        elif isinstance(item, dict):
            out.append(item)
    return out


def open_actions(note: Any) -> list[dict]:
    return [i for i in action_items(note) if not i.get("checked")]


def done_actions(note: Any) -> list[dict]:
    return [i for i in action_items(note) if i.get("checked")]


def primary_group(note: Any) -> str:
    cats = list(getattr(note, "categories", None) or (note.get("categories") if isinstance(note, dict) else None) or [])
    if cats:
        return str(cats[0])
    tags = list(getattr(note, "tags", None) or (note.get("tags") if isinstance(note, dict) else None) or [])
    if tags:
        return str(tags[0])
    return "Inbox"


def is_completed(note: Any) -> bool:
    if getattr(note, "completed_at", None):
        return True
    if isinstance(note, dict) and note.get("completed_at"):
        return True
    items = action_items(note)
    if items and all(i.get("checked") for i in items):
        return True
    return False


def group_notes(notes: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, list[Any]] = defaultdict(list)
    latest: dict[str, Any] = {}
    for note in notes:
        key = primary_group(note)
        buckets[key].append(note)
        updated = getattr(note, "updated_at", None) or (note.get("updated_at") if isinstance(note, dict) else None)
        prev = latest.get(key)
        if prev is None or (updated and updated > prev):
            latest[key] = updated

    names = sorted(buckets, key=lambda n: (n == "Inbox", -(latest[n].timestamp() if latest[n] else 0), n.lower()))
    groups = []
    for name in names:
        members = buckets[name]
        open_n = sum(len(open_actions(n)) for n in members)
        total_n = sum(len(action_items(n)) for n in members)
        groups.append(
            {
                "name": name,
                "notes": members,
                "open_tasks": open_n,
                "total_tasks": total_n,
                "note_count": len(members),
            }
        )
    return groups
