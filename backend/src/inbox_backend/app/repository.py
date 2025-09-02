from __future__ import annotations
from datetime import datetime
from typing import Iterable, Optional, Sequence, List, Dict, Tuple

from sqlalchemy import select, func, text, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from .models import Mailbox, Message, MessageBody, MessageAnalysis, Label, MessageLabel, MemoryItem


# ---------------------
# Existing primitives
# ---------------------

def ensure_mailbox(session: Session, name: str) -> Mailbox:
    mb = session.execute(select(Mailbox).where(Mailbox.name == name)).scalar_one_or_none()
    if not mb:
        mb = Mailbox(name=name, last_uid=0, last_seen=None)
        session.add(mb)
        session.flush()
    return mb


def get_last_uid(session: Session, mailbox: str) -> int:
    mb = ensure_mailbox(session, mailbox)
    return mb.last_uid


def set_last_uid(session: Session, mailbox: str, last_uid: int) -> None:
    mb = ensure_mailbox(session, mailbox)
    mb.last_uid = max(mb.last_uid, last_uid)
    mb.last_seen = datetime.utcnow()
    session.add(mb)


def upsert_messages(session: Session, rows: Iterable[dict]) -> int:
    """
    Insert-or-update messages by (mailbox, uid).
    On update: refresh flags (is_unread, is_answered, is_flagged) and body_preview if provided.
    Also ensures MessageBody is present if body_full provided and body row missing.
    Returns count of newly inserted rows.
    """
    inserted = 0
    for m in rows:
        body_full = m.pop("body_full", None)

        existing = session.execute(
            select(Message).where(
                Message.mailbox == m["mailbox"],
                Message.uid == m["uid"],
            )
        ).scalar_one_or_none()

        if existing:
            changed = False
            for k in ("is_unread", "is_answered", "is_flagged", "body_preview", "body_hash"):
                if k in m and getattr(existing, k) != m[k]:
                    setattr(existing, k, m[k]); changed = True
            for k in ("from_name", "from_email", "in_reply_to", "references_raw"):
                if k in m and getattr(existing, k) != m[k]:
                    setattr(existing, k, m[k]); changed = True
            if changed:
                session.add(existing)
            if body_full:
                has_body = session.execute(
                    select(MessageBody.id).where(MessageBody.message_id == existing.id)
                ).scalar_one_or_none()
                if not has_body:
                    session.add(MessageBody(message_id=existing.id, body_full=body_full))
            continue

        obj = Message(**m)
        session.add(obj)
        session.flush()
        if body_full:
            session.add(MessageBody(message_id=obj.id, body_full=body_full))
        inserted += 1

    return inserted


def update_flags_for_uids(session: Session, mailbox: str, flag_map: dict[int, tuple[int,int,int]]) -> int:
    touched = 0
    for uid, (unread, ans, flg) in flag_map.items():
        m = session.execute(
            select(Message).where(Message.mailbox == mailbox, Message.uid == uid)
        ).scalar_one_or_none()
        if not m:
            continue
        changed = False
        if m.is_unread != unread:
            m.is_unread = unread; changed = True
        if m.is_answered != ans:
            m.is_answered = ans; changed = True
        if m.is_flagged != flg:
            m.is_flagged = flg; changed = True
        if changed:
            session.add(m)
            touched += 1
    return touched


def get_recent_messages(session: Session, limit: int = 50) -> list[Message]:
    stmt = (
        select(Message)
        .order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def get_recent_uids(session: Session, mailbox: str, limit: int) -> list[int]:
    stmt = (
        select(Message.uid)
        .where(Message.mailbox == mailbox)
        .order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc())
        .limit(limit)
    )
    return [uid for (uid,) in session.execute(stmt)]


