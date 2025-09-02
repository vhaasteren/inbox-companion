from __future__ import annotations
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .imap_preview import preview as imap_preview
from .db import session_scope, engine
from .models import Message
from .repository import get_recent_messages
from .poller import start_scheduler
from sqlalchemy import text

app = FastAPI(title="Inbox Companion API", version="0.0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_scheduler = None


@app.on_event("startup")
def _on_startup():
    global _scheduler
    if _scheduler is None:
        _scheduler = start_scheduler()


@app.get("/healthz")
async def healthz():
    # verify DB connectivity too
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}


@app.get("/api/mail/preview")
async def api_mail_preview(limit: int = Query(10, ge=1, le=50)):
    # Live IMAP sanity endpoint
    return imap_preview(limit=limit)


@app.get("/api/messages/recent")
async def api_messages_recent(limit: int = Query(50, ge=1, le=200)):
    with session_scope() as s:
        rows = get_recent_messages(s, limit=limit)
        return {
            "items": [
                {
                    "id": r.id,
                    "mailbox": r.mailbox,
                    "uid": r.uid,
                    "message_id": r.message_id,
                    "subject": r.subject,
                    "from": r.from_raw,
                    "date": r.date_iso,
                    "snippet": r.snippet,
                }
                for r in rows
            ]
        }

