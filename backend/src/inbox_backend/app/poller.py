from __future__ import annotations
import imaplib
import re
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .db import session_scope, engine, Base, migrate_schema
from .repository import (
    ensure_mailbox, get_last_uid, set_last_uid, upsert_messages,
    get_recent_uids, update_flags_for_uids
)
from .imap_preview import fetch_uids_since, fetch_message_by_uid
from .providers import AccountConfig, iter_accounts_from_settings, open_imap_connection


def _imap_date_str(days_ago: int) -> str:
    d = datetime.utcnow().date() - timedelta(days=days_ago)
    return d.strftime("%d-%b-%Y")  # IMAP format, e.g., 20-Aug-2025


def _compose_box_name(acct: AccountConfig, mailbox: str) -> str:
    # Unique across accounts without DB schema changes
    return f"{acct.id}:{mailbox}"


def poll_account_mailbox(acct: AccountConfig, mailbox: str) -> dict:
    """
    Standard polling cycle (respects last_uid and default backfill policy) for one account/mailbox.
    """
    box_key = _compose_box_name(acct, mailbox)
    with session_scope() as s:
        ensure_mailbox(s, box_key)
        last_uid = get_last_uid(s, box_key)

    client = open_imap_connection(acct, mailbox)
    try:
        since_str = _imap_date_str(settings.backfill_days_max) if last_uid <= 0 else None
        uids = fetch_uids_since(
            client,
            last_uid=last_uid,
            since_str=since_str,
            only_unseen=settings.only_unseen
        )

        inserted = 0
        max_uid_seen = last_uid

        for uid in uids:
            try:
                row, uid_int = fetch_message_by_uid(client, box_key, uid)
                max_uid_seen = max(max_uid_seen, uid_int)
                with session_scope() as s:
                    inserted += upsert_messages(s, [row])
            except Exception:
                continue

        # Sync FLAGS for recent stored messages to capture read/star changes
        recent_limit = max(0, int(settings.flag_sync_recent))
        if recent_limit > 0:
            with session_scope() as s:
                recent_uids = get_recent_uids(s, box_key, limit=recent_limit)
            flag_map: dict[int, tuple[int, int, int]] = {}
            CHUNK = 200
            for i in range(0, len(recent_uids), CHUNK):
                chunk = recent_uids[i:i + CHUNK]
                if not chunk:
                    continue
                uid_list = ",".join(str(u) for u in chunk)
                tf, fl = client.uid("FETCH", uid_list, "(FLAGS)")
                if tf != "OK" or not fl:
                    continue
                for item in fl:
                    if not isinstance(item, tuple) or not isinstance(item[1], (bytes, bytearray)):
                        continue
                    text = item[1].decode("utf-8", "ignore")
                    try:
                        m_uid = int(text.split()[0])
                    except Exception:
                        continue
                    flags = tuple(re.findall(r"\\[A-Za-z]+", text))
                    flags_upper = " ".join(flags).upper()
                    seen = "\\SEEN" in flags_upper
                    answered = "\\ANSWERED" in flags_upper
                    flagged = "\\FLAGGED" in flags_upper
                    flag_map[m_uid] = (0 if seen else 1, 1 if answered else 0, 1 if flagged else 0)
            if flag_map:
                with session_scope() as s:
                    update_flags_for_uids(s, box_key, flag_map)

        with session_scope() as s:
            set_last_uid(s, box_key, max_uid_seen)

        return {
            "account_id": acct.id,
            "mailbox": mailbox,
            "box_key": box_key,
            "fetched": len(uids),
            "inserted": inserted,
            "last_uid": max_uid_seen,
        }
    finally:
        client.logout()


def poll_once() -> dict:
    """
    Poll all configured accounts & their mailboxes (standard policy).
    """
    summary = {"total_fetched": 0, "total_inserted": 0, "mailboxes": []}
    accounts = iter_accounts_from_settings(settings)
    for acct in accounts:
        for mb in acct.mailbox_names():
            try:
                res = poll_account_mailbox(acct, mb)
                summary["total_fetched"] += res["fetched"]
                summary["total_inserted"] += res["inserted"]
                summary["mailboxes"].append(res)
            except Exception:
                continue
    return summary


def backfill_since_days_acct(acct: AccountConfig, mailbox: str, days: int, only_unseen: bool = True, limit: int | None = None) -> dict:
    """
    Historical backfill for a specific account/mailbox (ignores last_uid; uses SINCE <N days>).
    Inserts only messages not yet in DB (idempotent).
    """
    box_key = _compose_box_name(acct, mailbox)
    client = open_imap_connection(acct, mailbox)
    try:
        crit = []
        if only_unseen:
            crit.append("UNSEEN")
        crit += ["SINCE", _imap_date_str(days)]
        typ, data = client.search(None, *crit)
        if typ != "OK" or not data:
            return {"account_id": acct.id, "mailbox": mailbox, "fetched": 0, "inserted": 0, "note": "search returned no data"}

        uids = data[0].split()
        if limit is not None and limit >= 0:
            uids = uids[:limit]

        inserted = 0
        for uid in uids:
            try:
                row, _ = fetch_message_by_uid(client, box_key, uid)
                with session_scope() as s:
                    inserted += upsert_messages(s, [row])
            except Exception:
                continue

        return {"account_id": acct.id, "mailbox": mailbox, "fetched": len(uids), "inserted": inserted}
    finally:
        client.logout()


# Backward-compat single-account wrapper
def backfill_since_days(mailbox: str, days: int, only_unseen: bool = True, limit: int | None = None) -> dict:
    acct = iter_accounts_from_settings(settings)[0]
    return backfill_since_days_acct(acct, mailbox, days, only_unseen, limit)


def start_scheduler() -> BackgroundScheduler:
    # Create/upgrade schema (incl. FTS)
    Base.metadata.create_all(bind=engine)
    migrate_schema()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(poll_once, "date", run_date=None)
    scheduler.add_job(poll_once, "interval", seconds=settings.poll_interval_seconds, id="poller", replace_existing=True)
    scheduler.start()
    return scheduler
