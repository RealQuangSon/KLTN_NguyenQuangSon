from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app import pms
from backend.app.main import create_app
from backend.app.models import Actor, DomainError

OWNER = Actor(id="owner-a", role="owner")
OTHER_OWNER = Actor(id="owner-b", role="owner")


@pytest.fixture
def accounts(service):
    with service.repo.db:
        for user, role in (("renter-a", "renter"), ("renter-b", "renter"), ("owner-a", "owner")):
            service.repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,?,?) "
                                    "ON CONFLICT(id) DO NOTHING", (user, role, "unused"))
    return service


def active_lease(service, renter, room_id="demo-01", start=date(2026, 10, 1), months=6):
    lease = service.create_lease(OWNER, pms.LeaseInput(renter_id=renter.id, room_id=room_id, start_date=start,
                                                       end_date=start + timedelta(days=30 * months),
                                                       occupants=2, vehicles=1))
    service.send_lease(OWNER, lease["id"])
    service.accept_lease(renter, lease["id"], lease["version"])
    return service.activate_lease(OWNER, lease["id"])


def test_lease_versioned_acceptance_activation_and_room_status(accounts, renter):
    service = accounts
    draft = service.create_lease(OWNER, pms.LeaseInput(renter_id="renter-a", room_id="demo-01",
                                                       start_date=date(2026, 10, 1), end_date=date(2027, 4, 1)))
    assert draft["status"] == "draft" and draft["rent_vnd"] == 2_500_000
    with pytest.raises(DomainError):
        service.lease(renter, draft["id"])  # drafts stay private to the landlord
    service.send_lease(OWNER, draft["id"])
    edited = service.update_lease(OWNER, draft["id"], pms.LeaseInput(
        renter_id="renter-a", room_id="demo-01", start_date=date(2026, 10, 1), end_date=date(2027, 4, 1),
        rent_vnd=2_600_000))
    assert edited["version"] == 2 and edited["status"] == "draft"
    service.send_lease(OWNER, draft["id"])
    with pytest.raises(DomainError) as stale:
        service.accept_lease(renter, draft["id"], 1)
    assert stale.value.code == "lease_version"
    service.accept_lease(renter, draft["id"], 2)
    active = service.activate_lease(OWNER, draft["id"])
    assert active["status"] == "active"
    room = service.catalog.room("demo-01")
    assert room.occupancy == "rented" and room.available is False
    with pytest.raises(DomainError) as overlap:
        service.create_lease(OWNER, pms.LeaseInput(renter_id="renter-b", room_id="demo-01",
                                                   start_date=date(2026, 12, 1), end_date=date(2027, 2, 1)))
    assert overlap.value.code == "lease_overlap"
    with pytest.raises(DomainError):
        service.create_lease(OTHER_OWNER, pms.LeaseInput(renter_id="renter-b", room_id="demo-02",
                                                         start_date=date(2027, 1, 1), end_date=date(2027, 6, 1)))
    assert "hợp đồng thuê phòng" in service.lease_document(renter, draft["id"])["html"].lower()
    kinds = [item["kind"] for item in service.notifications(renter)["items"]]
    assert {"lease_sent", "lease_active"} <= set(kinds)


def test_invoice_from_readings_matches_hand_calculation_and_is_immutable(accounts, renter):
    service = accounts
    lease = active_lease(service, renter)
    with pytest.raises(DomainError) as missing:
        service.issue_invoice(OWNER, lease["id"], pms.InvoiceInput(period="2026-10"))
    assert missing.value.code == "invoice_incomplete" and "chỉ số điện" in str(missing.value)
    service.record_reading(OWNER, lease["id"], pms.ReadingInput(period="2026-10", electricity_start=Decimal("1200"),
                                                               electricity_end=Decimal("1350")))
    invoice = service.issue_invoice(OWNER, lease["id"], pms.InvoiceInput(period="2026-10"))
    # 2.500.000 + 150 kWh × 3.000 + 2 người × 80.000 + 100.000 + 1 xe × 100.000 + 50.000
    assert invoice["total_vnd"] == 2_500_000 + 450_000 + 160_000 + 100_000 + 100_000 + 50_000 == 3_360_000
    assert invoice["due_date"] == "2026-10-05" and invoice["payment_status"] == "unpaid"
    with pytest.raises(DomainError) as twice:
        service.issue_invoice(OWNER, lease["id"], pms.InvoiceInput(period="2026-10"))
    assert twice.value.code == "invoice_exists"
    # Next period starts from last end reading; a decreasing meter is rejected.
    with pytest.raises(DomainError):
        service.record_reading(OWNER, lease["id"], pms.ReadingInput(period="2026-11", electricity_end=Decimal("1300")))
    reading = service.record_reading(OWNER, lease["id"], pms.ReadingInput(period="2026-11",
                                                                         electricity_end=Decimal("1400")))
    assert Decimal(str(reading["electricity_start"])) == 1350
    assert "HÓA ĐƠN" in service.invoice_document(renter, invoice["id"])["html"]


