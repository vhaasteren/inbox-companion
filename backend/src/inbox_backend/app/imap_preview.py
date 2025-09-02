from __future__ import annotations
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import ssl
from .config import settings


def _decode_mime_words(s: str | None) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for val, enc in parts:
        if isinstance(val, bytes):
            try:
                out.append(val.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(val.decode("utf-8", errors="replace"))
        else:
            out.append(str(val))
    return "".join(out)


def preview(limit: int = 10) -> dict:
    host, port = settings.imap_host, settings.imap_port
    mailbox = settings.imap_mailbox

    client = imaplib.IMAP4(host, port)
    #if settings.imap_use_starttls:
    #    context = ssl.create_default_context()
    #    client.starttls(ssl_context=context)
    if settings.imap_use_starttls:
        context = ssl.create_default_context()
        if not settings.imap_tls_verify:
            # Dev-only: accept self-signed (no hostname/CAs). ⚠️ Do NOT use in prod.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        client.starttls(ssl_context=context)

    client.login(settings.imap_user, settings.imap_pass)
    typ, _ = client.select(mailbox, readonly=True)
    if typ != "OK":
        raise RuntimeError(f"Cannot select mailbox: {mailbox}")

    typ, data = client.search(None, "ALL")
    if typ != "OK":
        raise RuntimeError("IMAP SEARCH failed")

    ids = data[0].split()
    items = []
    for uid in ids[-limit:]:
        t, msg_data = client.fetch(uid, "(RFC822)")
        if t != "OK":
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        subject = _decode_mime_words(msg.get("Subject")) or "(no subject)"
        sender = _decode_mime_words(msg.get("From")) or "(unknown)"
        date_raw = msg.get("Date")
        try:
            # Best-effort parse via email.utils.parsedate_to_datetime
            dt = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
            date_iso = dt.astimezone().isoformat() if dt else None
        except Exception:
            date_iso = None

        items.append({
            "uid": int(uid),
            "from": sender,
            "subject": subject,
            "date": date_iso,
        })

    client.logout()
    return {"mailbox": mailbox, "count": len(items), "items": items}

