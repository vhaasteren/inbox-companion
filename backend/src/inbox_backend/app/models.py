from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Mailbox(Base):
    __tablename__ = "mailbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    last_uid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("mailbox", "uid", name="uq_message_mailbox_uid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox: Mapped[str] = mapped_column(String(255), index=True)
    uid: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(512), index=True, nullable=True)

    subject: Mapped[str] = mapped_column(Text)
    from_raw: Mapped[str] = mapped_column(Text)
    date_iso: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    snippet: Mapped[str] = mapped_column(Text)            # ~ first 250 chars plain text
    body_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # sha256

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

