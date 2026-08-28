from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    configure_oauth,
    email_allowed,
    fetch_graph_me,
    login_user,
    logout_user,
    oauth,
    upsert_user_from_claims,
)
from app.config import get_settings
from app.db import get_db
from app.models import Note

log = logging.getLogger("voiceportal.auth")
router = APIRouter(tags=["auth"])


@router.get("/auth/login")
async def login(request: Request):
    settings = get_settings()
    if not settings.entra_configured:
        return RedirectResponse("/login?error=entra", status_code=302)
    configure_oauth(settings)
    return await oauth.microsoft.authorize_redirect(request, settings.auth_callback_url)


@router.get("/auth/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.entra_configured:
        return RedirectResponse("/login?error=entra", status_code=302)
    configure_oauth(settings)
    try:
        token = await oauth.microsoft.authorize_access_token(request)
    except Exception:
        log.exception("OIDC token exchange failed")
        return RedirectResponse("/login?error=oauth", status_code=302)

    claims = token.get("userinfo") or {}
    if not claims:
        try:
            claims = await oauth.microsoft.parse_id_token(request, token)
        except Exception:
            log.exception("OIDC id_token parse failed")
            claims = {}
    if not isinstance(claims, dict):
        claims = {}

    access_token = token.get("access_token") or ""
    graph = await fetch_graph_me(access_token)
    try:
        user = upsert_user_from_claims(db, claims, graph)
    except ValueError:
        return RedirectResponse("/login?error=profile", status_code=302)

    if not email_allowed(user.email, settings):
        logout_user(request)
        return RedirectResponse("/login?error=forbidden", status_code=302)

    db.commit()
    login_user(request, user)
    has_notes = db.query(Note.id).filter(Note.user_id == user.id).first() is not None
    if not has_notes:
        return RedirectResponse("/setup", status_code=302)
    return RedirectResponse("/", status_code=302)


@router.get("/auth/logout")
@router.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=302)
