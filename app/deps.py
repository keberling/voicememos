from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.db import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def _user_by_token(db: Session, token: str) -> User | None:
    token = (token or "").strip()
    if not token:
        return None
    user = db.query(User).filter(User.api_token == token).one_or_none()
    if user is None:
        return None
    if not hmac.compare_digest(user.api_token, token):
        return None
    return user


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_api_token: Annotated[str | None, Header(alias="X-API-Token")] = None,
) -> User | None:
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
    elif x_api_token:
        token = x_api_token.strip()
    if token:
        return _user_by_token(db, token)

    uid = current_user_id(request)
    if not uid:
        return None
    return db.query(User).filter(User.id == uid).one_or_none()


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def get_html_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    uid = current_user_id(request)
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.query(User).filter(User.id == uid).one_or_none()
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
