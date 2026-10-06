"""Landlord property management (PMS) and CRM.

Leases, meter readings, invoices, payments, maintenance and the lead pipeline.
Money follows the same rules as the pre-rental cost engine: integer VND,
Decimal unit prices, HALF_UP rounding per line, and no unknown rate is ever
billed as 0 (issuing an invoice with a missing rate is refused). Issued
invoices are immutable; payments are append-only records with a receipt number.
Contract acceptance is a versioned click-accept inside the app, not a legal
e-signature.
"""
from __future__ import annotations

import html
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .costs import rounded_vnd
from .models import Actor, DomainError, Model

LEASE_STATES = ("draft", "sent", "accepted", "active", "ended", "terminated")
TICKET_TRANSITIONS = {
    "submitted": {"assigned", "in_progress", "resolved"},
    "assigned": {"in_progress", "resolved"},
    "in_progress": {"resolved"},
    "reopened": {"assigned", "in_progress", "resolved"},
    "resolved": {"closed", "reopened"},
    "closed": set(),
}
LEAD_STAGES = ("new", "contacted", "viewing", "negotiating", "won", "lost")
LEAD_POINTS = {"view": 1, "chat": 3, "viewing": 5, "lease": 8}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def money(value: int | None) -> str:
    return "—" if value is None else f"{value:,}".replace(",", ".") + " ₫"


# ---------------------------------------------------------------- inputs

class LeaseInput(Model):
    renter_id: str = Field(min_length=1, max_length=64)
    room_id: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    rent_vnd: int | None = Field(default=None, gt=0)
    deposit_vnd: int | None = Field(default=None, ge=0)
    payment_day: int = Field(default=5, ge=1, le=28)
    occupants: int = Field(default=1, ge=1, le=20)
    vehicles: int = Field(default=1, ge=0, le=20)
    terms: str | None = Field(default=None, max_length=5000)


class LeaseRenewal(Model):
    end_date: date
    rent_vnd: int | None = Field(default=None, gt=0)


class LeaseTermination(Model):
    end_date: date
    settlement_note: str = Field(min_length=1, max_length=2000)


class ReadingInput(Model):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    electricity_start: Decimal | None = Field(default=None, ge=0)
    electricity_end: Decimal | None = Field(default=None, ge=0)
    water_start: Decimal | None = Field(default=None, ge=0)
    water_end: Decimal | None = Field(default=None, ge=0)


class InvoiceInput(Model):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    due_date: date | None = None


class PaymentInput(Model):
    amount_vnd: int = Field(gt=0)
    method: Literal["cash", "transfer"] = "transfer"
    reference: str | None = Field(default=None, max_length=120)


class ClaimInput(Model):
    amount_vnd: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=120)


class TicketInput(Model):
    room_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    priority: Literal["low", "normal", "urgent"] = "normal"


class TicketUpdate(Model):
    status: Literal["assigned", "in_progress", "resolved", "closed", "reopened"] | None = None
    assignee: str | None = Field(default=None, max_length=120)
    cost_vnd: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)


class LeadUpdate(Model):
    stage: Literal["new", "contacted", "viewing", "negotiating", "won", "lost"] | None = None
    notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- leases

DEFAULT_TERMS = ("1. Bên thuê thanh toán tiền thuê và các khoản phí theo hóa đơn hằng tháng trước ngày thanh toán.\n"
                 "2. Tiền cọc được hoàn sau khi bàn giao phòng, trừ các khoản hư hỏng hoặc nợ phí có biên bản.\n"
                 "3. Bên nào chấm dứt trước hạn phải báo trước ít nhất 30 ngày.\n"
                 "4. Bên thuê tuân thủ nội quy của nhà; bên cho thuê sửa chữa hư hỏng không do bên thuê gây ra.")


