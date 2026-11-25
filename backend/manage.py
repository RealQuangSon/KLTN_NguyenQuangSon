"""Explicit operator commands. Indexing requires --allow-live and may incur API costs."""
import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from backend.app import pms
from backend.app.catalog import Catalog, StoredCatalog
from backend.app.service import HomeMatchService
from backend.app.auth import SeedAuth, account_profile, update_account_profile
from backend.app.models import Actor
from backend.app.repository import Repository

# Every demo text carries this prefix; it also marks the seed as done (idempotency).
DEMO_MARKER = "[DEMO]"
# Display name of the demo renter; the viewing form prefills it (the phone is never stored on the account).
DEMO_RENTER_NAME = "Khách thuê demo"
DEMO_TERMS = ("1. [DEMO] Đây là hợp đồng mẫu do lệnh seed-demo tạo cho buổi demo, không phải hợp đồng thật.\n"
              "2. Bên thuê thanh toán tiền thuê và các khoản phí theo hóa đơn hằng tháng trước ngày thanh toán.\n"
              "3. Tiền cọc được hoàn sau khi bàn giao phòng, trừ các khoản hư hỏng hoặc nợ phí có biên bản.\n"
              "4. Bên nào chấm dứt trước hạn phải báo trước ít nhất 30 ngày.\n"
              "5. Bên thuê tuân thủ nội quy của nhà; bên cho thuê sửa chữa hư hỏng không do bên thuê gây ra.")


