from __future__ import annotations
from datetime import datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import Mailbox, Message, MessageBody


def ensure_mailbox(session: Session, name: str) -> Mailbox:
    mb = session.execute(select(Mailbox).where(Mailbox.name == name)).scalar_one_or_none()
    if not mb:
        mb = Mailbox(name=name, last_uid=0, last_seen=None)
        session.add(mb)
        session.flush()
    return mb


def get_last_uid(session: Session, mailbox: str) -> int:
    mb = ensure_mailbox(session, mailbox)
    return mb.last_uid


def set_last_uid(session: Session, mailbox: str, last_uid: int) -> None:
    mb = ensure_mailbox(session, mailbox)
    mb.last_uid = max(mb.last_uid, last_uid)
    mb.last_seen = datetime.utcnow()
    session.add(mb)


def upsert_messages(session: Session, rows: Iterable[dict]) -> int:
    """
    Insert-or-update messages by (mailbox, uid).
    On update: refresh flags (is_unread, is_answered, is_flagged) and body_preview if provided.
    Also ensures MessageBody is present if body_full provided and body row missing.
    Returns count of newly inserted rows.
    """
    inserted = 0
    for m in rows:
        body_full = m.pop("body_full", None)

        existing = session.execute(
            select(Message).where(
                Message.mailbox == m["mailbox"],
                Message.uid == m["uid"],
            )
        ).scalar_one_or_none()

        if existing:
            changed = False
            for k in ("is_unread", "is_answered", "is_flagged", "body_preview", "body_hash"):
                if k in m and getattr(existing, k) != m[k]:
                    setattr(existing, k, m[k]); changed = True
            for k in ("from_name", "from_email", "in_reply_to", "references_raw"):
                if k in m and getattr(existing, k) != m[k]:
                    setattr(existing, k, m[k]); changed = True
            if changed:
                session.add(existing)
            if body_full:
                has_body = session.execute(
                    select(MessageBody.id).where(MessageBody.message_id == existing.id)
                ).scalar_one_or_none()
                if not has_body:
                    session.add(MessageBody(message_id=existing.id, body_full=body_full))
            continue

        obj = Message(**m)
        session.add(obj)
        session.flush()
        if body_full:
            session.add(MessageBody(message_id=obj.id, body_full=body_full))
        inserted += 1

    return inserted


def update_flags_for_uids(session: Session, mailbox: str, flag_map: dict[int, tuple[int,int,int]]) -> int:
    touched = 0
    for uid, (unread, ans, flg) in flag_map.items():
        m = session.execute(
            select(Message).where(Message.mailbox == mailbox, Message.uid == uid)
        ).scalar_one_or_none()
        if not m:
            continue
        changed = False
        if m.is_unread != unread:
            m.is_unread = unread; changed = True
        if m.is_answered != ans:
            m.is_answered = ans; changed = True
        if m.is_flagged != flg:
            m.is_flagged = flg; changed = True
        if changed:
            session.add(m)
            touched += 1
    return touched


def get_recent_messages(session: Session, limit: int = 50) -> list[Message]:
    stmt = (
        select(Message)
        .order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def get_recent_uids(session: Session, mailbox: str, limit: int) -> list[int]:
    stmt = (
        select(Message.uid)
        .where(Message.mailbox == mailbox)
        .order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc())
        .limit(limit)
    )
    return [uid for (uid,) in session.execute(stmt)]


def search_messages(session: Session, q: str, limit: int = 50) -> list[Message]:
    """
    Full-text search using FTS5 over (subject, from_raw, snippet, body_preview).
    Ordered by recency (date_iso desc, id desc) for predictable UX.
    """
    # Use a raw SQL join since FTS5 virtual tables aren't mapped.
    rows = session.execute(text("""
        SELECT m.*
        FROM message m
        JOIN message_fts fts ON fts.rowid = m.id
        WHERE fts MATCH :q
        ORDER BY COALESCE(m.date_iso, '') DESC, m.id DESC
        LIMIT :lim
    """), {"q": q, "lim": int(limit)}).fetchall()
    # Convert to ORM objects via a second query on ids to avoid reflection hassles
    if not rows:
        return []
    ids = [r[0] for r in rows]  # first column is m.id
    stmt = select(Message).where(Message.id.in_(ids))
    # Preserve ordering by ids order
    obj_map = {m.id: m for m in session.execute(stmt).scalars()}
    return [obj_map[i] for i in ids if i in obj_map]


from sqlalchemy import text  # placed after functions to satisfy linters


def get_message_body(session: Session, message_id: int) -> Optional[str]:
    row = session.execute(
        select(MessageBody.body_full).where(MessageBody.message_id == message_id)
    ).scalar_one_or_none()
    return row

