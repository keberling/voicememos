from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Note, User, new_id, utcnow
from app.schemas import IngestOut

log = logging.getLogger("voiceportal.ingest")
router = APIRouter(tags=["ingest"])

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _user_from_token(db: Session, token: str | None) -> User:
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    user = db.query(User).filter(User.api_token == token).one_or_none()
    if user is None or not hmac.compare_digest(user.api_token, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user


def _extract_token(
    request: Request,
    token: str | None,
    authorization: str | None,
) -> str | None:
    if token and token.strip():
        return token.strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
        if authorization.strip().startswith("vnp_"):
            return authorization.strip()
    return None


@router.post("/api/v1/ingest", response_model=IngestOut, status_code=202)
async def ingest(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    token: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    title: str | None = Form(default=None),
    source: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
):
    settings = get_settings()
    user_token = _extract_token(request, token, authorization)
    user = _user_from_token(db, user_token)

    raw_name = file.filename or "memo.m4a"
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_upload_bytes + (1024 * 64):
                raise HTTPException(status_code=413, detail="File too large")
        except ValueError:
            pass

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    note_id = new_id()
    safe = SAFE_NAME.sub("_", Path(raw_name).name) or "memo.m4a"
    dest_dir = settings.upload_path / user.id / note_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    note_title = (title or "").strip() or "Voice dump"
    note = Note(
        id=note_id,
        user_id=user.id,
        title=note_title,
        tags=tag_list,
        categories=[],
        status="queued",
        filename=safe,
        audio_path=str(dest),
        lists={},
        action_items=[],
        ideas=[],
        entities={},
        source=(source or "ios-shortcut").strip() or "ios-shortcut",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(note)
    db.commit()
    log.info("Ingested note %s for user %s (%s bytes)", note.id, user.id, len(data))
    return IngestOut(id=note.id, status="queued", title=note.title)