def search_messages(session: Session, q: str, limit: int = 50) -> list[Message]:
    """
    Full-text search using FTS5 over (subject, from_raw, snippet, body_preview).
    """
    try:
        id_rows = session.execute(text("""
            SELECT m.id
            FROM message_fts
            JOIN message AS m ON message_fts.rowid = m.id
            WHERE message_fts MATCH :q
            ORDER BY COALESCE(m.date_iso, '') DESC, m.id DESC
            LIMIT :lim
        """), {"q": q, "lim": int(limit)}).fetchall()
    except OperationalError:
        id_rows = session.execute(text("""
            SELECT id FROM message
            WHERE subject LIKE :like
               OR from_raw LIKE :like
               OR snippet LIKE :like
               OR COALESCE(body_preview,'') LIKE :like
            ORDER BY COALESCE(date_iso, '') DESC, id DESC
            LIMIT :lim
        """), {"like": f"%{q}%", "lim": int(limit)}).fetchall()

    if not id_rows:
        return []
    ids = [r[0] for r in id_rows]
    stmt = select(Message).where(Message.id.in_(ids))
    obj_map = {m.id: m for m in session.execute(stmt).scalars()}
    return [obj_map[i] for i in ids if i in obj_map]


def get_message_body(session: Session, message_id: int) -> Optional[str]:
    row = session.execute(
        select(MessageBody.body_full).where(MessageBody.message_id == message_id)
    ).scalar_one_or_none()
    return row


# ---------------------
# Analysis & labels
# ---------------------

def get_analysis(session: Session, message_id: int) -> Optional[MessageAnalysis]:
    return session.execute(
        select(MessageAnalysis).where(MessageAnalysis.message_id == message_id)
    ).scalar_one_or_none()


