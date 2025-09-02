from __future__ import annotations
import os
from pydantic import BaseModel

class Settings(BaseModel):
    imap_host: str = os.getenv("IMAP_HOST", "127.0.0.1")
    imap_port: int = int(os.getenv("IMAP_PORT", "1143"))
    imap_user: str = os.getenv("IMAP_USER", "")
    imap_pass: str = os.getenv("IMAP_PASS", "")
    imap_mailbox: str = os.getenv("IMAP_MAILBOX", "INBOX")
    imap_use_starttls: bool = os.getenv("IMAP_USE_STARTTLS", "true").lower() == "true"
    imap_tls_verify: bool = os.getenv("IMAP_TLS_VERIFY", "true").lower() == "true"

    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

settings = Settings()

