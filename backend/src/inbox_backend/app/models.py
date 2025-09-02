from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    from_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    from_email: Mapped[Optional[str]] = mapped_column(String(320), index=True, nullable=True)

    date_iso: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # threading
    in_reply_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    references_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # flags
    is_unread: Mapped[int] = mapped_column(Integer, default=1, nullable=False)    # 1=true, 0=false
    is_answered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_flagged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # body storage policy
    snippet: Mapped[str] = mapped_column(Text)            # ~ first 250 chars plain text
    body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # first ~2KB

    body_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # sha256
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    body: Mapped["MessageBody"] = relationship(back_populates="message", uselist=False)


class MessageBody(Base):
    __tablename__ = "message_body"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_message_body_message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id", ondelete="CASCADE"), nullable=False, index=True)
    body_full: Mapped[str] = mapped_column(Text, nullable=False)

    message: Mapped[Message] = relationship(back_populates="body")
