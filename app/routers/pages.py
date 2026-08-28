from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.config import get_settings
from app.db import get_db
from app.deps import get_html_user
from app.models import Note, User, new_api_token, utcnow
from app.notes_query import collect_filters, get_owned_note, search_notes, user_notes_query
from app.serialize import note_to_out

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["pages"])


def _ctx(request: Request, user: User | None = None, **extra):
    settings = get_settings()
    data = {
        "request": request,
        "app_name": settings.APP_NAME,
        "user": user,
        "settings": settings,
        "ingest_url": settings.ingest_url,
        "shortcut_icloud_url": settings.SHORTCUT_ICLOUD_URL,
        "shortcut_file_url": settings.shortcut_file_url,
        "shortcut_add_url": settings.shortcut_add_url,
        "shortcut_import_url": settings.shortcut_import_url,
        "share_sheet_shortcut_url": settings.hosted_share_sheet_shortcut_url,
        "nav": extra.pop("nav", ""),
    }
    data.update(extra)
    return data


def _latest_note(db: Session, user_id: str) -> Note | None:
    return (
        db.query(Note)
        .filter(Note.user_id == user_id)
        .order_by(Note.created_at.desc())
        .first()
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None, db: Session = Depends(get_db)):
    uid = current_user_id(request)
    if uid:
        user = db.query(User).filter(User.id == uid).one_or_none()
        if user:
            return RedirectResponse("/", status_code=302)
    messages = {
        "entra": "Microsoft sign-in is not configured. Set AZURE_AD_CLIENT_ID, AZURE_AD_CLIENT_SECRET, and AZURE_AD_TENANT_ID.",
        "oauth": "Microsoft sign-in failed. Try again.",
        "forbidden": "That Microsoft account is not on the allow list.",
        "profile": "Microsoft did not return a usable user profile.",
    }
    return templates.TemplateResponse(
        request,
        "login.html",
        _ctx(
            request,
            error_message=messages.get(error or "", ""),
            entra_configured=get_settings().entra_configured,
            nav="login",
        ),
    )


@router.get("/", response_class=HTMLResponse)
@router.get("/notes", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    q: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    category: str | None = Query(default=None),
    user: User = Depends(get_html_user),
    db: Session = Depends(get_db),
):
    notes = search_notes(db, user.id, q=q, tag=tag, category=category, include_merged=False)
    all_notes = user_notes_query(db, user.id, include_merged=False).all()
    tags, cats = collect_filters(all_notes)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(
            request,
            user,
            notes=[note_to_out(n) for n in notes],
            q=q or "",
            active_tag=tag or "",
            active_category=category or "",
            all_tags=tags,
            all_categories=cats,
            in_flight=[
                note_to_out(n)
                for n in all_notes
                if n.status in {"queued", "transcribing", "structuring"}
            ],
            nav="notes",
            live_notes=True,
        ),
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(
    request: Request,
    rotated: str | None = None,
    user: User = Depends(get_html_user),
    db: Session = Depends(get_db),
):
    latest = _latest_note(db, user.id)
    return templates.TemplateResponse(
        request,
        "setup.html",
        _ctx(
            request,
            user,
            rotated=rotated == "1",
            nav="setup",
            latest_note=note_to_out(latest) if latest else None,
        ),
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    rotated: str | None = None,
    user: User = Depends(get_html_user),
):
    return templates.TemplateResponse(
        request,
        "settings.html",
        _ctx(
            request,
            user,
            rotated=rotated == "1",
            nav="settings",
        ),
    )


@router.post("/settings/token/rotate")
async def rotate_token_form(
    user: User = Depends(get_html_user),
    db: Session = Depends(get_db),
    next: str = Form(default="/settings"),
):
    user.api_token = new_api_token()
    db.add(user)
    db.commit()
    dest = "/setup" if next.startswith("/setup") else "/settings"
    return RedirectResponse(f"{dest}?rotated=1", status_code=303)


@router.get("/notes/{note_id}", response_class=HTMLResponse)
async def note_page(
    note_id: str,
    request: Request,
    user: User = Depends(get_html_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    target = None
    if note.merged_into_id:
        target = get_owned_note(db, user.id, note.merged_into_id)
    return templates.TemplateResponse(
        request,
        "note.html",
        _ctx(
            request,
            user,
            note=note_to_out(note),
            merged_into=note_to_out(target) if target else None,
            nav="notes",
        ),
    )


@router.post("/notes/{note_id}/retry")
async def retry_form(
    note_id: str,
    user: User = Depends(get_html_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.status != "merged":
        note.status = "queued"
        note.error = None
        note.updated_at = utcnow()
        db.commit()
    return RedirectResponse(f"/notes/{note_id}", status_code=303)


@router.post("/notes/{note_id}/delete")
async def delete_form(
    note_id: str,
    user: User = Depends(get_html_user),
    db: Session = Depends(get_db),
):
    note = get_owned_note(db, user.id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    audio_path = note.audio_path
    db.delete(note)
    db.commit()
    if audio_path:
        path = Path(audio_path)
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    return RedirectResponse("/", status_code=303)


def filter_qs(**kwargs) -> str:
    items = {k: v for k, v in kwargs.items() if v}
    return ("?" + urlencode(items)) if items else ""


templates.env.globals["filter_qs"] = filter_qs
