from __future__ import annotations
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .imap_preview import preview as imap_preview
from .db import session_scope, engine
from .models import Message
from .repository import get_recent_messages, search_messages, get_message_body
from .poller import start_scheduler, poll_once, backfill_since_days
from sqlalchemy import text

app = FastAPI(title="Inbox Companion API", version="0.2.0")

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
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True}


@app.get("/api/mail/preview")
async def api_mail_preview(limit: int = Query(10, ge=1, le=50)):
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
                    "from_name": r.from_name,
                    "from_email": r.from_email,
                    "date": r.date_iso,
                    "snippet": r.snippet,
                    "body_preview": r.body_preview,
                    "is_unread": bool(r.is_unread),
                    "is_answered": bool(r.is_answered),
                    "is_flagged": bool(r.is_flagged),
                    "in_reply_to": r.in_reply_to,
                    "references": r.references_raw,
                }
                for r in rows
            ]
        }


class BackfillRequest(BaseModel):
    mailbox: Optional[str] = None   # default: all mailboxes
    days: int                       # SINCE <days> (e.g., 400 to go further back)
    only_unseen: bool = True
    limit: Optional[int] = None     # process at most N UIDs (oldest first)


@app.post("/api/backfill")
async def api_backfill(req: BackfillRequest):
    mailboxes = [req.mailbox] if req.mailbox else settings.imap_mailboxes
    summaries = []
    for mb in mailboxes:
        res = backfill_since_days(mailbox=mb, days=req.days, only_unseen=req.only_unseen, limit=req.limit)
        summaries.append(res)
    total_inserted = sum(s["inserted"] for s in summaries)
    total_fetched = sum(s["fetched"] for s in summaries)
    return {"total_fetched": total_fetched, "total_inserted": total_inserted, "mailboxes": summaries}


@app.post("/api/refresh")
async def api_refresh_now():
    """
    Manually trigger one poll cycle across configured mailboxes.
    """
    summary = poll_once()
    return summary


@app.get("/api/messages/{message_id}/body")
async def api_message_body(message_id: int):
    with session_scope() as s:
        body = get_message_body(s, message_id)
    if body is None:
        raise HTTPException(status_code=404, detail="Body not found for message")
    return {"message_id": message_id, "body": body}


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=200)):
    with session_scope() as s:
        rows = search_messages(s, q=q, limit=limit)
        return {
            "items": [
                {
                    "id": r.id,
                    "mailbox": r.mailbox,
                    "uid": r.uid,
                    "message_id": r.message_id,
                    "subject": r.subject,
                    "from": r.from_raw,
                    "from_name": r.from_name,
                    "from_email": r.from_email,
                    "date": r.date_iso,
                    "snippet": r.snippet,
                    "body_preview": r.body_preview,
                    "is_unread": bool(r.is_unread),
                    "is_answered": bool(r.is_answered),
                    "is_flagged": bool(r.is_flagged),
                    "in_reply_to": r.in_reply_to,
                    "references": r.references_raw,
                }
                for r in rows
            ]
        }