def lease(repo, lease_id: str) -> dict:
    row = repo.db.execute("SELECT * FROM hm_leases WHERE id=?", (lease_id,)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy hợp đồng.", 404)
    return dict(row)


def lease_for(repo, lease_id: str, actor) -> dict:
    item = lease(repo, lease_id)
    if (actor.role == "owner" and item["landlord_id"] == actor.id) or \
            (actor.role == "renter" and item["renter_id"] == actor.id and item["status"] != "draft"):
        return item
    raise DomainError("not_found", "Không tìm thấy hợp đồng.", 404)


def leases(repo, actor) -> list[dict]:
    column = "landlord_id" if actor.role == "owner" else "renter_id"
    extra = "" if actor.role == "owner" else " AND status!='draft'"
    rows = repo.db.execute(f"SELECT * FROM hm_leases WHERE {column}=?{extra} ORDER BY created_at DESC", (actor.id,))
    return [dict(row) for row in rows]


def _overlaps(repo, room_id: str, start: date, end: date, ignore: str | None = None) -> bool:
    rows = repo.db.execute("SELECT id,start_date,end_date FROM hm_leases WHERE room_id=? AND status IN "
                           "('sent','accepted','active')", (room_id,)).fetchall()
    return any(row["id"] != ignore and start < date.fromisoformat(row["end_date"])
               and date.fromisoformat(row["start_date"]) < end for row in rows)


def create_lease(repo, room, landlord_id: str, data: LeaseInput, renewal_of: str | None = None) -> dict:
    if room.landlord != landlord_id:
        raise DomainError("not_found", "Không tìm thấy phòng.", 404)
    if data.end_date <= data.start_date:
        raise DomainError("invalid_period", "Ngày kết thúc phải sau ngày bắt đầu.", 422)
    renter = repo.db.execute("SELECT role FROM hm_users WHERE id=?", (data.renter_id,)).fetchone()
    if renter is None or renter["role"] != "renter":
        raise DomainError("invalid_renter", "Không tìm thấy tài khoản người thuê.", 422)
    if _overlaps(repo, room.id, data.start_date, data.end_date, ignore=renewal_of):
        raise DomainError("lease_overlap", "Phòng đã có hợp đồng trong khoảng thời gian này.", 409)
    now = utc_now()
    lease_id = str(uuid4())
    with repo.db:
        repo.db.execute("INSERT INTO hm_leases(id,landlord_id,renter_id,room_id,start_date,end_date,rent_vnd,"
                        "deposit_vnd,payment_day,occupants,vehicles,terms,status,version,renewal_of,quote_json,"
                        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'draft',1,?,?,?,?)",
                        (lease_id, landlord_id, data.renter_id, room.id, data.start_date.isoformat(),
                         data.end_date.isoformat(), data.rent_vnd or room.quote.rent_vnd,
                         data.deposit_vnd if data.deposit_vnd is not None else (room.quote.deposit_vnd or 0),
                         data.payment_day, data.occupants, data.vehicles, data.terms or DEFAULT_TERMS,
                         renewal_of, room.quote.model_dump_json(), now, now))
    return lease(repo, lease_id)


def update_lease(repo, item: dict, data: LeaseInput) -> dict:
    if item["status"] not in ("draft", "sent"):
        raise DomainError("lease_locked", "Chỉ sửa được hợp đồng chưa hiệu lực.", 409)
    if data.room_id != item["room_id"] or data.renter_id != item["renter_id"]:
        raise DomainError("invalid_request", "Không đổi phòng hoặc người thuê của hợp đồng.", 422)
    if data.end_date <= data.start_date:
        raise DomainError("invalid_period", "Ngày kết thúc phải sau ngày bắt đầu.", 422)
    if _overlaps(repo, item["room_id"], data.start_date, data.end_date, ignore=item["id"]):
        raise DomainError("lease_overlap", "Phòng đã có hợp đồng trong khoảng thời gian này.", 409)
    with repo.db:
        # Any change creates a new version; an earlier renter acceptance no longer applies.
        repo.db.execute("UPDATE hm_leases SET start_date=?,end_date=?,rent_vnd=?,deposit_vnd=?,payment_day=?,"
                        "occupants=?,vehicles=?,terms=?,version=version+1,status='draft',updated_at=? WHERE id=?",
                        (data.start_date.isoformat(), data.end_date.isoformat(), data.rent_vnd or item["rent_vnd"],
                         data.deposit_vnd if data.deposit_vnd is not None else item["deposit_vnd"],
                         data.payment_day, data.occupants, data.vehicles, data.terms or item["terms"],
                         utc_now(), item["id"]))
    return lease(repo, item["id"])


