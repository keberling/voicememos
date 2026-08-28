from __future__ import annotations

import re
from typing import Any

from app.schemas import StructureResult

STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "have",
    "just",
    "like",
    "want",
    "need",
    "also",
    "then",
    "than",
    "when",
    "what",
    "which",
    "your",
    "about",
    "into",
    "some",
    "them",
    "they",
    "were",
    "been",
    "will",
    "would",
    "could",
    "should",
    "there",
    "here",
    "it's",
    "dont",
    "don't",
    "gonna",
    "wanna",
    "yeah",
    "okay",
    "please",
    "today",
    "tomorrow",
    "maybe",
    "really",
    "thing",
    "things",
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def union_str_list(existing: list[str] | None, incoming: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, str):
            item = str(item)
        key = _norm(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def union_named_lists(
    existing: dict[str, list[str]] | None,
    incoming: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    """Union lists by name. Never smash unrelated lists into one blob."""
    out: dict[str, list[str]] = {}
    name_map: dict[str, str] = {}

    def canonical(name: str) -> str:
        key = _norm(name)
        return name_map.setdefault(key, name.strip() or "List")

    for source in (existing or {}, incoming or {}):
        if not isinstance(source, dict):
            continue
        for raw_name, items in source.items():
            name = canonical(str(raw_name))
            if not isinstance(items, list):
                items = [str(items)]
            out[name] = union_str_list(out.get(name, []), [str(x) for x in items])
    return out


def union_action_items(
    existing: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(incoming or []):
        coerced = coerce_action_item(item)
        key = _norm(coerced["text"])
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(coerced)
    return out


def coerce_action_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"text": item.strip(), "due": None, "project": None, "checked": False}
    if not isinstance(item, dict):
        return {"text": str(item), "due": None, "project": None, "checked": False}
    text = str(item.get("text") or item.get("title") or item.get("item") or "").strip()
    due = item.get("due")
    project = item.get("project")
    if due is not None:
        due = str(due).strip() or None
    if project is not None:
        project = str(project).strip() or None
    checked = bool(item.get("checked", False))
    return {"text": text, "due": due, "project": project, "checked": checked}


def coerce_lists(value: Any) -> dict[str, list[str]]:
    if not value:
        return {}
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
        return {"List": items} if items else {}
    if isinstance(value, dict):
        out: dict[str, list[str]] = {}
        for name, items in value.items():
            if isinstance(items, list):
                cleaned = [str(x).strip() for x in items if str(x).strip()]
            elif items:
                cleaned = [str(items).strip()]
            else:
                cleaned = []
            if cleaned:
                out[str(name).strip() or "List"] = cleaned
        return out
    return {}


def coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            key = _norm(text)
            if text and key not in seen:
                seen.add(key)
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def coerce_entities(value: Any) -> dict[str, Any]:
    empty = {"names": [], "places": [], "vendors": [], "tickets": []}
    if not value:
        return dict(empty)
    if isinstance(value, list):
        names = [str(x).strip() for x in value if str(x).strip()]
        return {**empty, "names": names}
    if isinstance(value, dict):
        out = dict(empty)
        for key in empty:
            out[key] = coerce_str_list(value.get(key))
        extras = {
            k: coerce_str_list(v)
            for k, v in value.items()
            if k not in empty and v
        }
        out.update(extras)
        return out
    return empty


def apply_structure_to_note_fields(result: StructureResult) -> dict[str, Any]:
    return {
        "title": (result.title or "Voice dump").strip() or "Voice dump",
        "summary": (result.summary or "").strip(),
        "categories": coerce_str_list(result.categories),
        "tags": coerce_str_list(result.tags),
        "lists": coerce_lists(result.lists),
        "action_items": union_action_items([], result.action_items),
        "ideas": coerce_str_list(result.ideas),
        "entities": coerce_entities(result.entities),
    }


def merge_into_existing(existing: dict[str, Any], incoming: StructureResult) -> dict[str, Any]:
    """Merge structured dump into an existing note. Keep speaker wording. Do not invent."""
    title = existing.get("title") or incoming.title or "Voice dump"
    if title.strip().lower() in {"voice dump", "untitled", "untitled voice dump"} and incoming.title:
        title = incoming.title
    return {
        "title": title,
        "summary": (incoming.summary or existing.get("summary") or "").strip(),
        "categories": union_str_list(existing.get("categories") or [], incoming.categories),
        "tags": union_str_list(existing.get("tags") or [], incoming.tags),
        "lists": union_named_lists(existing.get("lists") or {}, incoming.lists),
        "action_items": union_action_items(existing.get("action_items") or [], incoming.action_items),
        "ideas": union_str_list(existing.get("ideas") or [], incoming.ideas),
        "entities": _merge_entities(existing.get("entities") or {}, incoming.entities),
    }


def _merge_entities(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    a = coerce_entities(existing)
    b = coerce_entities(incoming)
    keys = set(a) | set(b)
    return {k: union_str_list(a.get(k) or [], b.get(k) or []) for k in keys}


def transcript_tokens(transcript: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'-]{2,}", (transcript or "").lower())
    return {w for w in words if w not in STOPWORDS}


def overlap_score(transcript: str, blob: str) -> int:
    tokens = transcript_tokens(transcript)
    if not tokens:
        return 0
    haystack = set(transcript_tokens(blob))
    return len(tokens & haystack)


def note_search_blob(note: Any) -> str:
    parts: list[str] = [
        getattr(note, "title", "") or "",
        getattr(note, "summary", "") or "",
        " ".join(getattr(note, "tags", None) or []),
        " ".join(getattr(note, "categories", None) or []),
    ]
    lists = getattr(note, "lists", None) or {}
    if isinstance(lists, dict):
        for name, items in lists.items():
            parts.append(str(name))
            parts.extend(str(x) for x in (items or []))
    for item in getattr(note, "action_items", None) or []:
        if isinstance(item, dict):
            parts.append(str(item.get("text") or ""))
        else:
            parts.append(str(item))
    ideas = getattr(note, "ideas", None) or []
    parts.extend(str(x) for x in ideas)
    entities = getattr(note, "entities", None) or {}
    if isinstance(entities, dict):
        for v in entities.values():
            if isinstance(v, list):
                parts.extend(str(x) for x in v)
            else:
                parts.append(str(v))
    return " ".join(parts)


def excerpt(text: str, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
