from __future__ import annotations
import imaplib
import email
import hashlib
import re
import ssl
from email.header import decode_header

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


def _clean_plain_text(msg: email.message.Message) -> str:
    """
    Extract a light plain-text representation: prefer 'text/plain',
    fallback to stripped 'text/html'.
    """
    # Prefer text/plain
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue

    # Fallback: text/plain (single part)
    if msg.get_content_type() == "text/plain":
        try:
            return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
        except Exception:
            pass

    # Fallback: text/html → strip tags minimally
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    return _strip_html(html)
                except Exception:
                    continue
    elif msg.get_content_type() == "text/html":
        try:
            html = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
            return _strip_html(html)
        except Exception:
            pass

    # Last resort: empty
    return ""


def _strip_html(html: str) -> str:
    # extremely light stripping (no bs4 to keep deps minimal in this module)
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", "", html)
    text = re.sub(r"(?is)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<.*?>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preview(limit: int = 10) -> dict:
    """Live IMAP preview for sanity checks (bypasses DB)."""
    host, port = settings.imap_host, settings.imap_port
    mailbox = settings.imap_mailbox

    client = imaplib.IMAP4(host, port)
    if settings.imap_use_starttls:
        context = ssl.create_default_context()
        if not settings.imap_tls_verify:
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


# --- Importer helpers (used by the poller) ---

def fetch_uids_since(client: imaplib.IMAP4, last_uid: int, initial_limit: int | None = None) -> list[bytes]:
    """
    Return a list of UIDs to fetch. If last_uid == 0, backfill with last N (initial_limit).
    """
    if last_uid <= 0 and initial_limit:
        typ, data = client.search(None, "ALL")
        if typ != "OK":
            return []
        all_ids = data[0].split()
        return all_ids[-initial_limit:]
    else:
        typ, data = client.uid("SEARCH", None, f"UID {last_uid + 1}:*")
        if typ != "OK" or not data or not data[0]:
            return []
        return data[0].split()


def fetch_message_by_uid(client: imaplib.IMAP4, uid: bytes) -> tuple[dict, int]:
    """
    Fetch and parse one message by UID, return a dict for DB insert and the numeric uid.
    """
    t, msg_data = client.uid("FETCH", uid, "(RFC822)")
    if t != "OK" or not msg_data or msg_data[0] is None:
        raise RuntimeError("UID FETCH failed")

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    subject = _decode_mime_words(msg.get("Subject")) or "(no subject)"
    sender = _decode_mime_words(msg.get("From")) or "(unknown)"
    message_id = msg.get("Message-ID")
    date_raw = msg.get("Date")
    try:
        dt = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
        date_iso = dt.astimezone().isoformat() if dt else None
    except Exception:
        date_iso = None

    plain = _clean_plain_text(msg).strip()
    snippet = (plain[:250] + "…") if len(plain) > 250 else plain

    return {
        "mailbox": settings.imap_mailbox,
        "uid": int(uid),
        "message_id": message_id,
        "subject": subject,
        "from_raw": sender,
        "date_iso": date_iso,
        "snippet": snippet,
        "body_hash": _sha256(raw),
    }, int(uid)

