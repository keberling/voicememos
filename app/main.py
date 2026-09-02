from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import configure_oauth
from app.config import get_settings
from app.db import init_db
from app.routers import auth, ingest, me, notes, pages, shortcuts
from app.worker import reset_stuck_notes, worker_loop
from app.db import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("voiceportal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    init_db()
    configure_oauth(settings)
    db = SessionLocal()
    try:
        reset_stuck_notes(db)
    finally:
        db.close()

    worker_task = None
    if not settings.DISABLE_WORKER:
        worker_task = asyncio.create_task(worker_loop(), name="voiceportal-worker")
    yield
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


settings = get_settings()
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="vp_session",
    same_site="lax",
    https_only=settings.cookie_secure,
    max_age=60 * 60 * 24 * 30,
)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(me.router)
app.include_router(notes.router)
app.include_router(shortcuts.router)


@app.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "name": s.APP_NAME,
        "llm": {
            "configured": s.llm_configured,
            "base_url": s.llm_base_url or None,
            "model": s.llm_model or None,
            "stt_model": s.STT_MODEL or None,
        },
    }


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    api = request.url.path.startswith("/api/")
    accept = request.headers.get("accept") or ""
    wants_html = "text/html" in accept or (not api and "application/json" not in accept)
    if exc.status_code == 401 and wants_html and not api:
        return RedirectResponse("/login", status_code=302)
    if api:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    return HTMLResponse("<h1>Something went wrong</h1>", status_code=500)
