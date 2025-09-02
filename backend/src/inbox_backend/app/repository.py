from __future__ import annotations
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from .models import Mailbox, Message


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


def upsert_messages(session: Session, messages: Iterable[dict]) -> int:
    """
    Insert messages if (mailbox, uid) not present. Returns count inserted.
    """
    inserted = 0
    for m in messages:
        exists = session.execute(
            select(Message.id).where(
                Message.mailbox == m["mailbox"],
                Message.uid == m["uid"],
            )
        ).scalar_one_or_none()
        if exists:
            continue
        obj = Message(**m)
        session.add(obj)
        inserted += 1
    return inserted


def get_recent_messages(session: Session, limit: int = 50) -> list[Message]:
    stmt = (
        select(Message)
        .order_by(func.coalesce(Message.date_iso, "") .desc(), Message.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())

