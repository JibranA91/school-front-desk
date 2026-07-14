from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    # Fail fast instead of blocking forever if a DDL lock is held by another
    # (possibly orphaned) connection — otherwise startup init_db() can hang.
    connect_args={"options": "-c lock_timeout=4000"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Enable pgvector and create tables. Idempotent; safe to call on startup."""
    # Import models so their tables register on Base.metadata.
    from app import models  # noqa: F401

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    # Lightweight additive migrations (no Alembic): bring existing tables up to
    # date without a reseed. IF NOT EXISTS makes each idempotent.
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS topic VARCHAR(40)")
        )
        conn.execute(
            text("ALTER TABLE changelog ADD COLUMN IF NOT EXISTS snapshot JSONB")
        )
        conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS updates_seen_at TIMESTAMPTZ")
        )
