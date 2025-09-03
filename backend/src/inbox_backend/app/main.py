from __future__ import annotations
from typing import Optional, List, Dict, Any
import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
import uuid

from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from sqlalchemy import text, select, func

from .config import settings
from .imap_preview import preview as imap_preview
from .db import session_scope, engine
from .models import Message, MessageAnalysis, Label, MemoryItem
from .repository import (
    get_recent_messages, search_messages, get_message_body,
    list_labels, upsert_label, labels_for_message,
    get_backlog, get_analysis, upsert_analysis, apply_labels,
    list_memory, upsert_memory, compose_allowed_labels,
    find_message_ids_missing_analysis,
)
from .poller import start_scheduler, poll_once, backfill_since_days, backfill_since_days_acct
from .llm_client import chat_json, get_system_summary_prompt, build_summary_user_prompt, compose_memory_block, ping_models
from .providers import iter_accounts_from_settings

app = FastAPI(title="Inbox Companion API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "cors_origins", ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_scheduler = None

def _has_meaningful_summary(row: MessageAnalysis) -> bool:
    """True only when there is a usable, non-empty summary and no last_error."""
    if not row:
        return False
    if getattr(row, "last_error", None):  # any recorded error means not meaningful
        return False
    s = (row.summary_json or "").strip()
    if not s or s in ("{}", "[]", "null"):
        return False
    try:
        obj = json.loads(s)
    except Exception:
        return False
    if not isinstance(obj, dict):
        return False

    has_content = bool(obj.get("bullets")) or bool(obj.get("key_actions")) \
        or int(obj.get("importance") or 0) or int(obj.get("urgency") or 0) \
        or int(obj.get("priority") or 0) or bool(obj.get("labels"))
    return has_content


def _export_message_fields(msg: Message) -> dict:
    """Copy only the fields we need so we don't touch a detached instance later."""
    return {
        "subject": msg.subject or "",
        "from_name": (msg.from_name or "") or (msg.from_raw or ""),
        "from_email": msg.from_email or "",
        "date_iso": msg.date_iso or "",
        "from_raw": msg.from_raw or "",
        "body_preview": msg.body_preview or "",
    }

# --------------------
# State dir / user-info prompt
# --------------------

def _state_dir() -> Path:
    sd = getattr(settings, "state_dir", None) or Path("/state")
    return Path(sd)

def _read_user_info_prompt() -> str:
    """
    If /state/user_info.txt exists (or STATE_DIR/user_info.txt), read and return.
    This is prepended to the LLM system prompt.
    """
    try:
        p = _state_dir() / "user_info.txt"
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


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
    mailbox: Optional[str] = None
    days: int
    only_unseen: bool = True
    limit: Optional[int] = None


@app.post("/api/backfill")
async def api_backfill(req: BackfillRequest):
    summaries = []
    accounts = iter_accounts_from_settings(settings)
    if req.mailbox:
        # Accept composite form "acct:INBOX"; otherwise run this mailbox on all accounts
        if ":" in req.mailbox:
            acct_id, mb = req.mailbox.split(":", 1)
            for acct in accounts:
                if acct.id == acct_id:
                    try:
                        summaries.append(
                            backfill_since_days_acct(acct, mb, days=req.days, only_unseen=req.only_unseen, limit=req.limit)
                        )
                    except Exception as e:
                        summaries.append({"account_id": acct.id, "mailbox": mb, "fetched": 0, "inserted": 0, "error": str(e)})

                    break
            if not summaries:
                raise HTTPException(status_code=400, detail=f"Unknown account in mailbox: {acct_id}")
        else:
            for acct in accounts:
                try:
                    summaries.append(
                        backfill_since_days_acct(acct, req.mailbox, days=req.days, only_unseen=req.only_unseen, limit=req.limit)
                    )
                except Exception as e:
                    summaries.append({"account_id": acct.id, "mailbox": mb, "fetched": 0, "inserted": 0, "error": str(e)})
    else:
        for acct in accounts:
            for mb in acct.mailbox_names():
                try:
                    summaries.append(
                        backfill_since_days_acct(acct, mb, days=req.days, only_unseen=req.only_unseen, limit=req.limit)
                    )
                except Exception as e:
                    summaries.append({"account_id": acct.id, "mailbox": mb, "fetched": 0, "inserted": 0, "error": str(e)})
    total_inserted = sum(s.get("inserted", 0) for s in summaries)
    total_fetched = sum(s.get("fetched", 0) for s in summaries)
    return {"total_fetched": total_fetched, "total_inserted": total_inserted, "mailboxes": summaries}


@app.post("/api/refresh")
async def api_refresh_now():
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
    expires_at: Optional[str] = None

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
    force: bool = False


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
    model: str = "deepseek-r1:8b"
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


def _compose_system_prompt_with_user_info() -> str:
    """
    Prepend user-specific info from /state/user_info.txt (if present) to the system prompt.
    """
    user_info = _read_user_info_prompt().strip()
    if not user_info:
        return get_system_summary_prompt()
    return f"{user_info}\n\n{get_system_summary_prompt()}"


async def summarize_one_id(mid: int, model: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    # ------- Load things inside session -------
    with session_scope() as s:
        msg = s.get(Message, mid)
        if not msg:
            return {"id": mid, "status": "not_found"}

        export = _export_message_fields(msg)
        body = get_message_body(s, mid) or export["body_preview"] or ""

        # Build normalized text for hashing/clip
        text = _normalize_body(
            export["subject"],
            export["from_name"],
            export["from_email"],
            export["date_iso"],
            body,
        )
        truncated = False
        max_chars = int(getattr(settings, "llm_max_chars", 20000))
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True

        current_hash = _hash_text(text)
        existing = get_analysis(s, mid)

        # Only skip when: same hash, NOT forced, and existing is meaningful
        if existing and existing.body_hash == current_hash and not force and _has_meaningful_summary(existing):
            try:
                data = json.loads(existing.summary_json)
                return {"id": mid, "status": "ok", "analysis": data, "skipped": True}
            except Exception:
                # fallthrough to regenerate if stored JSON is corrupted
                pass

        allowed = compose_allowed_labels(s)
        mem_items = list_memory(s)
        mem_block = compose_memory_block(
            [{"kind": m.kind, "key": m.key, "value": m.value} for m in mem_items], max_chars=3000
        )

    # ------- Outside session (no ORM access) -------
    system = _compose_system_prompt_with_user_info()
    user = build_summary_user_prompt(
        allowed_labels=allowed,
        memory_block=mem_block,
        subject=export["subject"],
        from_name=export["from_name"],
        from_email=export["from_email"],
        date=export["date_iso"],
        body_text=body if not truncated else body[:max_chars],
        truncated=truncated,
    )

    obj, usage, err = await chat_json(system, user, model=model)
    if err or obj is None:
        # Persist a row with last_error so we don't silently succeed
        with session_scope() as s:
            upsert_analysis(s, mid, current_hash, "", error=err or "unknown error")
        return {"id": mid, "status": "error", "error": err or "unknown error"}

    out = AnalysisOut(**{
        "version": int(obj.get("version", 2) or 2),
        "lang": obj.get("lang", "en") or "en",
        "bullets": [b for b in (obj.get("bullets") or [])][:3],
        "key_actions": [a for a in (obj.get("key_actions") or [])][:3],
        "urgency": int(obj.get("urgency", 0) or 0),
        "importance": int(obj.get("importance", 0) or 0),
        "priority": 0,
        "labels": [l for l in (obj.get("labels") or [])][:3],
        "confidence": float(obj.get("confidence", 0.0) or 0.0),
        "truncated": bool(obj.get("truncated", truncated)),
        "model": model or getattr(settings, "llm_model_summary", "deepseek-r1:8b"),
        "token_usage": {"prompt": int(usage.get("prompt", 0)), "completion": int(usage.get("completion", 0))},
        "notes": obj.get("notes", "") or "",
    })

    with session_scope() as s:
        upsert_analysis(s, mid, current_hash, json.dumps(out.dict()), error=None)
        apply_labels(s, mid, out.labels)

    return {"id": mid, "status": "ok", "analysis": out.dict()}


@app.post("/api/llm/summarize")
async def api_llm_summarize(payload: SummarizeIn):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty list")

    results = []
    ok = skipped = errors = 0

    for mid in payload.ids:
        try:
            # now pass force through
            res = await summarize_one_id(mid, model=payload.model, force=payload.force)
        except Exception as e:
            res = {"id": mid, "status": "error", "error": f"internal: {e.__class__.__name__}: {e}"}

        results.append(res)
        if res.get("status") == "ok":
            if res.get("skipped"):
                skipped += 1
            else:
                ok += 1
        elif res.get("status") == "error":
            errors += 1

    return {"results": results, "summary": {"ok": ok, "skipped": skipped, "errors": errors}}


class SummarizeAllIn(BaseModel):
    only_unread: bool = False
    limit: Optional[int] = None     # None = no limit
    mailbox: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/llm/summarize_all")
async def api_llm_summarize_all(payload: SummarizeAllIn):
    # 1) Find unsummarized message ids
    with session_scope() as s:
        stmt = (
            select(Message.id)
            .join(MessageAnalysis, MessageAnalysis.message_id == Message.id, isouter=True)
            .where(
                (MessageAnalysis.message_id == None) |
                (func.length(func.coalesce(MessageAnalysis.summary_json, "")) == 0)
            )
        )
        if payload.only_unread:
            stmt = stmt.where(Message.is_unread == 1)
        if payload.mailbox:
            stmt = stmt.where(Message.mailbox == payload.mailbox)
        stmt = stmt.order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc())
        if payload.limit is not None:
            stmt = stmt.limit(int(payload.limit))

        ids = [row[0] for row in s.execute(stmt).all()]

    # 2) Run sequentially (safe & simple)
    results = []
    for mid in ids:
        res = await summarize_one_id(mid, model=payload.model)
        results.append(res)

    ok = sum(1 for r in results if r.get("status") == "ok" and not r.get("skipped"))
    skipped = sum(1 for r in results if r.get("status") == "ok" and r.get("skipped"))
    errors = sum(1 for r in results if r.get("status") == "error")
    return {"count": len(ids), "results": results, "summary": {"ok": ok, "skipped": skipped, "errors": errors}}


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
        err = row.last_error if row else None
    return {"message_id": message_id, "analysis": data, "labels": labs, "error": err}


@app.delete("/api/messages/{message_id}/analysis")
async def api_delete_analysis(message_id: int):
    with session_scope() as s:
        row = s.query(MessageAnalysis).filter_by(message_id=message_id).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="No analysis to delete")
        s.delete(row)
        s.commit()
    return {"ok": True}


