"""BE-04: handoff support ticket lifecycle (hm_support).

A renter creates a ticket from chat ("Tôi muốn gặp người thật"); only admins
list and transition tickets (requested → in_progress → resolved, with a
reopening edge back to in_progress). Every status change notifies the renter
exactly once per status via the notification dedup key.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def client(service):
    with TestClient(create_app(lambda: service)) as test_client:
        yield test_client


def renter_headers():
    return {"Authorization": "Bearer demo-renter"}


def admin_headers():
    return {"Authorization": "Bearer demo-admin"}


def owner_headers():
    return {"Authorization": "Bearer demo-owner2"}


def open_ticket(client):
    """Create a support ticket from the deterministic chat handoff path."""
    session = client.post("/sessions", headers=renter_headers())
    assert session.status_code == 201, session.text
    session_id = session.json()["session_id"]
    reply = client.post(f"/sessions/{session_id}/messages", headers=renter_headers(),
                        json={"text": "Tôi muốn gặp người thật"})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["status"] == "support_requested" and body["ticket_id"]
    return body["ticket_id"]


def renter_notifications(client):
    return client.get("/notifications", headers=renter_headers()).json()["items"]


def test_chat_creates_ticket_and_admin_sees_it(client):
    ticket_id = open_ticket(client)
    tickets = client.get("/admin/support-tickets", headers=admin_headers())
    assert tickets.status_code == 200
    ticket = next(item for item in tickets.json() if item["id"] == ticket_id)
    assert ticket["session_id"] and ticket["status"] == "requested"
    assert ticket["assignee"] is None and ticket["note"] is None
    assert ticket["created_at"] and ticket["updated_at"] is None and ticket["resolved_at"] is None
    # The status filter narrows the admin listing.
    pending = client.get("/admin/support-tickets", headers=admin_headers(),
                         params={"status": "requested"}).json()
    assert ticket_id in {item["id"] for item in pending}
    assert ticket_id not in {item["id"] for item in
                             client.get("/admin/support-tickets", headers=admin_headers(),
                                        params={"status": "resolved"}).json()}


def test_lifecycle_transitions_notify_renter_once_per_status(client, service):
    ticket_id = open_ticket(client)
    assert renter_notifications(client) == []
    started = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                           json={"status": "in_progress"})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    assert started.json()["assignee"] == "admin"  # the actor takes the ticket
    assert started.json()["updated_at"] is not None
    resolved = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                            json={"status": "resolved", "note": "Đã gọi điện hướng dẫn khách."})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["note"] == "Đã gọi điện hướng dẫn khách."
    assert resolved.json()["resolved_at"] is not None
    # The renter (session owner) got one notification per status, nothing more.
    items = renter_notifications(client)
    assert [item["kind"] for item in items] == ["support_update", "support_update"]
    dedup = [service.repo.db.execute("SELECT dedup_key FROM hm_notifications WHERE id=?",
                                     (item["id"],)).fetchone()["dedup_key"] for item in items]
    assert set(dedup) == {f"support:{ticket_id}:in_progress", f"support:{ticket_id}:resolved"}
    assert all(item["link"] == "/tro-ly-ai" for item in items)


def test_repeated_patch_is_idempotent_and_notifies_nothing(client):
    ticket_id = open_ticket(client)
    client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                 json={"status": "in_progress"})
    resolved = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                            json={"status": "resolved", "note": "Đã xử lý xong."})
    again = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                         json={"status": "resolved", "note": "Đã xử lý xong."})
    assert again.status_code == 200 and again.json() == resolved.json()
    # Replaying the current status never writes or re-notifies (also on a fresh ticket).
    assert len(renter_notifications(client)) == 2
    fresh = open_ticket(client)
    replay = client.patch(f"/admin/support-tickets/{fresh}", headers=admin_headers(),
                          json={"status": "requested"})
    assert replay.status_code == 200 and replay.json()["status"] == "requested"
    assert replay.json()["updated_at"] is None
    assert len(renter_notifications(client)) == 2


def test_resolving_without_note_is_rejected_and_wrong_transition_conflicts(client):
    ticket_id = open_ticket(client)
    started = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                           json={"status": "in_progress"})
    missing = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                           json={"status": "resolved"})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "note_required"
    blank = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                         json={"status": "resolved", "note": "   "})
    assert blank.status_code == 422 and blank.json()["error"]["code"] == "note_required"
    wrong = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                         json={"status": "requested"})
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "ticket_state"
    # Reopening a resolved ticket is legal; resolving again needs no second note re-check failure.
    client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                 json={"status": "resolved", "note": "Nội dung xử lý."})
    reopened = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                            json={"status": "in_progress"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "in_progress"
    assert reopened.json()["resolved_at"] is None
    resolved_again = client.patch(f"/admin/support-tickets/{ticket_id}", headers=admin_headers(),
                                  json={"status": "resolved", "note": "Xử lý lần hai."})
    assert resolved_again.status_code == 200 and resolved_again.json()["status"] == "resolved"


def test_only_admin_can_list_or_transition_support_tickets(client):
    ticket_id = open_ticket(client)
    # The legacy landlord-facing listing is gone: owner lost support:list.
    assert client.get("/support-tickets", headers=owner_headers()).status_code == 403
    for headers in (owner_headers(), renter_headers()):
        assert client.get("/support-tickets", headers=headers).status_code == 403
        assert client.get("/admin/support-tickets", headers=headers).status_code == 403
        patch = client.patch(f"/admin/support-tickets/{ticket_id}", headers=headers,
                             json={"status": "in_progress"})
        assert patch.status_code == 403
    assert client.get("/admin/support-tickets").status_code == 401
    missing = client.patch("/admin/support-tickets/no-such-ticket", headers=admin_headers(),
                           json={"status": "in_progress"})
    assert missing.status_code == 404
    # The ticket stays untouched after all the denied attempts.
    tickets = client.get("/admin/support-tickets", headers=admin_headers()).json()
    assert next(item for item in tickets if item["id"] == ticket_id)["status"] == "requested"
