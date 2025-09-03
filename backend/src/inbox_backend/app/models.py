from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- Core mailbox/message storage (matches existing repository expectations) ---

class Mailbox(Base):
    __tablename__ = "mailbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    last_uid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox: Mapped[str] = mapped_column(String, index=True)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)

    message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    from_raw: Mapped[str] = mapped_column(Text, default="")
    from_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    from_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    date_iso: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    snippet: Mapped[str] = mapped_column(Text, default="")
    body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    body_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    is_unread: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_answered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_flagged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    in_reply_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    references_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps (match NOT NULL schema already present in SQLite)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("mailbox", "uid", name="uix_mailbox_uid"),
        Index("ix_msg_date", "date_iso"),
    )


class MessageBody(Base):
    __tablename__ = "message_body"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), unique=True, nullable=False, index=True)
    body_full: Mapped[str] = mapped_column(Text, nullable=False)


# --- LLM analysis & taxonomy ---

class MessageAnalysis(Base):
    __tablename__ = "message_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), unique=True, nullable=False, index=True)
    body_hash: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )


class Label(Base):
    __tablename__ = "label"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MessageLabel(Base):
    __tablename__ = "message_label"

    message_id: Mapped[int] = mapped_column(
        ForeignKey("message.id"), primary_key=True, index=True
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("label.id"), primary_key=True, index=True
    )

    __table_args__ = (UniqueConstraint("message_id", "label_id", name="uix_msg_label"),)


# --- Living prompt memory ---

class MemoryItem(Base):
    __tablename__ = "memory_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # rule|preference|project|contact|style|fact
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("kind", "key", name="uix_memory_kind_key"),)