@app.get("/api/llm/inspect/{message_id}")
async def api_llm_inspect(message_id: int):
    with session_scope() as s:
        row = get_analysis(s, message_id)
    if not row:
        return {
            "message_id": message_id,
            "has_summary": False,
            "last_error": None,
            "body_hash": None,
            "updated_at": None,
        }
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


# --------------------
# Batch summarize job with progress
# --------------------

class JobStatus(BaseModel):
    job_id: str
    state: str  # queued|running|done|error
    total: int
    processed: int
    ok: int
    skipped: int
    errors: int
    last_message_id: Optional[int] = None
    last_error: Optional[str] = None
    started_at: str
    finished_at: Optional[str] = None
    recent: List[Dict[str, Any]] = Field(default_factory=list)  # up to 20 recent results


_JOBS: Dict[str, JobStatus] = {}

async def _run_summarize_missing(job: JobStatus, only_unread: bool, limit: int, batch_size: int = 10):
    job.state = "running"
    try:
        with session_scope() as s:
            ids = find_message_ids_missing_analysis(s, only_unread=only_unread, limit=limit)
        job.total = len(ids)

        # Process in batches to avoid huge payloads
        for i in range(0, len(ids), batch_size):
            chunk = ids[i : i + batch_size]
            # Call the existing in-process summarize logic
            # Build a fake payload to reuse our function
            payload = SummarizeIn(ids=chunk)
            res = await api_llm_summarize(payload)  # type: ignore
            data = res if isinstance(res, dict) else res.dict()
            results = data.get("results", [])

            for r in results:
                job.processed += 1
                job.last_message_id = r.get("id")
                if r.get("status") == "ok":
                    if r.get("skipped"):
                        job.skipped += 1
                    else:
                        job.ok += 1
                elif r.get("status") == "error":
                    job.errors += 1
                    job.last_error = r.get("error")

                job.recent.append(r)
                if len(job.recent) > 20:
                    job.recent = job.recent[-20:]

        job.state = "done"
        job.finished_at = datetime.utcnow().isoformat()
    except Exception as e:
        job.state = "error"
        job.last_error = str(e)
        job.finished_at = datetime.utcnow().isoformat()


