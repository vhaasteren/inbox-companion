from __future__ import annotations
import imaplib
import email
import hashlib
import re
import ssl
from email.header import decode_header
from email.utils import parseaddr

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


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<.*?>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_plain_text(msg: email.message.Message) -> str:
    """
    Prefer 'text/plain' parts (no attachments). Fallback to stripped 'text/html'.
    Concatenate multiple text/plain parts.
    """
    texts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True) or b""
                    texts.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
                except Exception:
                    continue

    if texts:
        return "\n\n".join(t.strip() for t in texts if t.strip())

    # Single-part plain text
    if msg.get_content_type() == "text/plain":
        try:
            return (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "replace")
        except Exception:
            pass

    # Fallback: HTML
    html = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/html":
                try:
                    html = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
                    break
                except Exception:
                    continue
    elif msg.get_content_type() == "text/html":
        try:
            html = (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "replace")
        except Exception:
            pass

    return _strip_html(html or "")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _flags_from_resp(flags_tuple: tuple[str, ...]) -> tuple[int, int, int]:
    """
    Map IMAP flags to (is_unread, is_answered, is_flagged) as 1/0.
    """
    flags_str = " ".join(flags_tuple).upper()
    seen = "\\SEEN" in flags_str
    answered = "\\ANSWERED" in flags_str
    flagged = "\\FLAGGED" in flags_str
    return (0 if seen else 1, 1 if answered else 0, 1 if flagged else 0)


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
        # FLAGS via separate UID FETCH for robustness
        tf, fl = client.uid("FETCH", uid, "(FLAGS)")
        flags = ()
        if tf == "OK" and fl and isinstance(fl[0], tuple) and isinstance(fl[0][1], (bytes, bytearray)):
            flag_text = fl[0][1].decode("utf-8", "ignore")
            flags = tuple(re.findall(r"\\[A-Za-z]+", flag_text))
        is_unread, is_answered, is_flagged = _flags_from_resp(flags)

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        subject = _decode_mime_words(msg.get("Subject")) or "(no subject)"
        sender_raw = _decode_mime_words(msg.get("From")) or "(unknown)"
        name_decoded = _decode_mime_words(msg.get("From"))
        name, addr = parseaddr(name_decoded or "")
        date_raw = msg.get("Date")
        try:
            dt = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
            date_iso = dt.astimezone().isoformat() if dt else None
        except Exception:
            date_iso = None

        items.append({
            "uid": int(uid),
            "from": sender_raw,
            "from_name": name or None,
            "from_email": addr or None,
            "subject": subject,
            "date": date_iso,
            "is_unread": is_unread,
            "is_answered": is_answered,
            "is_flagged": is_flagged,
        })

    client.logout()
    return {"mailbox": mailbox, "count": len(items), "items": items}


# --- Importer helpers (used by the poller) ---

def fetch_uids_since(client: imaplib.IMAP4, last_uid: int, since_str: str | None, only_unseen: bool) -> list[bytes]:
    """
    Return list of UIDs to fetch.
    On first run (last_uid<=0): search by (SINCE <date>) and optionally UNSEEN.
    Otherwise: search by UIDs greater than last_uid and optionally UNSEEN.
    """
    if last_uid <= 0:
        # Build criteria
        crit = []
        if only_unseen:
            crit.append("UNSEEN")
        if since_str:
            crit += ["SINCE", since_str]
        typ, data = client.search(None, *crit) if crit else client.search(None, "ALL")
        if typ != "OK" or not data:
            return []
        return data[0].split()

    # Subsequent runs: restrict by UID range
    if only_unseen:
        typ, data = client.uid("SEARCH", None, f"UID {last_uid + 1}:*", "UNSEEN")
    else:
        typ, data = client.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def fetch_message_by_uid(client: imaplib.IMAP4, mailbox: str, uid: bytes) -> tuple[dict, int]:
    """
    Fetch and parse one message by UID, return a dict for DB upsert and the numeric uid.
    Skips attachments for body content.
    """
    # Get RFC822 + FLAGS robustly (two calls for compatibility)
    t, msg_data = client.uid("FETCH", uid, "(RFC822)")
    if t != "OK" or not msg_data or msg_data[0] is None:
        raise RuntimeError("UID FETCH RFC822 failed")

    tf, fl = client.uid("FETCH", uid, "(FLAGS)")
    flags = ()
    if tf == "OK" and fl and isinstance(fl[0], tuple) and isinstance(fl[0][1], (bytes, bytearray)):
        flag_text = fl[0][1].decode("utf-8", "ignore")
        flags = tuple(re.findall(r"\\[A-Za-z]+", flag_text))
    is_unread, is_answered, is_flagged = _flags_from_resp(flags)

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    subject = _decode_mime_words(msg.get("Subject")) or "(no subject)"
    sender_raw = _decode_mime_words(msg.get("From")) or "(unknown)"
    name_decoded = _decode_mime_words(msg.get("From"))
    name, addr = parseaddr(name_decoded or "")
    message_id = msg.get("Message-ID")
    in_reply_to = msg.get("In-Reply-To")
    references_raw = msg.get("References")

    date_raw = msg.get("Date")
    try:
        dt = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
        date_iso = dt.astimezone().isoformat() if dt else None
    except Exception:
        date_iso = None

    plain = _clean_plain_text(msg).strip()
    snippet = (plain[:250] + "…") if len(plain) > 250 else plain
    body_preview = plain[:2048] if plain else None

    return {
        "mailbox": mailbox,
        "uid": int(uid),
        "message_id": message_id,
        "subject": subject,
        "from_raw": sender_raw,
        "from_name": name or None,
        "from_email": addr or None,
        "date_iso": date_iso,
        "snippet": snippet,
        "body_preview": body_preview,
        "body_full": plain,  # stored in separate table
        "in_reply_to": in_reply_to,
        "references_raw": references_raw,
        "is_unread": 1 if is_unread else 0,
        "is_answered": 1 if is_answered else 0,
        "is_flagged": 1 if is_flagged else 0,
        "body_hash": _sha256(raw),
    }, int(uid)

