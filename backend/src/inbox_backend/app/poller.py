from __future__ import annotations
import imaplib
import ssl
import time
from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .db import session_scope, engine, Base
from .repository import ensure_mailbox, get_last_uid, set_last_uid, upsert_messages
from .imap_preview import fetch_uids_since, fetch_message_by_uid


def _imap_connect() -> imaplib.IMAP4:
    client = imaplib.IMAP4(settings.imap_host, settings.imap_port)
    if settings.imap_use_starttls:
        context = ssl.create_default_context()
        if not settings.imap_tls_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        client.starttls(ssl_context=context)
    client.login(settings.imap_user, settings.imap_pass)
    typ, _ = client.select(settings.imap_mailbox, readonly=True)
    if typ != "OK":
        raise RuntimeError(f"Cannot select mailbox: {settings.imap_mailbox}")
    return client


def poll_once() -> dict:
    """
    One polling cycle:
      - determine last_uid from DB
      - fetch new UIDs
      - fetch each message and insert if new
      - update last_uid
    """
    with session_scope() as s:
        ensure_mailbox(s, settings.imap_mailbox)
        last_uid = get_last_uid(s, settings.imap_mailbox)

    client = _imap_connect()
    try:
        uids = fetch_uids_since(client, last_uid, initial_limit=settings.initial_fetch_limit)
        inserted = 0
        max_uid_seen = last_uid

        for uid in uids:
            try:
                row, uid_int = fetch_message_by_uid(client, uid)
                max_uid_seen = max(max_uid_seen, uid_int)
                with session_scope() as s:
                    inserted += upsert_messages(s, [row])
            except Exception:
                # Keep polling resilient; skip problematic message
                continue

        # Update last_uid after batch
        with session_scope() as s:
            set_last_uid(s, settings.imap_mailbox, max_uid_seen)

        return {"fetched": len(uids), "inserted": inserted, "last_uid": max_uid_seen}
    finally:
        client.logout()


def start_scheduler() -> BackgroundScheduler:
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    scheduler = BackgroundScheduler(daemon=True)
    # Initial immediate run to populate quickly
    scheduler.add_job(poll_once, "date", run_date=None)
    # Then recurring
    scheduler.add_job(poll_once, "interval", seconds=settings.poll_interval_seconds, id="poller", replace_existing=True)
    scheduler.start()
    return scheduler