@app.post("/api/llm/summarize_missing")
async def api_llm_summarize_missing(
    limit: int = Query(1000, ge=1, le=5000),
    only_unread: bool = Query(False),
):
    """
    Start a background job to summarize all messages that don't have a stored analysis.
    Returns a job_id for progress polling.
    """
    job_id = uuid.uuid4().hex
    job = JobStatus(
        job_id=job_id,
        state="queued",
        total=0,
        processed=0,
        ok=0,
        skipped=0,
        errors=0,
        started_at=datetime.utcnow().isoformat(),
    )
    _JOBS[job_id] = job

    asyncio.create_task(_run_summarize_missing(job, only_unread=only_unread, limit=limit))
    return {"job_id": job_id}


@app.get("/api/llm/jobs/{job_id}")
async def api_llm_job_status(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.dict()

@app.get("/api/llm/jobs")
async def api_llm_jobs_list(kind: Optional[str] = None):
    """
    Return all known jobs (optionally filtered by kind), newest first.
    Each job includes computed 'remaining' and 'pct' for convenience.
    Works whether _JOBS values are dicts or Pydantic models.
    """
    def _as_dict(obj) -> dict:
        # Normalize whatever we stored into a plain dict
        if isinstance(obj, dict):
            return dict(obj)
        # Pydantic v2
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        # Pydantic v1
        if hasattr(obj, "dict"):
            return obj.dict()
        # Fallback to attrs
        return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_") and not callable(getattr(obj, k))}

    out = []
    # Snapshot to avoid mutation while iterating
    for job_id, info in list(_JOBS.items()):
        row = _as_dict(info)

        # Optional filter by kind
        if kind and (row.get("kind") != kind):
            continue

        row["job_id"] = job_id

        total = row.get("total") or 0
        ok = int(row.get("ok") or 0)
        skipped = int(row.get("skipped") or 0)
        errors = int(row.get("errors") or 0)

        remaining = None
        if isinstance(total, int):
            remaining = max(0, total - ok - skipped - errors)

        row["remaining"] = remaining
        row["pct"] = round(((ok + skipped + errors) / total) * 100.0, 1) if isinstance(total, int) and total > 0 else None

        out.append(row)

    # Sort by created_at desc if present
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"jobs": out}