def test_payment_claim_reconciliation_receipt_and_debt(accounts, renter):
    service = accounts
    lease = active_lease(service, renter)
    service.record_reading(OWNER, lease["id"], pms.ReadingInput(period="2026-10", electricity_start=Decimal("0"),
                                                               electricity_end=Decimal("100")))
    invoice = service.issue_invoice(OWNER, lease["id"], pms.InvoiceInput(period="2026-10"))
    claim = service.claim_payment(renter, invoice["id"], pms.ClaimInput(amount_vnd=2_000_000, reference="CK 123"))
    assert service.invoice_detail(renter, invoice["id"])["paid_vnd"] == 0  # a claim is not a payment
    decided = service.decide_claim(OWNER, claim["id"], True)
    assert decided["payment"]["receipt_no"].startswith("BL-202610-")
    detail = service.invoice_detail(renter, invoice["id"])
    assert detail["payment_status"] == "partially_paid" and detail["balance_vnd"] == invoice["total_vnd"] - 2_000_000
    with pytest.raises(DomainError) as again:
        service.decide_claim(OWNER, claim["id"], True)
    assert again.value.code == "claim_decided"
    with pytest.raises(DomainError) as over:
        service.record_payment(OWNER, invoice["id"], pms.PaymentInput(amount_vnd=detail["balance_vnd"] + 1))
    assert over.value.code == "overpayment"
    paid = service.record_payment(OWNER, invoice["id"], pms.PaymentInput(amount_vnd=detail["balance_vnd"], method="cash"))
    assert service.invoice_detail(OWNER, invoice["id"])["payment_status"] == "paid"
    receipt = service.invoice_document(renter, invoice["id"], paid["receipt_no"])["html"]
    assert "BIÊN LAI" in receipt and paid["receipt_no"] in receipt
    summary = service.billing_summary(OWNER)["periods"][0]
    assert summary["billed_vnd"] == summary["collected_vnd"] and summary["outstanding_vnd"] == 0
    with pytest.raises(DomainError):
        service.invoice_detail(Actor(id="renter-b", role="renter"), invoice["id"])


def test_payment_and_renewal_reminders_run_once(accounts, renter):
    service = accounts
    start = datetime.now(timezone.utc).date() - timedelta(days=170)
    lease = active_lease(service, renter, start=start, months=6)
    period = start.strftime("%Y-%m")
    service.record_reading(OWNER, lease["id"], pms.ReadingInput(period=period, electricity_start=Decimal("0"),
                                                               electricity_end=Decimal("10")))
    service.issue_invoice(OWNER, lease["id"], pms.InvoiceInput(period=period))  # due long ago → overdue
    first, second = service.run_jobs(), service.run_jobs()
    assert first["payment_reminders"] == 2 and second["payment_reminders"] == 0
    assert first["lease_renewal_reminders"] == 2 and second["lease_renewal_reminders"] == 0
    renewal = service.renew_lease(OWNER, lease["id"], pms.LeaseRenewal(end_date=date.fromisoformat(lease["end_date"])
                                                                        + timedelta(days=180)))
    assert renewal["renewal_of"] == lease["id"] and renewal["start_date"] == lease["end_date"]