def set_lease_status(repo, item: dict, status: str, expected: tuple[str, ...], **fields) -> dict:
    if item["status"] not in expected:
        raise DomainError("lease_state", f"Hợp đồng đang ở trạng thái {item['status']}.", 409)
    assignments = ", ".join(f"{key}=?" for key in fields)
    with repo.db:
        repo.db.execute(f"UPDATE hm_leases SET status=?,updated_at=?{', ' + assignments if assignments else ''} "
                        "WHERE id=? AND status=?", (status, utc_now(), *fields.values(), item["id"], item["status"]))
    return lease(repo, item["id"])


def lease_document(item: dict, room_title: str) -> str:
    esc = html.escape
    terms = "".join(f"<li>{esc(line.split('. ', 1)[-1])}</li>" for line in item["terms"].splitlines() if line.strip())
    accepted = ("Bên thuê đã chấp thuận phiên bản " + str(item["renter_accepted_version"])
                if item["renter_accepted_version"] else "Bên thuê chưa chấp thuận")
    return f"""<article class="document"><h1>HỢP ĐỒNG THUÊ PHÒNG</h1>
<p>Mã hợp đồng: {esc(item['id'])} · Phiên bản {item['version']} · Trạng thái: {esc(item['status'])}</p>
<p><strong>Bên cho thuê:</strong> {esc(item['landlord_id'])} &nbsp; <strong>Bên thuê:</strong> {esc(item['renter_id'])}</p>
<p><strong>Phòng:</strong> {esc(room_title)} ({esc(item['room_id'])})</p>
<p><strong>Thời hạn:</strong> {esc(item['start_date'])} đến {esc(item['end_date'])} · Thanh toán trước ngày
{item['payment_day']} hằng tháng</p>
<p><strong>Giá thuê:</strong> {money(item['rent_vnd'])}/tháng · <strong>Tiền cọc:</strong> {money(item['deposit_vnd'])}
· Số người ở: {item['occupants']} · Số xe: {item['vehicles']}</p>
<h2>Điều khoản</h2><ol>{terms}</ol>
<p><em>{accepted}. Chấp thuận trong ứng dụng là xác nhận nội dung giữa hai bên, không thay thế chữ ký số có
giá trị pháp lý.</em></p></article>"""


# ---------------------------------------------------------------- billing

def record_reading(repo, item: dict, data: ReadingInput, actor_id: str) -> dict:
    if item["status"] != "active":
        raise DomainError("lease_state", "Chỉ ghi chỉ số cho hợp đồng đang hiệu lực.", 409)
    previous = repo.db.execute("SELECT electricity_end,water_end FROM hm_meter_readings WHERE lease_id=? AND period<? "
                               "ORDER BY period DESC LIMIT 1", (item["id"], data.period)).fetchone()
    e_start = data.electricity_start if data.electricity_start is not None else (
        Decimal(str(previous["electricity_end"])) if previous and previous["electricity_end"] is not None else None)
    w_start = data.water_start if data.water_start is not None else (
        Decimal(str(previous["water_end"])) if previous and previous["water_end"] is not None else None)
    for start, end, label in ((e_start, data.electricity_end, "điện"), (w_start, data.water_end, "nước")):
        if end is not None and start is None:
            raise DomainError("reading_start_required", f"Cần chỉ số đầu kỳ của {label} cho kỳ đầu tiên.", 422)
        if end is not None and end < start:
            raise DomainError("reading_decreased", f"Chỉ số cuối kỳ {label} nhỏ hơn đầu kỳ.", 422)
    with repo.db:
        repo.db.execute("INSERT INTO hm_meter_readings VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(lease_id,period) DO UPDATE "
                        "SET electricity_start=excluded.electricity_start,electricity_end=excluded.electricity_end,"
                        "water_start=excluded.water_start,water_end=excluded.water_end,recorded_by=excluded.recorded_by,"
                        "recorded_at=excluded.recorded_at",
                        (str(uuid4()), item["id"], data.period,
                         *(str(value) if value is not None else None
                           for value in (e_start, data.electricity_end, w_start, data.water_end)),
                         actor_id, utc_now()))
    return dict(repo.db.execute("SELECT * FROM hm_meter_readings WHERE lease_id=? AND period=?",
                                (item["id"], data.period)).fetchone())


