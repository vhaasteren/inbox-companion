from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import json
import imaplib
import ssl
import os
import logging

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

log = logging.getLogger(__name__)


@dataclass
class AccountConfig:
    id: str
    provider: str  # 'protonbridge' | 'yahoo' | 'ox' | 'gmail' | 'generic'
    imap: Dict[str, Any]
    mailboxes: Optional[List[str]] = None

    def mailbox_names(self) -> List[str]:
        return self.mailboxes or ["INBOX"]


def _read_text(p: str) -> str:
    return Path(p).read_text(encoding="utf-8")


def _load_accounts_from_path(path: str) -> List[AccountConfig]:
    text = _read_text(path)
    data: Dict[str, Any]
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    out: List[AccountConfig] = []
    for a in (data.get("accounts") or []):
        out.append(
            AccountConfig(
                id=a["id"],
                provider=a.get("provider", "generic"),
                imap=a.get("imap", {}),
                mailboxes=a.get("mailboxes"),
            )
        )
    return out


def iter_accounts_from_settings(settings) -> List[AccountConfig]:
    """
    Priority:
      1) ACCOUNTS_JSON (env)
      2) ACCOUNTS_CONFIG (YAML or JSON file)
      3) Legacy single-account IMAP_* env
    """
    js = os.getenv("ACCOUNTS_JSON")
    if js:
        data = json.loads(js)
        return [
            AccountConfig(
                id=a["id"],
                provider=a.get("provider", "generic"),
                imap=a.get("imap", {}),
                mailboxes=a.get("mailboxes"),
            )
            for a in (data.get("accounts") or [])
        ]

    p = getattr(settings, "accounts_config", None) or os.getenv("ACCOUNTS_CONFIG")
    if p and Path(p).exists():
        return _load_accounts_from_path(p)

    # legacy fallback
    use_ssl = False
    use_starttls = getattr(settings, "imap_use_starttls", True)
    acct = AccountConfig(
        id="default",
        provider=os.getenv("IMAP_PROVIDER", "protonbridge"),
        imap={
            "host": getattr(settings, "imap_host", "127.0.0.1"),
            "port": int(getattr(settings, "imap_port", 1143)),
            "use_ssl": use_ssl,
            "use_starttls": use_starttls,
            "tls_verify": getattr(settings, "imap_tls_verify", True),
            "username": getattr(settings, "imap_user", ""),
            "password": getattr(settings, "imap_pass", ""),
        },
        mailboxes=getattr(settings, "imap_mailboxes", ["INBOX"]),
    )
    return [acct]


def open_imap_connection(acct: AccountConfig, mailbox: str) -> imaplib.IMAP4:
    """Open & SELECT a mailbox with SSL or STARTTLS; tls_verify can be disabled (local bridges)."""

    # Warnings
    if acct.imap.get("use_ssl") and int(acct.imap.get("port", 0)) == 143:
        log.warning("[%s] use_ssl=true with port 143 usually means STARTTLS. Set use_ssl=false, use_starttls=true, or switch to port 993.", acct.id)
    if acct.imap.get("use_starttls") and int(acct.imap.get("port", 0)) == 993:
        log.warning("[%s] use_starttls=true on 993 is unusual; IMAPS typically uses SSL without STARTTLS.", acct.id)

    host = acct.imap.get("host") or "127.0.0.1"
    port = int(acct.imap.get("port") or 993)
    use_ssl = bool(acct.imap.get("use_ssl", port == 993))
    use_starttls = bool(acct.imap.get("use_starttls", not use_ssl))
    tls_verify = bool(acct.imap.get("tls_verify", True))
    username = acct.imap.get("username") or ""
    password = acct.imap.get("password") or ""

    if use_ssl:
        ctx = ssl.create_default_context()
        if not tls_verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)  # type: ignore
    else:
        client = imaplib.IMAP4(host, port)
        if use_starttls:
            ctx = ssl.create_default_context()
            if not tls_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            client.starttls(ssl_context=ctx)

    client.login(username, password)
    typ, _ = client.select(mailbox, readonly=True)
    if typ != "OK":
        try:
            client.logout()
        finally:
            pass
        raise RuntimeError(f"[{acct.id}] Cannot select mailbox: {mailbox}")
    return client
