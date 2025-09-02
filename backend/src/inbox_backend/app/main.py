from __future__ import annotations
from typing import Optional, List, Dict, Any

import hashlib
import json
import logging
from datetime import datetime

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from sqlalchemy import text

from .config import settings
from .imap_preview import preview as imap_preview
from .db import session_scope, engine
from .models import Message
from .repository import (
    get_recent_messages, search_messages, get_message_body,
    list_labels, upsert_label, labels_for_message,
    get_backlog, get_analysis, upsert_analysis, apply_labels,
    list_memory, upsert_memory, compose_allowed_labels,
)
from .poller import start_scheduler, poll_once, backfill_since_days
from .llm_client import chat_json, SYSTEM_SUMMARY_PROMPT, build_summary_user_prompt, compose_memory_block, ping_models

# Logger
logger = logging.getLogger("inbox")
if not logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

app = FastAPI(title="Inbox Companion API", version="0.3.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "cors_origins", ["*"]),
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


# --------------------
# Existing feeds
# --------------------

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
    mailboxes = [req.mailbox] if req.mailbox else getattr(settings, "imap_mailboxes", ["INBOX"])
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


# --------------------
# Labels API
# --------------------

class LabelIn(BaseModel):
    name: str
    color: Optional[str] = None
    weight: int = 0


@app.get("/api/labels")
async def api_labels_list():
    with session_scope() as s:
        labs = list_labels(s)
        return {"labels": [{"id": l.id, "name": l.name, "color": l.color, "weight": l.weight} for l in labs]}


@app.post("/api/labels")
async def api_labels_upsert(lab: LabelIn):
    with session_scope() as s:
        row = upsert_label(s, lab.name, lab.color, lab.weight)
        return {"id": row.id, "name": row.name, "color": row.color, "weight": row.weight}


# --------------------
# Memory API (living prompt)
# --------------------

class MemoryItemIn(BaseModel):
    kind: str
    key: str
    value: str
    weight: int = 0
    expires_at: Optional[str] = None  # ISO timestamp or None

    @validator("kind")
    def _kind_ok(cls, v: str) -> str:
        return v.strip().lower()


@app.get("/api/memory")
async def api_memory_list(kind: Optional[str] = None):
    with session_scope() as s:
        rows = list_memory(s, kind=kind)
        return {
            "items": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "key": r.key,
                    "value": r.value,
                    "weight": r.weight,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "updated_at": r.updated_at.isoformat(),
                }
                for r in rows
            ]
        }


@app.post("/api/memory")
async def api_memory_upsert(item: MemoryItemIn):
    exp_dt = None
    if item.expires_at:
        try:
            exp_dt = datetime.fromisoformat(item.expires_at)
        except Exception:
            raise HTTPException(status_code=400, detail="expires_at must be ISO datetime or null")
    with session_scope() as s:
        row = upsert_memory(s, item.kind, item.key, item.value, item.weight, exp_dt)
        return {
            "id": row.id,
            "kind": row.kind,
            "key": row.key,
            "value": row.value,
            "weight": row.weight,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "updated_at": row.updated_at.isoformat(),
        }


# --------------------
# LLM Summarization
# --------------------

class SummarizeIn(BaseModel):
    ids: List[int] = Field(default_factory=list)
    model: Optional[str] = None


class AnalysisOut(BaseModel):
    version: int = 2
    lang: str = "en"
    bullets: List[str] = Field(default_factory=list)
    key_actions: List[str] = Field(default_factory=list)
    urgency: int = 0
    importance: int = 0
    priority: int = 0
    labels: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    truncated: bool = False
    model: str = "deepseek-r1:32b"
    token_usage: Dict[str, int] = Field(default_factory=lambda: {"prompt": 0, "completion": 0})
    notes: Optional[str] = ""


def _hash_text(txt: str) -> str:
    return hashlib.sha256(txt.encode("utf-8", "ignore")).hexdigest()


def _normalize_body(subject: str, from_name: str, from_email: str, date: Optional[str], body: str) -> str:
    parts = [
        f"Subject: {subject or ''}",
        f"From: {from_name or ''} <{from_email or ''}>",
        f"Date: {date or ''}",
        "",
        body or "",
    ]
    return "\n".join(parts).strip()


