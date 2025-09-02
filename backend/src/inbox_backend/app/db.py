from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


# Ensure DB directory exists
db_file = Path(settings.db_path)
db_file.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{db_file}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Generator:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _column_exists(conn, table: str, col: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table});")).all()
    return any(r[1] == col for r in rows)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=:t"),
        {"t": table},
    ).fetchone()
    return row is not None


def _create_fts(conn) -> None:
    # Create FTS5 virtual table for search over message list data
    conn.execute(text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
            subject,
            from_raw,
            snippet,
            body_preview,
            content='message',
            content_rowid='id'
        );
    """))
    # Triggers to keep FTS in sync
    conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS message_ai AFTER INSERT ON message BEGIN
            INSERT INTO message_fts(rowid, subject, from_raw, snippet, body_preview)
            VALUES (new.id, new.subject, new.from_raw, new.snippet, new.body_preview);
        END;
    """))
    conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS message_ad AFTER DELETE ON message BEGIN
            INSERT INTO message_fts(message_fts, rowid) VALUES('delete', old.id);
        END;
    """))
    conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS message_au AFTER UPDATE ON message BEGIN
            INSERT INTO message_fts(message_fts, rowid) VALUES('delete', old.id);
            INSERT INTO message_fts(rowid, subject, from_raw, snippet, body_preview)
            VALUES (new.id, new.subject, new.from_raw, new.snippet, new.body_preview);
        END;
    """))
    # Backfill any rows that might be missing from FTS (idempotent)
    conn.execute(text("""
        INSERT INTO message_fts(rowid, subject, from_raw, snippet, body_preview)
        SELECT m.id, m.subject, m.from_raw, m.snippet, m.body_preview
        FROM message AS m
        WHERE NOT EXISTS (SELECT 1 FROM message_fts WHERE rowid = m.id);
    """))


def migrate_schema() -> None:
    """
    Naive SQLite in-place migrator: adds new columns/tables if missing.
    Safe to run on every startup.
    """
    from .models import Base as ModelsBase  # avoid circular
    ModelsBase.metadata.create_all(bind=engine)  # create tables if missing

    with engine.begin() as conn:
        # message table: add new columns if missing
        add_cols = {
            "from_name": "TEXT",
            "from_email": "TEXT",
            "in_reply_to": "TEXT",
            "references_raw": "TEXT",
            "is_unread": "INTEGER DEFAULT 1 NOT NULL",
            "is_answered": "INTEGER DEFAULT 0 NOT NULL",
            "is_flagged": "INTEGER DEFAULT 0 NOT NULL",
            "body_preview": "TEXT",
        }
        for col, decl in add_cols.items():
            if not _column_exists(conn, "message", col):
                conn.execute(text(f"ALTER TABLE message ADD COLUMN {col} {decl};"))

        # FTS virtual table and triggers
        _create_fts(conn)