def test_termination_frees_the_room(accounts, renter):
    service = accounts
    lease = active_lease(service, renter)
    ended = service.terminate_lease(OWNER, lease["id"], pms.LeaseTermination(
        end_date=date(2026, 12, 31), settlement_note="Hoàn cọc đủ, không hư hỏng."))
    assert ended["status"] == "terminated" and service.catalog.room("demo-01").occupancy == "vacant"


def test_maintenance_requires_tenancy_and_follows_transitions(accounts, renter):
    service = accounts
    with pytest.raises(DomainError) as no_lease:
        service.create_ticket(renter, pms.TicketInput(room_id="demo-01", title="Hỏng vòi", description="Rò nước"))
    assert no_lease.value.code == "no_active_lease"
    active_lease(service, renter)
    ticket = service.create_ticket(renter, pms.TicketInput(room_id="demo-01", title="Hỏng vòi nước",
                                                           description="Vòi rò nước liên tục", priority="urgent"))
    assert ticket["landlord_id"] == "owner-a" and ticket["status"] == "submitted"
    assert service.notifications(OWNER)["items"][0]["kind"] == "maintenance_urgent"
    with pytest.raises(DomainError):
        service.update_ticket(renter, ticket["id"], pms.TicketUpdate(status="resolved"))
    service.update_ticket(OWNER, ticket["id"], pms.TicketUpdate(status="assigned", assignee="Thợ Minh"))
    service.update_ticket(OWNER, ticket["id"], pms.TicketUpdate(status="resolved", cost_vnd=150_000))
    with pytest.raises(DomainError) as reason:
        service.update_ticket(renter, ticket["id"], pms.TicketUpdate(status="reopened"))
    assert reason.value.code == "note_required"
    reopened = service.update_ticket(renter, ticket["id"], pms.TicketUpdate(status="reopened", note="Vẫn rò"))
    assert reopened["status"] == "reopened" and len(reopened["timeline"]) == 4
    with pytest.raises(DomainError):
        service.update_ticket(OTHER_OWNER, ticket["id"], pms.TicketUpdate(status="assigned"))


def test_lead_pipeline_dashboard_and_analytics(accounts, renter):
    service = accounts
    service.listing("demo-01", renter)
    service.start_conversation(renter, "demo-01")
    lead = service.leads(OWNER)[0]
    assert lead["stage"] == "contacted" and lead["interest"] == "warm" and set(lead["sources"]) == {"view", "chat"}
    active_lease(service, renter)
    lead = service.leads(OWNER)[0]
    assert lead["stage"] == "won" and lead["interest"] == "hot"
    assert service.update_lead(OWNER, lead["id"], pms.LeadUpdate(notes="Khách quen"))["notes"] == "Khách quen"
    dashboard = service.landlord_dashboard(OWNER)
    assert dashboard["rented"] == 1 and dashboard["rooms"] >= 1 and 0 < dashboard["occupancy_rate"] <= 1
    stats = next(row for row in service.landlord_analytics(OWNER)["rooms"] if row["room_id"] == "demo-01")
    assert stats["views"] == 1 and stats["leases_won"] == 1
    with pytest.raises(DomainError):
        service.landlord_dashboard(renter)


def test_pms_routes(accounts):
    service = accounts
    with TestClient(create_app(lambda: service)) as client:
        owner = {"Authorization": "Bearer demo-owner-a"}
        renter = {"Authorization": "Bearer demo-renter-a"}
        created = client.post("/landlord/leases", headers=owner, json={
            "renter_id": "renter-a", "room_id": "demo-01", "start_date": "2026-10-01", "end_date": "2027-04-01"})
        assert created.status_code == 201
        lease_id = created.json()["id"]
        assert client.post(f"/landlord/leases/{lease_id}/send", headers=owner).status_code == 200
        assert client.post(f"/leases/{lease_id}/accept", headers=renter, json={"expected_version": 1}).status_code == 200
        assert client.post(f"/landlord/leases/{lease_id}/activate", headers=owner).json()["status"] == "active"
        assert client.get("/landlord/dashboard", headers=renter).status_code == 403
        assert client.get("/landlord/dashboard", headers=owner).json()["rented"] == 1
        assert client.get("/leases", headers=renter).json()[0]["id"] == lease_id