def _month_start(today: date, months_back: int) -> date:
    """First day of the month `months_back` months before today."""
    index = today.year * 12 + today.month - 1 - months_back
    return date(index // 12, index % 12 + 1, 1)


def _demo_room(service: HomeMatchService, owner: Actor):
    """One vacant, published TP.HCM room of owner2 whose fees are all billable."""
    def billable(room) -> bool:
        return all(fee.included_in_rent or fee.amount_vnd is not None for fee in room.quote.fees)
    rooms = [room for room in service.catalog.rooms()
             if room.landlord == owner.id and room.city == "TP.HCM" and room.published
             and room.occupancy in (None, "vacant") and billable(room)]
    return min(rooms, key=lambda room: room.id) if rooms else None


def seed_demo(service: HomeMatchService) -> dict:
    """Fill one vacant TP.HCM room of owner2 with a [DEMO]-tagged PMS scenario.

    Only HomeMatchService/pms methods are called (no raw SQL), so contract
    versioning, invoice immutability and balance checks stay enforced. Past
    dates come from explicit inputs (LeaseInput.start_date, reading/invoice
    periods), so no service validation is loosened. Idempotent: any owner2
    lease whose terms contain the [DEMO] marker skips the seeding cleanly.
    The demo renter also gets a display name (through the account-profile
    helper) when it has none.
    """
    if os.getenv("HOMEMATCH_PUBLIC", "false").strip().lower() == "true":
        # Deployment guard, not a business rule: demo data must never exist in a public deployment.
        raise SystemExit("seed-demo từ chối chạy khi HOMEMATCH_PUBLIC=true: "
                         "dữ liệu demo không được đưa vào môi trường công khai.")
    owner = Actor(id="owner2", role="owner")
    renter = Actor(id="renter", role="renter")
    # Name only, and only when the account has none, so a name the renter typed is never overwritten.
    if not account_profile(service.repo, renter.id)["display_name"]:
        update_account_profile(service.repo, renter.id, {"display_name": DEMO_RENTER_NAME})
    existing = next((item for item in service.leases(owner) if DEMO_MARKER in (item["terms"] or "")), None)
    if existing is not None:
        return {"status": "already_seeded", "lease_id": existing["id"], "room_id": existing["room_id"]}
    room = _demo_room(service, owner)
    if room is None:
        raise SystemExit("seed-demo không tìm thấy phòng trống, đã công khai ở TP.HCM của owner2 "
                         "với đủ định giá phí; hãy kiểm tra kho phòng.")
    today = datetime.now(timezone.utc).date()
    start = _month_start(today, 2)
    # 1. Contract lifecycle: create -> send -> renter accepts -> activate, starting two months ago.
    lease = service.create_lease(owner, pms.LeaseInput(
        renter_id=renter.id, room_id=room.id, start_date=start, end_date=start + timedelta(days=365),
        occupants=1, vehicles=1, terms=DEMO_TERMS))
    service.send_lease(owner, lease["id"])
    service.accept_lease(renter, lease["id"], lease["version"])
    service.activate_lease(owner, lease["id"])
    # 2. Two billing periods from meter readings; period 1 collected in full, period 2 overdue.
    periods = [start.strftime("%Y-%m"), _month_start(today, 1).strftime("%Y-%m")]
    service.record_reading(owner, lease["id"], pms.ReadingInput(
        period=periods[0], electricity_start=Decimal("1000"), electricity_end=Decimal("1150"),
        water_start=Decimal("50"), water_end=Decimal("54")))
    first = service.issue_invoice(owner, lease["id"], pms.InvoiceInput(period=periods[0]))
    service.record_payment(owner, first["id"], pms.PaymentInput(
        amount_vnd=first["total_vnd"], method="transfer",
        reference=f"{DEMO_MARKER} Chuyển khoản tiền thuê kỳ {periods[0]}"))
    service.record_reading(owner, lease["id"], pms.ReadingInput(
        period=periods[1], electricity_end=Decimal("1310"), water_end=Decimal("58")))
    second = service.issue_invoice(owner, lease["id"], pms.InvoiceInput(period=periods[1]))
    # 3. The renter claims a partial transfer for period 2; it stays unconfirmed (a claim is not a payment).
    service.claim_payment(renter, second["id"], pms.ClaimInput(
        amount_vnd=second["balance_vnd"] // 2,  # fixed demo amount; pms still owns every money rule
        reference=f"{DEMO_MARKER} Đã chuyển một phần tiền kỳ {periods[1]}"))
    # 4. One maintenance ticket, moved to in_progress by the landlord.
    ticket = service.create_ticket(renter, pms.TicketInput(
        room_id=room.id, title=f"{DEMO_MARKER} Vòi nước nhỏ giọt",
        description=f"{DEMO_MARKER} Vòi nước trong phòng bị nhỏ giọt liên tục, mong chủ nhà sửa giúp."))
    service.update_ticket(owner, ticket["id"], pms.TicketUpdate(
        status="in_progress", assignee=f"{DEMO_MARKER} Thợ Minh",
        note=f"{DEMO_MARKER} Đã nhận lịch, hẹn thợ đến kiểm tra trong tuần."))
    # 5. One conversation with two messages, stored through the conversations module (PII-masked rules apply).
    conversation = service.start_conversation(renter, room.id)
    service.send_conversation_message(renter, conversation["id"],
                                      f"{DEMO_MARKER} Chào anh, em nhận phòng rồi, cho em hỏi giờ giữ xe ạ?")
    service.send_conversation_message(owner, conversation["id"],
                                      f"{DEMO_MARKER} Chào em, em gửi xe ở tầng trệt và nhận thẻ từ bảo vệ nhé.")
    return {"status": "seeded", "lease_id": lease["id"], "room_id": room.id, "periods": periods}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command",
                        choices=["setup", "migrate", "import", "index", "seed-users", "seed-demo", "jobs"])
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--rotate-passwords", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "index" and not arguments.allow_live:
        parser.error("index requires --allow-live; embedding API calls may incur costs")
    storage = os.getenv("HOMEMATCH_DATABASE_URL") or os.getenv("HOMEMATCH_DB_PATH", ".local/homematch.sqlite")
    if arguments.command == "migrate":
        repo = Repository(storage)
        try:
            print(json.dumps({"status": "migrated", "schema_version": repo.schema_version,
                              "storage": "postgresql" if repo.db.postgres else "sqlite"}))
        finally:
            repo.close()
        return
    service = HomeMatchService(storage)
    try:
        if arguments.command == "seed-users":
            auth = SeedAuth(service.repo, service.lock)
            if arguments.rotate_passwords:
                auth.rotate_passwords()
            result = {"status": "seeded", "passwords_rotated": arguments.rotate_passwords}
        elif arguments.command == "seed-demo":
            result = seed_demo(service)
        elif arguments.command == "import":
            if not arguments.catalog or not isinstance(service.catalog, StoredCatalog):
                parser.error("import requires --catalog JSON and stored catalog")
            with service.lock:
                version = service.catalog.import_rooms(Catalog(arguments.catalog).rooms())
            result = {"catalog_version": version, "rooms": len(service.catalog.rooms())}
        elif arguments.command == "jobs":
            # Same idempotent automation run the API's background thread performs.
            result = service.run_jobs()
        elif arguments.command == "index":
            scorer = getattr(service.catalog, "semantic_scorer", None)
            if scorer is None:
                parser.error("index requires PostgreSQL and HOMEMATCH_EMBEDDING_MODE=openai")
            result = scorer.index()
        else:
            result = {"storage": "postgresql" if service.repo.db.postgres else "sqlite",
                      "schema_version": service.repo.schema_version, "rooms": len(service.catalog.rooms())}
        print(json.dumps(result, ensure_ascii=False))
    finally:
        service.close()


if __name__ == "__main__":
    main()
