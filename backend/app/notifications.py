"""In-app notifications with idempotent delivery.

Every notification carries a dedup key, so a retried event or a re-run job
never notifies twice. Email delivery is the labelled development stub only
(log line), like account verification; nothing is sent to an external provider.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("homematch.api")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def notify(repo, user_id: str, kind: str, title: str, body: str, dedup_key: str, link: str | None = None,
           email: bool = False) -> bool:
    """Returns True only when a new notification was stored."""
    with repo.db:
        exists = repo.db.execute("SELECT 1 FROM hm_notifications WHERE dedup_key=?", (dedup_key,)).fetchone()
        if exists:
            return False
        repo.db.execute("INSERT INTO hm_notifications(id,user_id,kind,title,body,link,dedup_key,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (str(uuid4()), user_id, kind, title, body, link, dedup_key, utc_now()))
    if email:
        # Development stub: no email provider is integrated; the log line is labelled as fake delivery.
        logger.info("DEV-STUB fake email (development only): kind=%s", kind)
    return True


def list_for(repo, user_id: str, limit: int = 50) -> dict:
    rows = [dict(row) for row in repo.db.execute(
        "SELECT id,kind,title,body,link,created_at,read_at FROM hm_notifications WHERE user_id=? "
        "ORDER BY created_at DESC LIMIT ?", (user_id, limit))]
    unread = repo.db.execute("SELECT COUNT(*) AS n FROM hm_notifications WHERE user_id=? AND read_at IS NULL",
                             (user_id,)).fetchone()["n"]
    return {"unread": unread, "items": rows}


def mark_read(repo, user_id: str, notification_id: str | None = None):
    with repo.db:
        if notification_id is None:
            repo.db.execute("UPDATE hm_notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
                            (utc_now(), user_id))
        else:
            repo.db.execute("UPDATE hm_notifications SET read_at=? WHERE id=? AND user_id=?",
                            (utc_now(), notification_id, user_id))
