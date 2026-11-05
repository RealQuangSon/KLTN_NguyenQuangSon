"""Landlord promotions per listing.

A promotion is landlord-entered marketing text with an end date, shown on the
public listing and reused by the lead re-engagement job. It never changes the
approved rent and is never read by the pricing or ranking engines (catalog.py,
costs.py and semantic.py must not touch hm_promotions). Text is PII-masked on
write so phone numbers or emails cannot leak into public DTOs or
notifications.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .conversations import mask_pii, utc_now
from .models import DomainError

MAX_DAYS = 90


def today_vn() -> date:
    """The platform's calendar day in Vietnam time (UTC+7)."""
    return datetime.now(timezone(timedelta(hours=7))).date()


def set_promotion(repo, room_id: str, landlord_id: str, text: str, valid_until: date) -> dict:
    today = today_vn()
    if not today <= valid_until <= today + timedelta(days=MAX_DAYS):
        raise DomainError("invalid_promotion",
                          f"Ngày kết thúc ưu đãi phải từ hôm nay đến tối đa {MAX_DAYS} ngày nữa.", 422)
    stripped = text.strip()
    if not stripped:
        raise DomainError("invalid_promotion", "Nội dung ưu đãi cần có ít nhất một ký tự.", 422)
    masked = mask_pii(stripped)
    with repo.db:
        repo.db.execute("INSERT INTO hm_promotions(room_id,landlord_id,text,valid_until,updated_at) "
                        "VALUES(?,?,?,?,?) ON CONFLICT(room_id) DO UPDATE SET landlord_id=excluded.landlord_id,"
                        "text=excluded.text,valid_until=excluded.valid_until,updated_at=excluded.updated_at",
                        (room_id, landlord_id, masked, valid_until.isoformat(), utc_now()))
    return {"room_id": room_id, "text": masked, "valid_until": valid_until.isoformat()}


def delete_promotion(repo, room_id: str) -> None:
    exists = repo.db.execute("SELECT 1 FROM hm_promotions WHERE room_id=?", (room_id,)).fetchone()
    if exists is None:
        raise DomainError("not_found", "Phòng này chưa có ưu đãi.", 404)
    with repo.db:
        repo.db.execute("DELETE FROM hm_promotions WHERE room_id=?", (room_id,))


def active(repo, room_id: str, today: date | None = None) -> dict | None:
    """The stored promotion while it is still valid (end date today or later); null otherwise."""
    row = repo.db.execute("SELECT text,valid_until FROM hm_promotions WHERE room_id=?", (room_id,)).fetchone()
    if row is None or date.fromisoformat(row["valid_until"]) < (today or today_vn()):
        return None
    return {"text": row["text"], "valid_until": row["valid_until"]}


def active_by_room(repo, today: date | None = None) -> dict[str, dict]:
    """Every still-valid promotion in a single query, keyed by room, for list pages."""
    today = today or today_vn()
    return {row["room_id"]: {"text": row["text"], "valid_until": row["valid_until"]}
            for row in repo.db.execute("SELECT room_id,text,valid_until FROM hm_promotions").fetchall()
            if date.fromisoformat(row["valid_until"]) >= today}
