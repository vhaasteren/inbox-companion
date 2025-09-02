from __future__ import annotations
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .imap_preview import preview as imap_preview

app = FastAPI(title="Inbox Companion API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/api/mail/preview")
async def api_mail_preview(limit: int = Query(10, ge=1, le=50)):
    return imap_preview(limit=limit)