def invoice_lines(item: dict, reading: dict | None) -> list[dict]:
    """Rent plus each fee from the quote snapshot taken when the lease was created."""
    quote = json.loads(item["quote_json"])
    lines = [{"name": "rent", "label": "Tiền thuê", "quantity": "1", "unit_price": str(item["rent_vnd"]),
              "amount_vnd": item["rent_vnd"]}]
    labels = {"electricity": "Điện", "water": "Nước", "internet": "Internet", "parking": "Gửi xe",
              "service": "Dịch vụ"}
    missing = []
    for fee in quote["fees"]:
        label = labels.get(fee["name"], fee["name"])
        if fee["included_in_rent"]:
            lines.append({"name": fee["name"], "label": label + " (đã gồm trong thuê)", "quantity": "0",
                          "unit_price": "0", "amount_vnd": 0})
            continue
        if fee["amount_vnd"] is None:
            missing.append(label)
            continue
        rate = Decimal(str(fee["amount_vnd"]))
        if fee["mode"] in ("kwh", "m3"):
            key = "electricity" if fee["mode"] == "kwh" else "water"
            if not reading or reading.get(f"{key}_end") is None:
                missing.append(f"chỉ số {label.lower()}")
                continue
            quantity = Decimal(str(reading[f"{key}_end"])) - Decimal(str(reading[f"{key}_start"]))
        else:
            quantity = Decimal({"fixed": 1, "person": item["occupants"], "vehicle": item["vehicles"]}[fee["mode"]])
        lines.append({"name": fee["name"], "label": label, "quantity": str(quantity), "unit_price": str(rate),
                      "amount_vnd": rounded_vnd(quantity * rate)})
    if missing:
        raise DomainError("invoice_incomplete", "Chưa lập được hóa đơn, còn thiếu: " + ", ".join(missing) + ".", 422)
    return lines


def issue_invoice(repo, item: dict, data: InvoiceInput) -> dict:
    if item["status"] != "active":
        raise DomainError("lease_state", "Chỉ lập hóa đơn cho hợp đồng đang hiệu lực.", 409)
    exists = repo.db.execute("SELECT id FROM hm_invoices WHERE lease_id=? AND period=?",
                             (item["id"], data.period)).fetchone()
    if exists:
        raise DomainError("invoice_exists", "Kỳ này đã có hóa đơn; hóa đơn đã phát hành không sửa được.", 409)
    reading = repo.db.execute("SELECT * FROM hm_meter_readings WHERE lease_id=? AND period=?",
                              (item["id"], data.period)).fetchone()
    lines = invoice_lines(item, dict(reading) if reading else None)
    year, month = map(int, data.period.split("-"))
    due = data.due_date or date(year, month, item["payment_day"])
    invoice_id = str(uuid4())
    with repo.db:
        repo.db.execute("INSERT INTO hm_invoices VALUES(?,?,?,?,?,0,?,'issued',?)",
                        (invoice_id, item["id"], data.period, json.dumps(lines, ensure_ascii=False),
                         sum(line["amount_vnd"] for line in lines), due.isoformat(), utc_now()))
    return invoice(repo, invoice_id)


