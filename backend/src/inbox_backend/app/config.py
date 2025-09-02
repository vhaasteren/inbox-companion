from __future__ import annotations
import os
from pydantic import BaseModel


class Settings(BaseModel):
    # IMAP / Proton Bridge
    imap_host: str = os.getenv("IMAP_HOST", "127.0.0.1")
    imap_port: int = int(os.getenv("IMAP_PORT", "1143"))
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_pass: str = os.getenv("IMAP_PASS", "")

    # Single mailbox compatibility (fallback)
    imap_mailbox: str = os.getenv("IMAP_MAILBOX", "INBOX")

    # Multi-mailbox support: comma-separated list; falls back to single mailbox if unset
    imap_mailboxes: list[str] = [
        m.strip() for m in os.getenv("IMAP_MAILBOXES", "").split(",") if m.strip()
    ] or [os.getenv("IMAP_MAILBOX", "INBOX")]

    imap_use_starttls: bool = os.getenv("IMAP_USE_STARTTLS", "true").lower() == "true"
    imap_tls_verify: bool = os.getenv("IMAP_TLS_VERIFY", "true").lower() == "true"

    # DB / polling (persisted via /data bind mount in docker-compose)
    db_path: str = os.getenv("DB_PATH", "/data/inbox.sqlite3")
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    # Backfill / fetch policy
    backfill_days_max: int = int(os.getenv("BACKFILL_DAYS_MAX", "200"))  # initial backfill time window
    only_unseen: bool = os.getenv("ONLY_UNSEEN", "true").lower() == "true"

    # How many recent stored messages (per mailbox) to re-sync FLAGS each cycle
    flag_sync_recent: int = int(os.getenv("FLAG_SYNC_RECENT", "300"))

    # Server / CORS / LLM
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

    # System prompt
    system_prompt_summary_path: str = "/state/system_prompt_summary.txt"


settings = Settings()

