from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

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


def _extract_token(request: Request, token: str | None, authorization: str | None) -> str | None:
    if token and str(token).strip():
        return str(token).strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
        if authorization.strip().startswith("vnp_"):
            return authorization.strip()
    q = request.query_params.get("token")
    if q and q.strip():
        return q.strip()
    return None


def _filename_from_type(content_type: str, fallback: str = "memo.m4a") -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    return {
        "audio/mp4": "memo.m4a",
        "audio/x-m4a": "memo.m4a",
        "audio/m4a": "memo.m4a",
        "audio/aac": "memo.aac",
        "audio/mpeg": "memo.mp3",
        "audio/wav": "memo.wav",
        "audio/x-wav": "memo.wav",
        "audio/webm": "memo.webm",
        "audio/ogg": "memo.ogg",
        "audio/x-caf": "memo.caf",
    }.get(ctype, fallback)


@router.post("/api/v1/ingest", response_model=IngestOut, status_code=202)
async def ingest(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Accept multipart (file=) or a raw audio body.

    iOS Shortcuts will not put Recorded Audio into a Form text field.
    The working shortcut uses Request Body: File plus Authorization: Bearer.
    """
    settings = get_settings()
    content_type = (request.headers.get("content-type") or "").lower()

    token = request.query_params.get("token")
    tags = request.query_params.get("tags")
    title = request.query_params.get("title")
    source = request.query_params.get("source")
    data = b""
    filename = "memo.m4a"

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_upload_bytes + (1024 * 64):
                raise HTTPException(status_code=413, detail="File too large")
        except ValueError:
            pass

    if "multipart/form-data" in content_type:
        form = await request.form()
        token = token or form.get("token")  # type: ignore[assignment]
        tags = tags or form.get("tags")  # type: ignore[assignment]
        title = title or form.get("title")  # type: ignore[assignment]
        source = source or form.get("source")  # type: ignore[assignment]
        upload = form.get("file")
        if isinstance(upload, UploadFile):
            data = await upload.read()
            filename = upload.filename or filename
        elif upload:
            raise HTTPException(status_code=400, detail="file must be an audio upload")
    else:
        data = await request.body()
        filename = _filename_from_type(content_type, filename)
        disp = request.headers.get("content-disposition") or ""
        match = re.search(r'filename="?([^";]+)"?', disp, re.I)
        if match:
            filename = match.group(1)

    user = _user_from_token(db, _extract_token(request, token if isinstance(token, str) else None, authorization))

    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    note_id = new_id()
    safe = SAFE_NAME.sub("_", Path(filename).name) or "memo.m4a"
    dest_dir = settings.upload_path / user.id / note_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)

    tag_list = []
    if tags and isinstance(tags, str):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    note_title = (str(title).strip() if title else "") or "Voice dump"
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
        source=(str(source).strip() if source else "ios-shortcut") or "ios-shortcut",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(note)
    db.commit()
    log.info("Ingested note %s for user %s (%s bytes)", note.id, user.id, len(data))
    return IngestOut(id=note.id, status="queued", title=note.title)
