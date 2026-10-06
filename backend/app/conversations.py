"""Live chat between a renter and a landlord, with smart handover from the AI.

Starting a conversation copies a handover context: the renter's confirmed needs
(never income, the exact ratio or loan terms), the room, and the recent AI chat
turns, all PII-masked. Messages are polled; delivery is in-app only. A landlord
only sees conversations about their own rooms.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from .models import DomainError

ACCOUNT_NUMBER = re.compile(r"(?<!\d)\d{9,16}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+84|0)(?:[ .-]*\d){8,10}(?!\d)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_pii(text: str) -> str:
    """Contact details and account-like numbers never reach logs, audit views or handover context."""
    text = EMAIL.sub("[email đã che]", text)
    text = PHONE.sub("[SĐT đã che]", text)
    return ACCOUNT_NUMBER.sub("[số đã che]", text)


def needs_summary(profile: dict | None) -> dict | None:
    if not profile:
        return None
    return {key: profile.get(key) for key in ("city", "area", "room_type", "min_bedrooms", "must_amenities",
                                              "preferences", "max_monthly_cost_vnd")
            if profile.get(key) not in (None, [])} | {"people": (profile.get("scenario") or {}).get("people")}


def start(repo, renter_id: str, landlord_id: str, room_id: str | None, session_id: str | None,
          context: dict) -> dict:
    existing = repo.db.execute("SELECT * FROM hm_conversations WHERE renter_id=? AND landlord_id=? AND "
                               + ("room_id=?" if room_id else "room_id IS NULL"),
                               (renter_id, landlord_id, *([room_id] if room_id else []))).fetchone()
    if existing:
        return dict(existing)
    now = utc_now()
    conversation_id = str(uuid4())
    with repo.db:
        repo.db.execute("INSERT INTO hm_conversations(id,renter_id,landlord_id,room_id,session_id,status,context_json,"
                        "created_at,last_message_at) VALUES(?,?,?,?,?,'open',?,?,?)",
                        (conversation_id, renter_id, landlord_id, room_id, session_id,
                         json.dumps(context, ensure_ascii=False), now, now))
        repo.db.execute("INSERT INTO hm_messages VALUES(?,?,?,?,?,?)",
                        (str(uuid4()), conversation_id, "system", "system",
                         "Khách chuyển từ trợ lý AI sang trò chuyện trực tiếp. Ngữ cảnh đã được chuyển kèm "
                         "(nhu cầu đã xác nhận, phòng quan tâm, các lượt chat gần nhất đã che thông tin liên hệ).",
                         now))
    return get(repo, conversation_id)


def get(repo, conversation_id: str) -> dict:
    row = repo.db.execute("SELECT * FROM hm_conversations WHERE id=?", (conversation_id,)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy cuộc trò chuyện.", 404)
    return dict(row)


def authorize(conversation: dict, actor) -> str:
    """Returns the actor's side; anyone else gets the same 404 as a missing conversation."""
    if actor.role == "renter" and conversation["renter_id"] == actor.id:
        return "renter"
    if actor.role == "owner" and conversation["landlord_id"] == actor.id:
        return "landlord"
    raise DomainError("not_found", "Không tìm thấy cuộc trò chuyện.", 404)


def projection(repo, conversation: dict, side: str | None) -> dict:
    read_at = conversation.get(f"{side}_read_at") if side else None
    other = "owner" if side == "renter" else "renter"
    unread = repo.db.execute("SELECT COUNT(*) AS n FROM hm_messages WHERE conversation_id=? AND sender_role=? "
                             "AND created_at>?", (conversation["id"], other, read_at or "")).fetchone()["n"]
    return {**{key: conversation[key] for key in ("id", "renter_id", "landlord_id", "room_id", "session_id",
                                                 "status", "created_at", "last_message_at", "first_response_at")},
            "context": json.loads(conversation["context_json"]), "unread": unread}


def messages(repo, conversation_id: str, after: str | None = None) -> list[dict]:
    rows = repo.db.execute("SELECT id,sender_id,sender_role,body,created_at FROM hm_messages WHERE conversation_id=? "
                           "AND created_at>? ORDER BY created_at,id", (conversation_id, after or ""))
    return [dict(row) for row in rows]


def send(repo, conversation: dict, actor, side: str, body: str) -> dict:
    text = body.strip()
    if not text or len(text) > 2000:
        raise DomainError("invalid_message", "Tin nhắn cần có 1–2000 ký tự.", 422)
    if conversation["status"] != "open":
        raise DomainError("conversation_closed", "Cuộc trò chuyện đã đóng.", 409)
    now = utc_now()
    message = {"id": str(uuid4()), "sender_id": actor.id, "sender_role": actor.role, "body": text, "created_at": now}
    with repo.db:
        repo.db.execute("INSERT INTO hm_messages VALUES(?,?,?,?,?,?)",
                        (message["id"], conversation["id"], actor.id, actor.role, text, now))
        repo.db.execute(f"UPDATE hm_conversations SET last_message_at=?,{side}_read_at=? WHERE id=?",
                        (now, now, conversation["id"]))
        if side == "landlord" and not conversation["first_response_at"]:
            repo.db.execute("UPDATE hm_conversations SET first_response_at=? WHERE id=? AND first_response_at IS NULL",
                            (now, conversation["id"]))
    return message


def mark_read(repo, conversation_id: str, side: str):
    with repo.db:
        repo.db.execute(f"UPDATE hm_conversations SET {side}_read_at=? WHERE id=?", (utc_now(), conversation_id))


def handover_report(repo) -> dict:
    """Landlord responsiveness for the admin console: response rate and median first-response time."""
    rows = [dict(row) for row in repo.db.execute("SELECT id,landlord_id,created_at,first_response_at,status "
                                                 "FROM hm_conversations ORDER BY created_at DESC")]
    by_landlord: dict[str, dict] = {}
    for row in rows:
        minutes = None
        if row["first_response_at"]:
            delta = datetime.fromisoformat(row["first_response_at"]) - datetime.fromisoformat(row["created_at"])
            minutes = round(delta.total_seconds() / 60, 1)
        row["response_minutes"] = minutes
        stats = by_landlord.setdefault(row["landlord_id"], {"landlord_id": row["landlord_id"], "conversations": 0,
                                                            "answered": 0, "minutes": []})
        stats["conversations"] += 1
        if minutes is not None:
            stats["answered"] += 1
            stats["minutes"].append(minutes)
    summary = []
    for stats in by_landlord.values():
        values = sorted(stats.pop("minutes"))
        stats["response_rate"] = round(stats["answered"] / stats["conversations"], 3)
        stats["median_response_minutes"] = values[len(values) // 2] if values else None
        summary.append(stats)
    return {"landlords": sorted(summary, key=lambda item: item["landlord_id"]), "conversations": rows}
