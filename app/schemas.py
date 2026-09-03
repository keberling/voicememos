from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenRotateOut(BaseModel):
    api_token: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    api_token: str
    created_at: datetime
    last_ingest_ok_at: datetime | None = None
    ingest_url: str
    setup_complete: bool


class IngestOut(BaseModel):
    id: str
    status: str = "queued"
    title: str


class MergeEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    source_note_id: str | None = None
    excerpt: str
    created_at: datetime


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    status: str
    error: str | None = None
    warning: str | None = None
    filename: str | None = None
    transcript: str | None = None
    summary: str | None = None
    lists: dict[str, list[str]] = Field(default_factory=dict)
    action_items: list[dict[str, Any]] = Field(default_factory=list)
    ideas: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    merged_into_id: str | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    completed: bool = False
    suggestions: dict[str, Any] | None = None
    merge_events: list[MergeEventOut] = Field(default_factory=list)
    updated_from_voice: bool = False


class NotePatch(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    categories: list[str] | None = None
    summary: str | None = None
    transcript: str | None = None
    lists: dict[str, list[str]] | None = None
    action_items: list[dict[str, Any]] | None = None
    ideas: list[str] | None = None
    entities: dict[str, Any] | None = None
    completed: bool | None = None


class ActionCheckIn(BaseModel):
    checked: bool


class StructureResult(BaseModel):
    action: str = "create"
    target_note_id: str | None = None
    title: str = "Voice dump"
    summary: str = ""
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    lists: dict[str, list[str]] = Field(default_factory=dict)
    action_items: list[dict[str, Any]] = Field(default_factory=list)
    ideas: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    parse_warning: str | None = None
    raw: Any = None
