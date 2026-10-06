"""Automation engine: scheduled reminders, lead re-engagement and housekeeping.

`run_due` is idempotent: every notification has a dedup key, so running it
every few minutes (background thread), from `python -m backend.manage jobs`
or from the admin console never notifies twice. Jobs only read ledger data and
the deterministic cost engine; nothing here calls a model.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .costs import calculate_cost
from .models import Scenario
from .notifications import notify

REENGAGE_AFTER_HOURS = int(os.getenv("HOMEMATCH_REENGAGE_AFTER_HOURS", "24"))
SIMILAR_PRICE_BAND = 0.2


def _money(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " ₫"


def viewing_reminders(service, now: datetime) -> int:
    soon = (now + timedelta(hours=24)).isoformat()
    sent = 0
    for row in service.repo.db.execute("SELECT id,owner_id,landlord_id,room_id,requested_at,mode,meeting_url "
                                       "FROM hm_viewings WHERE status='confirmed' AND requested_at>? AND requested_at<=?",
                                       (now.isoformat(), soon)).fetchall():
        when = datetime.fromisoformat(row["requested_at"]).astimezone(timezone(timedelta(hours=7)))
        body = (f"Lịch xem phòng {row['room_id']} lúc {when:%H:%M %d/%m} (giờ Việt Nam), "
                + ("trực tuyến qua link phòng họp." if row["mode"] == "online" else "xem trực tiếp."))
        for user, link in ((row["owner_id"], "/nguoi-thue/lich-xem"), (row["landlord_id"], "/chu-nha/lich-xem")):
            sent += notify(service.repo, user, "viewing_reminder", "Nhắc lịch xem phòng", body,
                           f"viewing-reminder:{row['id']}:{user}", link, email=True)
    return sent


def similar_rooms(rooms, room, limit: int = 3) -> list:
    base = calculate_cost(room.quote, Scenario()).monthly_total_vnd or room.quote.rent_vnd
    result = []
    for other in rooms:
        if other.id == room.id or not other.published or other.available is not True:
            continue
        if other.city != room.city or other.room_type != room.room_type:
            continue
        monthly = calculate_cost(other.quote, Scenario()).monthly_total_vnd
        if monthly is None or abs(monthly - base) > base * SIMILAR_PRICE_BAND:
            continue
        result.append((abs(monthly - base), other, monthly))
    return [(other, monthly) for _, other, monthly in sorted(result, key=lambda item: (item[0], item[1].id))[:limit]]


def lead_reengagement(service, now: datetime) -> int:
    """Renters who looked at a room but booked no viewing get comparable vacant rooms, once."""
    cutoff = (now - timedelta(hours=REENGAGE_AFTER_HOURS)).isoformat()
    rows = service.repo.db.execute(
        "SELECT user_id,room_id,MAX(viewed_at) AS last_view FROM hm_room_views WHERE user_id IS NOT NULL "
        "GROUP BY user_id,room_id HAVING MAX(viewed_at)<=?", (cutoff,)).fetchall()
    rooms = {room.id: room for room in service.catalog.rooms()}
    sent = 0
    for row in rows:
        booked = service.repo.db.execute("SELECT 1 FROM hm_viewings WHERE owner_id=? AND room_id=?",
                                         (row["user_id"], row["room_id"])).fetchone()
        room = rooms.get(row["room_id"])
        if booked or room is None:
            continue
        suggestions = similar_rooms(list(rooms.values()), room)
        if not suggestions:
            continue
        lines = "; ".join(f"{other.title.split('. ')[0]} ({_money(monthly)}/tháng)" for other, monthly in suggestions)
        sent += notify(service.repo, row["user_id"], "lead_reengagement", "Phòng tương tự bạn có thể quan tâm",
                       f"Bạn đã xem {room.title.split('. ')[0]} nhưng chưa đặt lịch. Gợi ý tương đương: {lines}.",
                       f"reengage:{row['user_id']}:{row['room_id']}", "/tim-kiem")
    return sent


def payment_reminders(service, now: datetime) -> int:
    """Due within 3 days → renter; overdue → renter and landlord. One notice per invoice per stage."""
    today = now.date()
    sent = 0
    rows = service.repo.db.execute("SELECT i.id,i.period,i.total_vnd,i.paid_vnd,i.due_date,l.renter_id,l.landlord_id,"
                                   "l.room_id FROM hm_invoices i JOIN hm_leases l ON l.id=i.lease_id "
                                   "WHERE i.status='issued' AND i.paid_vnd<i.total_vnd").fetchall()
    for row in rows:
        due = datetime.fromisoformat(row["due_date"]).date()
        balance = _money(row["total_vnd"] - row["paid_vnd"])
        if due < today:
            for user, link in ((row["renter_id"], "/nguoi-thue/hoa-don"), (row["landlord_id"], "/chu-nha/hoa-don")):
                sent += notify(service.repo, user, "invoice_overdue", "Hóa đơn quá hạn",
                               f"Phòng {row['room_id']} kỳ {row['period']} còn nợ {balance} (hạn {row['due_date']}).",
                               f"invoice-overdue:{row['id']}:{user}", link, email=True)
        elif (due - today).days <= 3:
            sent += notify(service.repo, row["renter_id"], "invoice_due", "Sắp đến hạn thanh toán",
                           f"Hóa đơn kỳ {row['period']} còn {balance}, hạn {row['due_date']}.",
                           f"invoice-due:{row['id']}", "/nguoi-thue/hoa-don", email=True)
    return sent


def lease_renewal_reminders(service, now: datetime) -> int:
    limit = (now.date() + timedelta(days=30)).isoformat()
    sent = 0
    for row in service.repo.db.execute("SELECT id,renter_id,landlord_id,room_id,end_date FROM hm_leases "
                                       "WHERE status='active' AND end_date<=?", (limit,)).fetchall():
        renewed = service.repo.db.execute("SELECT 1 FROM hm_leases WHERE renewal_of=? AND status!='terminated'",
                                          (row["id"],)).fetchone()
        if renewed:
            continue
        body = f"Hợp đồng phòng {row['room_id']} hết hạn ngày {row['end_date']}. Trao đổi để gia hạn hoặc thanh lý."
        for user, link in ((row["renter_id"], "/nguoi-thue/hop-dong"), (row["landlord_id"], "/chu-nha/hop-dong")):
            sent += notify(service.repo, user, "lease_renewal", "Sắp hết hạn hợp đồng", body,
                           f"lease-renewal:{row['id']}:{user}", link, email=True)
    return sent


EXTRA_JOBS = [("payment_reminders", payment_reminders), ("lease_renewal_reminders", lease_renewal_reminders)]


def run_due(service, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    run_id = str(uuid4())
    with service.repo.db:
        service.repo.db.execute("INSERT INTO hm_job_runs(id,started_at) VALUES(?,?)", (run_id, now.isoformat()))
    summary = {"viewing_reminders": viewing_reminders(service, now),
               "lead_reengagement": lead_reengagement(service, now),
               "transcripts_purged": service.purge_transcripts()}
    for name, job in EXTRA_JOBS:
        summary[name] = job(service, now)
    with service.repo.db:
        service.repo.db.execute("UPDATE hm_job_runs SET finished_at=?,summary_json=? WHERE id=?",
                                (datetime.now(timezone.utc).isoformat(), json.dumps(summary), run_id))
    return {"run_id": run_id, **summary}
