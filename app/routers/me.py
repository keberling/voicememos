from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User, new_api_token
from app.schemas import MeOut, TokenRotateOut

router = APIRouter(tags=["me"])


@router.get("/api/v1/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    settings = get_settings()
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        api_token=user.api_token,
        created_at=user.created_at,
        last_ingest_ok_at=user.last_ingest_ok_at,
        ingest_url=settings.ingest_url,
        setup_complete=user.last_ingest_ok_at is not None,
    )


@router.post("/api/v1/me/token/rotate", response_model=TokenRotateOut)
def rotate_token(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.api_token = new_api_token()
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenRotateOut(api_token=user.api_token)
