from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.merge import coerce_action_item, coerce_entities, coerce_lists, coerce_str_list
from app.schemas import StructureResult

log = logging.getLogger("voiceportal.llm")

SYSTEM_PROMPT = """You process every personal voice dump. Nothing is too small.

Decide if this continues an existing note of any kind. If yes, merge. If no, create.
Infer categories and tags from content. Do not force a grocery or shopping frame.
Pull out every list, task, decision, name, date, place, and idea that was actually said.
Deduplicate case-insensitive when merging. Keep the speaker's wording. Do not invent content.
A mixed dump can merge the matching part and keep leftover content in ideas, or create if nothing matches.

Possible types, not a closed list: list, task, idea, meeting, job, home, family, travel, money, vehicle, tech, reminder, journal, mixed.

Return JSON only with this shape:
{
  "action": "merge" or "create",
  "target_note_id": string or null,
  "title": string,
  "summary": string,
  "categories": string[],
  "tags": string[],
  "lists": { "<list name>": string[] },
  "action_items": [{ "text": string, "due": string or null, "project": string or null }],
  "ideas": string[],
  "entities": { "names": string[], "places": string[], "vendors": string[], "tickets": string[] },
  "confidence": number
}

lists is an object keyed by list name, not a single array. Empty object if there are no lists.
action_items due and project are null if unsaid.
entities only include names, places, vendors, ticket numbers actually spoken.
Grocery is one example of a list, not the schema. Classify from any dump.
If this is a new topic, action must be create and target_note_id must be null.
If this continues an existing candidate, action is merge and target_note_id is that candidate's id.
"""


class LLMError(RuntimeError):
    pass


def _client_timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(connect=15.0, read=seconds, write=30.0, pool=15.0)


async def transcribe_audio(path: str | Path, filename: str | None = None, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.stt_base_url or not settings.stt_api_key:
        raise LLMError("STT is not configured. Set LLM_BASE_URL and LLM_API_KEY (or STT_* overrides).")

    audio_path = Path(path)
    name = filename or audio_path.name
    url = f"{settings.stt_base_url}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.stt_api_key}"}
    data = {"model": settings.STT_MODEL or "whisper-1"}

    content = audio_path.read_bytes()
    files = {"file": (name, content, _guess_audio_type(name))}

    async with httpx.AsyncClient(timeout=_client_timeout(180.0)) as client:
        try:
            response = await client.post(url, headers=headers, data=data, files=files)
        except httpx.HTTPError as exc:
            raise LLMError(f"Transcription request failed: {exc}") from exc

    if response.status_code >= 400:
        raise LLMError(f"Transcription failed ({response.status_code}): {_trim(response.text)}")

    payload = _safe_json(response.text)
    text = ""
    if isinstance(payload, dict):
        text = str(payload.get("text") or payload.get("transcript") or "").strip()
    elif isinstance(payload, str):
        text = payload.strip()
    if not text:
        raise LLMError("Transcription returned empty text.")
    return text


async def structure_dump(
    transcript: str,
    candidates: list[dict[str, Any]],
    *,
    extra_title: str | None = None,
    extra_tags: list[str] | None = None,
    settings: Settings | None = None,
) -> StructureResult:
    settings = settings or get_settings()
    if not settings.llm_base_url or not settings.LLM_API_KEY or not settings.LLM_MODEL:
        raise LLMError("LLM router is not configured. Set LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL.")

    user_payload = {
        "transcript": transcript,
        "optional_title": extra_title or None,
        "optional_tags": extra_tags or [],
        "existing_notes": candidates,
        "instructions": (
            "Use existing_notes to decide merge vs create. "
            "Only merge if this dump continues one of those notes."
        ),
    }
    body = {
        "model": settings.LLM_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    url = f"{settings.llm_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=_client_timeout(90.0)) as client:
        try:
            response = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Structuring request failed: {exc}") from exc

    if response.status_code >= 400:
        raise LLMError(f"Structuring failed ({response.status_code}): {_trim(response.text)}")

    payload = _safe_json(response.text)
    content = _message_content(payload)
    return parse_structure_response(content, raw=payload)


def parse_structure_response(content: str | dict | list | None, raw: Any = None) -> StructureResult:
    warning = None
    data: Any = content
    if isinstance(content, str):
        data, warning = _extract_json(content)
    if not isinstance(data, dict):
        return StructureResult(
            action="create",
            title="Voice dump",
            ideas=[str(content or "").strip()] if content else [],
            parse_warning="Could not parse AI response; kept raw transcript in ideas.",
            raw=raw if raw is not None else content,
        )

    action = str(data.get("action") or "create").strip().lower()
    if action not in {"merge", "create"}:
        action = "create"

    target = data.get("target_note_id")
    if target is not None:
        target = str(target).strip() or None

    items = data.get("action_items") or []
    if not isinstance(items, list):
        items = [items]
    action_items = [coerce_action_item(x) for x in items if x]

    confidence = data.get("confidence", 0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    return StructureResult(
        action=action,
        target_note_id=target,
        title=str(data.get("title") or "Voice dump").strip() or "Voice dump",
        summary=str(data.get("summary") or "").strip(),
        categories=coerce_str_list(data.get("categories")),
        tags=coerce_str_list(data.get("tags")),
        lists=coerce_lists(data.get("lists")),
        action_items=action_items,
        ideas=coerce_str_list(data.get("ideas")),
        entities=coerce_entities(data.get("entities")),
        confidence=max(0.0, min(1.0, confidence)),
        parse_warning=warning,
        raw=raw if raw is not None else data,
    )


def _extract_json(text: str) -> tuple[Any, str | None]:
    text = (text or "").strip()
    if not text:
        return None, "empty model output"
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1)), None
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1]), None
        except json.JSONDecodeError:
            pass
    return None, "Could not parse AI response; kept raw transcript in ideas."


def _message_content(payload: Any) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("text"):
                        parts.append(str(block["text"]))
                    else:
                        parts.append(str(block))
                return "\n".join(parts)
            if content:
                return str(content)
        if "text" in payload:
            return str(payload["text"])
    return str(payload or "")


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _trim(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _guess_audio_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return {
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".caf": "audio/x-caf",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".flac": "audio/flac",
    }.get(suffix, "application/octet-stream")
