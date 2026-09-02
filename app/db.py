from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["pool_pre_ping"] = False
    return kwargs


settings = get_settings()
engine = create_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def init_db() -> None:
    from pathlib import Path

    from app import models  # noqa: F401

    url = settings.DATABASE_URL
    if url.startswith("sqlite:///") and ":memory:" not in url:
        raw = url.removeprefix("sqlite:///")
        if raw:
            Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    _ensure_notes_completed_at()


def _ensure_notes_completed_at() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "notes" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("notes")}
    if "completed_at" in cols:
        return
    ddl = (
        "ALTER TABLE notes ADD COLUMN completed_at DATETIME"
        if settings.DATABASE_URL.startswith("sqlite")
        else "ALTER TABLE notes ADD COLUMN completed_at TIMESTAMPTZ"
    )
    with engine.begin() as conn:
        conn.execute(text(ddl))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