@app.post("/api/llm/summarize")
async def api_llm_summarize(payload: SummarizeIn):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty list")

    results = []
    model = payload.model or getattr(settings, "llm_model_summary", "deepseek-r1:32b")

    async def summarize_one(mid: int) -> Dict[str, Any]:
        # 1) Load and MATERIALIZE inside the session
        with session_scope() as s:
            msg = s.get(Message, mid)
            if not msg:
                return {"id": mid, "status": "not_found"}

            # Gather body text
            body_text = get_message_body(s, mid) or (msg.body_preview or "")
            msg_data = {
                "subject": msg.subject or "",
                "from_name": msg.from_name or (msg.from_raw or ""),
                "from_email": msg.from_email or "",
                "date": msg.date_iso or "",
            }

            # Build normalized text for hashing & truncation
            text_for_hash = _normalize_body(
                msg_data["subject"], msg_data["from_name"], msg_data["from_email"], msg_data["date"], body_text
            )

            truncated = False
            max_chars = int(getattr(settings, "llm_max_chars", 20000))
            clipped_text = text_for_hash
            if len(clipped_text) > max_chars:
                clipped_text = clipped_text[:max_chars]
                truncated = True

            current_hash = _hash_text(clipped_text)
            existing = get_analysis(s, mid)

            # Decide whether to skip:
            # Skip ONLY if we have the same hash AND a non-empty summary_json AND no last_error.
            if existing and existing.body_hash == current_hash:
                try:
                    parsed = json.loads(existing.summary_json or "{}")
                except Exception:
                    parsed = {}
                has_nonempty = isinstance(parsed, dict) and len(parsed.keys()) > 0
                if has_nonempty and not existing.last_error:
                    return {"id": mid, "status": "ok", "analysis": parsed, "skipped": True}
                # otherwise: fall through and re-run the model

            # Compose allowed labels and memory block while session is open
            allowed = compose_allowed_labels(s)
            mem_items = list_memory(s)
            mem_block = compose_memory_block(
                [{"kind": m.kind, "key": m.key, "value": m.value} for m in mem_items],
                max_chars=3000,
            )

        # 2) Call LLM OUTSIDE the session using only primitives
        system = SYSTEM_SUMMARY_PROMPT
        user = build_summary_user_prompt(
            allowed_labels=allowed,
            memory_block=mem_block,
            subject=msg_data["subject"],
            from_name=msg_data["from_name"],
            from_email=msg_data["from_email"],
            date=msg_data["date"],
            body_text=body_text if not truncated else body_text[:max_chars],
            truncated=truncated,
        )

        logger.info(f"[LLM] summarize message_id={mid} model={model}")
        obj, usage, err = await chat_json(system, user, model=model)
        if err or obj is None:
            logger.error(f"[LLM] error message_id={mid}: {err}")
            with session_scope() as s:
                upsert_analysis(s, mid, current_hash, json.dumps({}), error=err or "unknown error")
            return {"id": mid, "status": "error", "error": err}

        # 3) Coerce & validate; store; apply labels
        out = AnalysisOut(**{
            "version": int(obj.get("version", 2) or 2),
            "lang": obj.get("lang", "en") or "en",
            "bullets": [b for b in (obj.get("bullets") or [])][:3],
            "key_actions": [a for a in (obj.get("key_actions") or [])][:3],
            "urgency": int(obj.get("urgency", 0) or 0),
            "importance": int(obj.get("importance", 0) or 0),
            "priority": 0,  # derived elsewhere if needed
            "labels": [l for l in (obj.get("labels") or [])][:3],
            "confidence": float(obj.get("confidence", 0.0) or 0.0),
            "truncated": bool(obj.get("truncated", truncated)),
            "model": model,
            "token_usage": {"prompt": int(usage.get("prompt", 0)), "completion": int(usage.get("completion", 0))},
            "notes": obj.get("notes", "") or "",
        })

        with session_scope() as s:
            upsert_analysis(s, mid, current_hash, json.dumps(out.dict()), error=None)
            apply_labels(s, mid, out.labels)

        logger.info(f"[LLM] ok message_id={mid} prompt_tokens={out.token_usage.get('prompt',0)} "
                    f"completion_tokens={out.token_usage.get('completion',0)}")
        return {"id": mid, "status": "ok", "analysis": out.dict()}

    # Process sequentially
    ok = skipped = errors = 0
    for mid in payload.ids:
        res = await summarize_one(mid)
        status = res.get("status")
        if status == "ok" and res.get("skipped"):
            skipped += 1
        elif status == "ok":
            ok += 1
        else:
            errors += 1
        results.append(res)

    return {"results": results, "summary": {"ok": ok, "skipped": skipped, "errors": errors}}


@app.get("/api/messages/{message_id}/analysis")
async def api_get_analysis(message_id: int):
    with session_scope() as s:
        row = get_analysis(s, message_id)
        if not row or not row.summary_json:
            raise HTTPException(status_code=404, detail="Analysis not found")
        try:
            data = json.loads(row.summary_json)
        except Exception:
            data = {}
        labs = labels_for_message(s, message_id)
        err = row.last_error or None
    return {"message_id": message_id, "analysis": data, "labels": labs, "error": err}


# Small inspect helper to see stored error/hash
@app.get("/api/llm/inspect/{message_id}")
async def api_llm_inspect(message_id: int):
    with session_scope() as s:
        row = get_analysis(s, message_id)
        if not row:
            raise HTTPException(status_code=404, detail="No analysis row")
        return {
            "message_id": message_id,
            "has_summary": bool(row.summary_json),
            "last_error": row.last_error,
            "body_hash": row.body_hash,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


# --------------------
# Backlog view
# --------------------

@app.get("/api/backlog")
async def api_backlog(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1000),
    min_priority: int = Query(0, ge=0, le=100),
    only_unread: bool = Query(False),
):
    with session_scope() as s:
        rows = get_backlog(s, limit=limit, offset=offset, min_priority=min_priority, only_unread=only_unread)
        items = []
        for msg, an, pr in rows:
            items.append({
                "id": msg.id,
                "mailbox": msg.mailbox,
                "uid": msg.uid,
                "message_id": msg.message_id,
                "subject": msg.subject,
                "from": msg.from_raw,
                "from_name": msg.from_name,
                "from_email": msg.from_email,
                "date": msg.date_iso,
                "snippet": msg.snippet,
                "body_preview": msg.body_preview,
                "is_unread": bool(msg.is_unread),
                "is_answered": bool(msg.is_answered),
                "is_flagged": bool(msg.is_flagged),
                "in_reply_to": msg.in_reply_to,
                "references": msg.references_raw,
                "priority": pr,
                "has_analysis": bool(an and an.summary_json),
            })
        return {"items": items}


# --------------------
# LLM ping
# --------------------

@app.get("/api/llm/ping")
async def api_llm_ping():
    ok, models, err = await ping_models()
    return {"ok": ok, "models": models, "error": err}

