from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def new_api_token() -> str:
    return "vnp_" + secrets.token_urlsafe(24)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    oid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    api_token: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    last_ingest_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    notes: Mapped[list[Note]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_user_status", "user_id", "status"),
        Index("ix_notes_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="Voice dump")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    lists: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    action_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ideas: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    raw_ai: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    merged_into_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="notes")
    merge_events: Mapped[list[MergeEvent]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="MergeEvent.created_at",
    )


class MergeEvent(Base):
    __tablename__ = "merge_events"
    __table_args__ = (UniqueConstraint("id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="voice")
    source_note_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    note: Mapped[Note] = relationship(back_populates="merge_events")
