from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.models import Actor, CatalogStatus

OWNER = Actor(id="owner-a", role="owner")


def free_room(service):
    return next(room for room in service.catalog.rooms() if room.published and room.available)


def kinds(service, user):
    return [item["kind"] for item in service.notifications(user)["items"]]


def test_viewing_events_notify_landlord_then_renter_once(service, renter):
    room = free_room(service)
    when = datetime.now(timezone.utc) + timedelta(hours=5)
    viewing = service.request_listing_viewing(renter, room.id, when, "k1")
    service.request_listing_viewing(renter, room.id, when, "k1")  # replay
    assert kinds(service, OWNER) == ["viewing_requested"]
    service.respond_viewing(viewing["id"], OWNER, "confirmed")
    assert kinds(service, renter) == ["viewing_confirmed"]
    # Reminder job: confirmed viewing within 24h reminds both sides, and re-running never duplicates.
    first = service.run_jobs()
    second = service.run_jobs()
    assert first["viewing_reminders"] == 2 and second["viewing_reminders"] == 0
    assert kinds(service, renter).count("viewing_reminder") == 1


def test_room_status_and_price_changes_reach_engaged_renters(service, renter):
    room = free_room(service)
    service.listing(room.id, renter)
    service.change_room_status(room.id, OWNER, CatalogStatus(expected_revision=room.revision, occupancy="deposited"))
    items = service.notifications(renter)["items"]
    assert items[0]["kind"] == "room_changed" and "đã có người cọc" in items[0]["body"]
    assert service.notifications(Actor(id="renter-b", role="renter"))["unread"] == 0


def test_lead_reengagement_suggests_similar_vacant_rooms_once(service, renter):
    room = free_room(service)
    service.listing(room.id, renter)
    later = datetime.now(timezone.utc) + timedelta(days=2)
    assert service.run_jobs(later)["lead_reengagement"] == 1
    assert service.run_jobs(later)["lead_reengagement"] == 0
    note = next(item for item in service.notifications(renter)["items"] if item["kind"] == "lead_reengagement")
    assert "Gợi ý tương đương" in note["body"]
    # A renter who booked a viewing for the room is not chased.
    other = Actor(id="renter-b", role="renter")
    service.listing(room.id, other)
    service.request_listing_viewing(other, room.id, later + timedelta(days=1), "kb")
    service.run_jobs(later + timedelta(days=1))
    assert "lead_reengagement" not in kinds(service, other)


def test_notification_routes_mark_read_and_admin_runs_jobs(service, renter):
    room = free_room(service)
    service.listing(room.id, renter)
    service.change_room_status(room.id, OWNER, CatalogStatus(expected_revision=room.revision, published=False))
    with TestClient(create_app(lambda: service)) as client:
        headers = {"Authorization": "Bearer demo-renter-a"}
        listed = client.get("/notifications", headers=headers).json()
        assert listed["unread"] == 1
        assert client.post("/notifications/read", headers=headers).json()["unread"] == 0
        admin = {"Authorization": "Bearer demo-admin-a"}
        assert client.post("/admin/jobs/run", headers=headers).status_code == 403
        run = client.post("/admin/jobs/run", headers=admin).json()
        assert "lead_reengagement" in run
        assert client.get("/admin/jobs", headers=admin).json()[0]["summary"] is not None