def invoice(repo, invoice_id: str) -> dict:
    row = repo.db.execute("SELECT i.*,l.landlord_id,l.renter_id,l.room_id FROM hm_invoices i "
                          "JOIN hm_leases l ON l.id=i.lease_id WHERE i.id=?", (invoice_id,)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy hóa đơn.", 404)
    return invoice_projection(dict(row))


def invoice_projection(row: dict, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    balance = row["total_vnd"] - row["paid_vnd"]
    status = "paid" if balance <= 0 else "partially_paid" if row["paid_vnd"] > 0 else "unpaid"
    return {**{key: row[key] for key in ("id", "lease_id", "period", "total_vnd", "paid_vnd", "due_date",
                                         "created_at", "landlord_id", "renter_id", "room_id")},
            "lines": json.loads(row["lines_json"]), "balance_vnd": max(balance, 0), "payment_status": status,
            "overdue": balance > 0 and date.fromisoformat(row["due_date"]) < today}


def invoices(repo, actor) -> list[dict]:
    column = "l.landlord_id" if actor.role == "owner" else "l.renter_id"
    rows = repo.db.execute(f"SELECT i.*,l.landlord_id,l.renter_id,l.room_id FROM hm_invoices i JOIN hm_leases l "
                           f"ON l.id=i.lease_id WHERE {column}=? ORDER BY i.period DESC,i.created_at DESC", (actor.id,))
    return [invoice_projection(dict(row)) for row in rows]


def invoice_for(repo, invoice_id: str, actor) -> dict:
    item = invoice(repo, invoice_id)
    if (actor.role == "owner" and item["landlord_id"] == actor.id) or \
            (actor.role == "renter" and item["renter_id"] == actor.id):
        return item
    raise DomainError("not_found", "Không tìm thấy hóa đơn.", 404)


def record_payment(repo, item: dict, data: PaymentInput, actor_id: str, claim_id: str | None = None) -> dict:
    if data.amount_vnd > item["balance_vnd"]:
        raise DomainError("overpayment", "Số tiền vượt số còn phải thu của hóa đơn.", 422)
    now = utc_now()
    count = repo.db.execute("SELECT COUNT(*) AS n FROM hm_payments").fetchone()["n"] + 1
    receipt_no = f"BL-{item['period'].replace('-', '')}-{count:05d}"
    payment_id = str(uuid4())
    with repo.db:
        changed = repo.db.execute("UPDATE hm_invoices SET paid_vnd=paid_vnd+? WHERE id=? AND paid_vnd=?",
                                  (data.amount_vnd, item["id"], item["paid_vnd"])).rowcount
        if changed != 1:
            raise DomainError("invoice_changed", "Hóa đơn vừa thay đổi; hãy tải lại.", 409)
        repo.db.execute("INSERT INTO hm_payments VALUES(?,?,?,?,?,?,?,?,?)",
                        (payment_id, item["id"], data.amount_vnd, data.method, data.reference, receipt_no,
                         claim_id, actor_id, now))
    return dict(repo.db.execute("SELECT * FROM hm_payments WHERE id=?", (payment_id,)).fetchone())


def payments(repo, invoice_id: str) -> list[dict]:
    return [dict(row) for row in repo.db.execute("SELECT * FROM hm_payments WHERE invoice_id=? ORDER BY recorded_at",
                                                 (invoice_id,))]


def claim_payment(repo, item: dict, renter_id: str, data: ClaimInput) -> dict:
    if item["balance_vnd"] <= 0:
        raise DomainError("invoice_paid", "Hóa đơn đã thanh toán đủ.", 409)
    claim_id = str(uuid4())
    with repo.db:
        repo.db.execute("INSERT INTO hm_payment_claims VALUES(?,?,?,?,?,'pending',?,NULL)",
                        (claim_id, item["id"], renter_id, data.amount_vnd, data.reference, utc_now()))
    return dict(repo.db.execute("SELECT * FROM hm_payment_claims WHERE id=?", (claim_id,)).fetchone())


def claims(repo, actor) -> list[dict]:
    column = "l.landlord_id" if actor.role == "owner" else "c.renter_id"
    rows = repo.db.execute(f"SELECT c.*,i.period,l.room_id FROM hm_payment_claims c JOIN hm_invoices i ON i.id=c.invoice_id "
                           f"JOIN hm_leases l ON l.id=i.lease_id WHERE {column}=? ORDER BY c.created_at DESC", (actor.id,))
    return [dict(row) for row in rows]


def invoice_document(item: dict, room_title: str) -> str:
    esc = html.escape
    rows = "".join(f"<tr><td>{esc(line['label'])}</td><td>{esc(line['quantity'])}</td>"
                   f"<td>{money(int(Decimal(line['unit_price'])))}</td><td>{money(line['amount_vnd'])}</td></tr>"
                   for line in item["lines"])
    return f"""<article class="document"><h1>HÓA ĐƠN TIỀN PHÒNG KỲ {esc(item['period'])}</h1>
<p>Mã hóa đơn: {esc(item['id'])} · Phòng: {esc(room_title)} · Bên thuê: {esc(item['renter_id'])}</p>
<table><thead><tr><th>Khoản</th><th>Số lượng</th><th>Đơn giá</th><th>Thành tiền</th></tr></thead>
<tbody>{rows}</tbody></table>
<p><strong>Tổng cộng:</strong> {money(item['total_vnd'])} · Đã thu: {money(item['paid_vnd'])} ·
Còn lại: {money(item['balance_vnd'])} · Hạn thanh toán: {esc(item['due_date'])}</p></article>"""


def receipt_document(item: dict, payment: dict) -> str:
    esc = html.escape
    method = "Chuyển khoản" if payment["method"] == "transfer" else "Tiền mặt"
    return f"""<article class="document"><h1>BIÊN LAI THU TIỀN</h1>
<p>Số biên lai: {esc(payment['receipt_no'])} · Ngày: {esc(payment['recorded_at'][:10])}</p>
<p>Đã nhận của {esc(item['renter_id'])} số tiền {money(payment['amount_vnd'])} ({method}) cho hóa đơn kỳ
{esc(item['period'])} (mã {esc(item['id'])}).</p>
<p>Người thu: {esc(payment['recorded_by'])} · Tham chiếu: {esc(payment['reference'] or '—')}</p></article>"""


def billing_summary(repo, landlord_id: str) -> dict:
    by_period: dict[str, dict] = {}
    for item in invoices(repo, Actor(id=landlord_id, role="owner")):
        row = by_period.setdefault(item["period"], {"period": item["period"], "billed_vnd": 0, "collected_vnd": 0,
                                                    "outstanding_vnd": 0, "overdue_invoices": 0})
        row["billed_vnd"] += item["total_vnd"]
        row["collected_vnd"] += item["paid_vnd"]
        row["outstanding_vnd"] += item["balance_vnd"]
        row["overdue_invoices"] += int(item["overdue"])
    return {"periods": sorted(by_period.values(), key=lambda row: row["period"], reverse=True)}


# ---------------------------------------------------------------- maintenance

def ticket(repo, ticket_id: str) -> dict:
    row = repo.db.execute("SELECT * FROM hm_maintenance WHERE id=?", (ticket_id,)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy yêu cầu sửa chữa.", 404)
    item = dict(row)
    item["timeline"] = json.loads(item.pop("timeline_json"))
    return item


def tickets(repo, actor) -> list[dict]:
    column = "landlord_id" if actor.role == "owner" else "renter_id"
    rows = repo.db.execute(f"SELECT id FROM hm_maintenance WHERE {column}=? ORDER BY updated_at DESC", (actor.id,))
    return [ticket(repo, row["id"]) for row in rows]


def create_ticket(repo, room, renter_id: str, data: TicketInput) -> dict:
    active = repo.db.execute("SELECT id FROM hm_leases WHERE room_id=? AND renter_id=? AND status='active'",
                             (room.id, renter_id)).fetchone()
    if active is None:
        raise DomainError("no_active_lease", "Chỉ người đang thuê phòng mới gửi được yêu cầu sửa chữa.", 403)
    now = utc_now()
    ticket_id = str(uuid4())
    timeline = [{"at": now, "by": renter_id, "status": "submitted", "note": data.title}]
    with repo.db:
        repo.db.execute("INSERT INTO hm_maintenance VALUES(?,?,?,?,?,?,?,?,'submitted',NULL,NULL,?,?,?)",
                        (ticket_id, room.id, active["id"], renter_id, room.landlord, data.title, data.description,
                         data.priority, json.dumps(timeline, ensure_ascii=False), now, now))
    return ticket(repo, ticket_id)


def update_ticket(repo, item: dict, actor, data: TicketUpdate) -> dict:
    status = data.status
    if status:
        renter_moves = {"closed", "reopened"}
        if (actor.role == "renter") != (status in renter_moves):
            raise DomainError("forbidden", "Vai trò không được chuyển yêu cầu sang trạng thái này.", 403)
        if status not in TICKET_TRANSITIONS[item["status"]]:
            raise DomainError("ticket_state", f"Không chuyển được từ {item['status']} sang {status}.", 409)
        if status == "reopened" and not data.note:
            raise DomainError("note_required", "Cần ghi lý do mở lại.", 422)
    if actor.role == "renter" and (data.assignee is not None or data.cost_vnd is not None):
        raise DomainError("forbidden", "Người thuê không phân công hoặc ghi chi phí.", 403)
    timeline = item["timeline"] + [{"at": utc_now(), "by": actor.id, "status": status or item["status"],
                                    "note": data.note, "assignee": data.assignee, "cost_vnd": data.cost_vnd}]
    with repo.db:
        repo.db.execute("UPDATE hm_maintenance SET status=?,assignee=COALESCE(?,assignee),cost_vnd=COALESCE(?,cost_vnd),"
                        "timeline_json=?,updated_at=? WHERE id=?",
                        (status or item["status"], data.assignee, data.cost_vnd,
                         json.dumps(timeline, ensure_ascii=False), utc_now(), item["id"]))
    return ticket(repo, item["id"])


# ---------------------------------------------------------------- CRM

def touch_lead(repo, landlord_id: str, renter_id: str, room_id: str, source: str, stage_floor: str = "new"):
    """Event-driven pipeline: interest points accumulate, the stage only moves forward (never past won/lost)."""
    now = utc_now()
    row = repo.db.execute("SELECT * FROM hm_leads WHERE landlord_id=? AND renter_id=? AND room_id=?",
                          (landlord_id, renter_id, room_id)).fetchone()
    with repo.db:
        if row is None:
            repo.db.execute("INSERT INTO hm_leads(id,landlord_id,renter_id,room_id,stage,score,sources_json,created_at,"
                            "updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (str(uuid4()), landlord_id, renter_id, room_id, stage_floor, LEAD_POINTS.get(source, 0),
                             json.dumps([source]), now, now))
            return
        stage = row["stage"]
        if stage not in ("won", "lost") and LEAD_STAGES.index(stage_floor) > LEAD_STAGES.index(stage):
            stage = stage_floor
        sources = json.loads(row["sources_json"])
        repo.db.execute("UPDATE hm_leads SET stage=?,score=score+?,sources_json=?,updated_at=? WHERE id=?",
                        (stage, LEAD_POINTS.get(source, 0), json.dumps(sorted(set(sources) | {source})), now, row["id"]))


def leads(repo, landlord_id: str) -> list[dict]:
    rows = repo.db.execute("SELECT * FROM hm_leads WHERE landlord_id=? ORDER BY score DESC,updated_at DESC",
                           (landlord_id,))
    result = []
    for row in rows:
        item = dict(row)
        item["sources"] = json.loads(item.pop("sources_json"))
        item["interest"] = "hot" if item["score"] >= 8 else "warm" if item["score"] >= 3 else "cold"
        result.append(item)
    return result


def update_lead(repo, landlord_id: str, lead_id: str, data: LeadUpdate) -> dict:
    row = repo.db.execute("SELECT id FROM hm_leads WHERE id=? AND landlord_id=?", (lead_id, landlord_id)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy khách tiềm năng.", 404)
    with repo.db:
        repo.db.execute("UPDATE hm_leads SET stage=COALESCE(?,stage),notes=COALESCE(?,notes),updated_at=? WHERE id=?",
                        (data.stage, data.notes, utc_now(), lead_id))
    return next(item for item in leads(repo, landlord_id) if item["id"] == lead_id)


# ---------------------------------------------------------------- dashboard & analytics

def dashboard(repo, rooms: list, landlord_id: str, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    own = [room for room in rooms if room.landlord == landlord_id]
    rented = sum(room.occupancy == "rented" for room in own)
    deposited = sum(room.occupancy == "deposited" for room in own)
    month = today.strftime("%Y-%m")
    actor = Actor(id=landlord_id, role="owner")
    bills = invoices(repo, actor)
    revenue = repo.db.execute("SELECT COALESCE(SUM(p.amount_vnd),0) AS v FROM hm_payments p JOIN hm_invoices i "
                              "ON i.id=p.invoice_id JOIN hm_leases l ON l.id=i.lease_id WHERE l.landlord_id=? "
                              "AND substr(p.recorded_at,1,7)=?", (landlord_id, month)).fetchone()["v"]
    week = (today + timedelta(days=7)).isoformat()
    upcoming = repo.db.execute("SELECT COUNT(*) AS n FROM hm_viewings WHERE landlord_id=? AND status='confirmed' "
                               "AND requested_at>=? AND requested_at<=?", (landlord_id, today.isoformat(), week)
                               ).fetchone()["n"]
    ending = repo.db.execute("SELECT COUNT(*) AS n FROM hm_leases WHERE landlord_id=? AND status='active' AND end_date<=?",
                             (landlord_id, (today + timedelta(days=30)).isoformat())).fetchone()["n"]
    open_tickets = repo.db.execute("SELECT COUNT(*) AS n FROM hm_maintenance WHERE landlord_id=? AND status NOT IN "
                                   "('resolved','closed')", (landlord_id,)).fetchone()["n"]
    pending_claims = sum(claim["status"] == "pending" for claim in claims(repo, actor))
    return {"rooms": len(own), "rented": rented, "deposited": deposited, "vacant": len(own) - rented - deposited,
            "occupancy_rate": round(rented / len(own), 3) if own else None,
            "revenue_month_vnd": revenue, "month": month,
            "outstanding_vnd": sum(item["balance_vnd"] for item in bills),
            "overdue_invoices": sum(item["overdue"] for item in bills),
            "upcoming_viewings": upcoming, "leases_ending_30d": ending, "open_tickets": open_tickets,
            "pending_payment_claims": pending_claims,
            "notice": "Số liệu tính từ dữ liệu trong hệ thống (tin, hợp đồng, hóa đơn, phiếu thu)."}


def analytics(repo, rooms: list, landlord_id: str) -> dict:
    result = []
    for room in (room for room in rooms if room.landlord == landlord_id):
        views = repo.db.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT user_id) AS u FROM hm_room_views WHERE room_id=?",
                                (room.id,)).fetchone()
        viewings = repo.db.execute("SELECT COUNT(*) AS n, SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS c "
                                   "FROM hm_viewings WHERE room_id=?", (room.id,)).fetchone()
        won = repo.db.execute("SELECT COUNT(*) AS n FROM hm_leases WHERE room_id=? AND status IN ('active','ended')",
                              (room.id,)).fetchone()["n"]
        revenue = repo.db.execute("SELECT COALESCE(SUM(p.amount_vnd),0) AS v FROM hm_payments p JOIN hm_invoices i "
                                  "ON i.id=p.invoice_id JOIN hm_leases l ON l.id=i.lease_id WHERE l.room_id=?",
                                  (room.id,)).fetchone()["v"]
        requested = viewings["n"] or 0
        result.append({"room_id": room.id, "title": room.title.split(". ")[0], "views": views["n"],
                       "unique_viewers": views["u"], "viewings_requested": requested,
                       "viewings_confirmed": viewings["c"] or 0, "leases_won": won, "revenue_vnd": revenue,
                       "view_to_viewing": round(requested / views["n"], 3) if views["n"] else None,
                       "viewing_to_lease": round(won / requested, 3) if requested else None})
    return {"rooms": sorted(result, key=lambda row: (-row["views"], row["room_id"]))}