def upsert_analysis(
    session: Session,
    message_id: int,
    body_hash: str,
    summary_json: str,
    error: Optional[str] = None,
) -> MessageAnalysis:
    row = get_analysis(session, message_id)
    if row:
        row.body_hash = body_hash
        row.summary_json = summary_json
        row.last_error = error
        row.updated_at = datetime.utcnow()
        session.add(row)
        return row
    row = MessageAnalysis(
        message_id=message_id,
        body_hash=body_hash,
        summary_json=summary_json,
        last_error=error,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def list_labels(session: Session) -> List[Label]:
    return list(session.execute(select(Label).order_by(Label.name.asc())).scalars())


def upsert_label(session: Session, name: str, color: Optional[str] = None, weight: int = 0) -> Label:
    lab = session.execute(select(Label).where(Label.name == name)).scalar_one_or_none()
    if lab:
        if color is not None:
            lab.color = color
        if weight is not None:
            lab.weight = int(weight)
        session.add(lab)
        return lab
    lab = Label(name=name, color=color, weight=int(weight or 0))
    session.add(lab)
    session.flush()
    return lab


def apply_labels(session: Session, message_id: int, label_names: List[str]) -> None:
    if label_names is None:
        return
    name_to_id: Dict[str, int] = {}
    for nm in label_names:
        nm = (nm or "").strip()
        if not nm:
            continue
        lab = session.execute(select(Label).where(Label.name == nm)).scalar_one_or_none()
        if not lab:
            lab = Label(name=nm, color=None, weight=0)
            session.add(lab)
            session.flush()
        name_to_id[nm] = lab.id

    session.execute(delete(MessageLabel).where(MessageLabel.message_id == message_id))
    for lab_id in name_to_id.values():
        session.add(MessageLabel(message_id=message_id, label_id=lab_id))


def labels_for_message(session: Session, message_id: int) -> List[str]:
    q = text("""
        SELECT l.name
        FROM message_label AS ml
        JOIN label AS l ON l.id = ml.label_id
        WHERE ml.message_id = :mid
        ORDER BY l.name ASC
    """)
    rows = session.execute(q, {"mid": message_id}).fetchall()
    return [r[0] for r in rows]


# ---------------------
# Memory (living prompt)
# ---------------------

def list_memory(session: Session, kind: Optional[str] = None) -> List[MemoryItem]:
    stmt = select(MemoryItem)
    if kind:
        stmt = stmt.where(MemoryItem.kind == kind)
    stmt = stmt.order_by(MemoryItem.weight.desc(), MemoryItem.updated_at.desc())
    return list(session.execute(stmt).scalars())


def upsert_memory(
    session: Session,
    kind: str,
    key: str,
    value: str,
    weight: int = 0,
    expires_at: Optional[datetime] = None,
) -> MemoryItem:
    row = session.execute(
        select(MemoryItem).where(MemoryItem.kind == kind, MemoryItem.key == key)
    ).scalar_one_or_none()
    if row:
        row.value = value
        row.weight = int(weight or 0)
        row.expires_at = expires_at
        row.updated_at = datetime.utcnow()
        session.add(row)
        return row
    row = MemoryItem(
        kind=kind,
        key=key,
        value=value,
        weight=int(weight or 0),
        expires_at=expires_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def compose_allowed_labels(session: Session) -> List[str]:
    labs = list_labels(session)
    return [l.name for l in labs] if labs else ["work", "personal", "finance", "newsletter", "uncategorized"]


# ---------------------
# Backlog query
# ---------------------

def _derive_priority(importance: int, urgency: int) -> int:
    importance = max(0, min(int(importance), 5))
    urgency = max(0, min(int(urgency), 5))
    score = (2 * importance + urgency) / 3.0
    return int(round(score * 20))


def get_backlog(
    session: Session,
    limit: int = 50,
    offset: int = 0,
    min_priority: int = 0,
    only_unread: bool = False,
) -> List[Tuple[Message, Optional[MessageAnalysis], int]]:
    stmt = select(Message, MessageAnalysis).join(
        MessageAnalysis, MessageAnalysis.message_id == Message.id, isouter=True
    )
    if only_unread:
        stmt = stmt.where(Message.is_unread == 1)
    stmt = stmt.order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc()).limit(1000)
    rows = list(session.execute(stmt).all())

    out: List[Tuple[Message, Optional[MessageAnalysis], int]] = []
    import json as _json
    for (msg, an) in rows:
        importance = urgency = 0
        if an and an.summary_json:
            try:
                data = _json.loads(an.summary_json)
                importance = int(data.get("importance", 0) or 0)
                urgency = int(data.get("urgency", 0) or 0)
            except Exception:
                pass
        pr = _derive_priority(importance, urgency)
        if pr >= int(min_priority or 0):
            out.append((msg, an, pr))

    out.sort(key=lambda t: (t[2], t[0].date_iso or "", t[0].id), reverse=True)
    return out[offset: offset + limit]


# ---------------------
# Missing-analysis query (for batch summarize)
# ---------------------

def find_message_ids_missing_analysis(
    session: Session,
    only_unread: bool = False,
    limit: int = 1000,
) -> List[int]:
    """
    Return message IDs that have NO analysis, or an empty/garbage summary_json,
    or had a previous last_error (so we can retry).
    """
    # Subquery of message_ids that are considered "good" (meaningful) summaries
    # We keep this simple: non-null, length > 2 AND not one of '{}', '[]', 'null' (case-insensitive-ish).
    good_ids = session.execute(text("""
        SELECT ma.message_id
        FROM message_analysis AS ma
        WHERE ma.last_error IS NULL
          AND ma.summary_json IS NOT NULL
          AND LENGTH(TRIM(ma.summary_json)) > 2
          AND TRIM(ma.summary_json) NOT IN ('{}','[]','null','NULL')
    """)).fetchall()
    good_set = {r[0] for r in good_ids}

    # Candidate messages (recent-ish ordering; keep your ordering preference)
    stmt = select(Message.id)
    if only_unread:
        stmt = stmt.where(Message.is_unread == 1)
    stmt = stmt.order_by(func.coalesce(Message.date_iso, "").desc(), Message.id.desc()).limit(limit * 3)
    candidates = [r[0] for r in session.execute(stmt).fetchall()]

    # Filter out those with good summaries; include those with missing or error/empty summaries
    missing: List[int] = []
    if not candidates:
        return missing

    # Fast check of analysis rows for the candidates in one go
    rows = session.execute(
        select(MessageAnalysis.message_id, MessageAnalysis.summary_json, MessageAnalysis.last_error)
        .where(MessageAnalysis.message_id.in_(candidates))
    ).fetchall()
    by_id = {mid: (sj, le) for (mid, sj, le) in rows}

    for mid in candidates:
        if mid in good_set:
            continue
        sj, le = by_id.get(mid, (None, None))
        if le is not None:
            missing.append(mid)        # had an error -> retry
            continue
        s = (sj or "").strip()
        if not s or s in ("{}", "[]", "null", "NULL"):
            missing.append(mid)        # empty-ish -> retry
            continue
        # Extra safety: if JSON is corrupt, retry
        try:
            _ = json.loads(s)
        except Exception:
            missing.append(mid)
            continue

    # Apply limit after filtering
    return missing[: int(limit)]
