from __future__ import annotations

import logging
from typing import Any

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import User, new_api_token, new_id, utcnow

log = logging.getLogger("voiceportal.auth")

SESSION_USER_KEY = "user_id"

oauth = OAuth()
_oauth_ready = False


def configure_oauth(settings: Settings | None = None) -> None:
    global _oauth_ready
    settings = settings or get_settings()
    if _oauth_ready or not settings.entra_configured:
        return
    oauth.register(
        name="microsoft",
        client_id=settings.AZURE_AD_CLIENT_ID,
        client_secret=settings.AZURE_AD_CLIENT_SECRET,
        server_metadata_url=settings.entra_metadata_url,
        client_kwargs={"scope": "openid profile email User.Read"},
    )
    _oauth_ready = True


def current_user_id(request: Request) -> str | None:
    return request.session.get(SESSION_USER_KEY)


def login_user(request: Request, user: User) -> None:
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


def upsert_user_from_claims(db: Session, claims: dict[str, Any], graph: dict[str, Any] | None = None) -> User:
    graph = graph or {}
    oid = str(claims.get("oid") or claims.get("sub") or graph.get("id") or "").strip()
    if not oid:
        raise ValueError("Microsoft account is missing an object id.")

    email = _email_from(claims, graph)
    name = (
        str(graph.get("displayName") or claims.get("name") or claims.get("preferred_username") or email or "").strip()
        or "User"
    )
    if not email:
        email = f"{oid}@users.noreply.microsoft"

    user = db.query(User).filter(User.oid == oid).one_or_none()
    if user is None and email:
        user = db.query(User).filter(User.email == email.lower()).one_or_none()
    if user is None:
        user = User(
            id=new_id(),
            oid=oid,
            email=email.lower(),
            name=name,
            api_token=new_api_token(),
            created_at=utcnow(),
        )
        db.add(user)
    else:
        user.oid = oid
        user.email = email.lower()
        if name:
            user.name = name
        if not user.api_token:
            user.api_token = new_api_token()
    db.flush()
    return user


def email_allowed(email: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    allowed = settings.allowed_emails
    if not allowed:
        return True
    return email.strip().lower() in allowed


async def fetch_graph_me(access_token: str) -> dict[str, Any]:
    if not access_token:
        return {}
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
        if response.status_code >= 400:
            log.warning("Graph /me failed: %s %s", response.status_code, response.text[:300])
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        log.warning("Graph /me request error: %s", exc)
        return {}


def _email_from(claims: dict[str, Any], graph: dict[str, Any]) -> str:
    for source in (graph, claims):
        for key in ("mail", "email", "userPrincipalName", "preferred_username", "upn"):
            value = source.get(key)
            if value and "@" in str(value):
                return str(value).strip().lower()
    return ""
