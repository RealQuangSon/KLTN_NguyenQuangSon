import sys

import pytest

from backend import manage
from backend.app.auth import SeedAuth, account_profile, update_account_profile
from backend.app.models import Actor

OWNER = Actor(id="owner2", role="owner")
RENTER = Actor(id="renter", role="renter")


def service_has_no_demo(service) -> bool:
    return not any("[DEMO]" in (item["terms"] or "") for item in service.leases(OWNER))


@pytest.fixture(autouse=True)
def public_off(monkeypatch):
    # The deployment guard must be deterministic even if the developer shell exports HOMEMATCH_PUBLIC.
    monkeypatch.setenv("HOMEMATCH_PUBLIC", "false")


@pytest.fixture
def seeded_users(service):
    SeedAuth(service.repo, service.lock)
    return service


def test_seed_demo_twice_is_idempotent_and_populates_pms(seeded_users):
    service = seeded_users
    first = manage.seed_demo(service)
    assert first["status"] == "seeded"
    leases = service.leases(OWNER)
    assert len(leases) == 1 and leases[0]["status"] == "active"
    assert "[DEMO]" in leases[0]["terms"]
    again = manage.seed_demo(service)
    assert again["status"] == "already_seeded"
    assert len(service.leases(OWNER)) == 1  # re-running never duplicates the scenario


def test_seed_demo_dashboard_shows_overdue_invoice(seeded_users):
    service = seeded_users
    manage.seed_demo(service)
    dashboard = service.landlord_dashboard(OWNER)
    assert dashboard["overdue_invoices"] >= 1
    assert dashboard["rented"] >= 1
    invoices = service.invoices(OWNER)
    assert len(invoices) == 2
    paid = next(item for item in invoices if item["payment_status"] == "paid")
    assert paid["balance_vnd"] == 0
    overdue = next(item for item in invoices if item["overdue"])
    assert overdue["balance_vnd"] > 0
    # The renter's claim on the overdue period stays pending: a claim is not a payment.
    claims = service.payment_claims(OWNER)
    assert len(claims) == 1 and claims[0]["status"] == "pending"
    assert service.invoice_detail(OWNER, overdue["id"])["paid_vnd"] == 0


def test_seed_demo_ticket_in_progress_and_conversation_with_two_messages(seeded_users):
    service = seeded_users
    manage.seed_demo(service)
    tickets = service.tickets(OWNER)
    assert len(tickets) == 1 and tickets[0]["status"] == "in_progress"
    conversations = service.conversations(OWNER)
    assert len(conversations) == 1
    all_messages = service.conversation_messages(OWNER, conversations[0]["id"])["messages"]
    # The module itself adds one system handover note on start; the scenario sends exactly two messages.
    thread = [message for message in all_messages if message["sender_role"] in ("renter", "owner")]
    assert len(thread) == 2
    assert all("[DEMO]" in message["body"] for message in thread)


def test_seed_demo_names_the_renter_without_overwriting(seeded_users):
    service = seeded_users
    manage.seed_demo(service)
    profile = account_profile(service.repo, RENTER.id)
    assert profile["display_name"] == manage.DEMO_RENTER_NAME
    assert profile["contact_phone"] is None and profile["email"] is None
    update_account_profile(service.repo, RENTER.id, {"display_name": "Tên tự đặt"})
    manage.seed_demo(service)
    assert account_profile(service.repo, RENTER.id)["display_name"] == "Tên tự đặt"


def test_seed_demo_refuses_public_mode(seeded_users, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_PUBLIC", "true")
    with pytest.raises(SystemExit) as stopped:
        manage.seed_demo(seeded_users)
    assert stopped.value.code != 0
    assert service_has_no_demo(seeded_users)


def test_seed_demo_command_refuses_public_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_DB_PATH", str(tmp_path / "public.sqlite"))
    monkeypatch.setenv("HOMEMATCH_PUBLIC", "true")
    monkeypatch.setattr(sys, "argv", ["manage.py", "seed-demo"])
    with pytest.raises(SystemExit) as stopped:
        manage.main()
    assert stopped.value.code != 0


def test_seed_demo_command_seeds_cleanly_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_DB_PATH", str(tmp_path / "cli.sqlite"))
    for command in ("setup", "seed-users", "seed-demo", "seed-demo"):
        monkeypatch.setattr(sys, "argv", ["manage.py", command])
        manage.main()  # the second seed-demo returns already_seeded and still exits 0
