"""BE-07: landlord promotions (hm_promotions).

A promotion is owner-only data with a bounded validity window; text is
PII-masked before storage; expired promotions disappear from both the DTOs and
the lead re-engagement notification, while the dedup key and — crucially — the
deterministic ranking stay untouched (ranking must never read hm_promotions).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.automation import similar_rooms
from backend.app.main import create_app
from backend.app.promotions import today_vn

OWNER_A = {"Authorization": "Bearer demo-owner-a"}
OWNER_B = {"Authorization": "Bearer demo-owner-b"}
RENTER_A = {"Authorization": "Bearer demo-renter-a"}


@pytest.fixture
def client(service):
    with TestClient(create_app(lambda: service)) as test_client:
        yield test_client


def free_room(service):
    return next(room for room in service.catalog.rooms() if room.published and room.available)


def put_promotion(client, room_id, text="Giảm giá tháng đầu", valid_until=None, headers=OWNER_A):
    return client.put(f"/landlord/rooms/{room_id}/promotion", headers=headers,
                      json={"text": text, "valid_until": (valid_until or today_vn()).isoformat()})


def reengagement_note(service, renter):
    items = service.notifications(renter)["items"]
    return next(item for item in items if item["kind"] == "lead_reengagement")


def test_put_promotion_reaches_reengagement_notification_with_same_dedup(client, service, renter):
    viewed = free_room(service)
    service.listing(viewed.id, renter)
    suggested = similar_rooms(service.catalog.rooms(), viewed)[0][0]
    until = today_vn() + timedelta(days=30)
    created = put_promotion(client, suggested.id, text="Giảm giá tháng đầu", valid_until=until)
    assert created.status_code == 200, created.text
    assert created.json() == {"room_id": suggested.id, "text": "Giảm giá tháng đầu",
                              "valid_until": until.isoformat()}
    later = datetime.now(timezone.utc) + timedelta(days=2)
    assert service.run_jobs(later)["lead_reengagement"] == 1
    note = reengagement_note(service, renter)
    assert f"Ưu đãi: Giảm giá tháng đầu (đến {until:%d/%m})" in note["body"]
    # The dedup key stays exactly as before promotions existed: no double sends.
    assert service.run_jobs(later)["lead_reengagement"] == 0
    assert len(service.notifications(renter)["items"]) == 1


def test_expired_promotion_is_absent_from_dto_and_notification(client, service, renter):
    viewed = free_room(service)
    service.listing(viewed.id, renter)
    suggested = similar_rooms(service.catalog.rooms(), viewed)[0][0]
    until = today_vn() + timedelta(days=1)
    assert put_promotion(client, suggested.id, valid_until=until).status_code == 200
    # Time passes: the promotion quietly expires.
    yesterday = (today_vn() - timedelta(days=1)).isoformat()
    with service.repo.db:
        service.repo.db.execute("UPDATE hm_promotions SET valid_until=?", (yesterday,))
    assert client.get(f"/listings/{suggested.id}").json()["promotion"] is None
    search = client.get("/listings", params={"city": suggested.city}).json()
    target = next(item for item in search["items"] if item["id"] == suggested.id)
    assert target["promotion"] is None
    later = datetime.now(timezone.utc) + timedelta(days=2)
    assert service.run_jobs(later)["lead_reengagement"] == 1
    assert "Ưu đãi" not in reengagement_note(service, renter)["body"]


def test_promotion_shows_on_listing_and_landlord_dtos_and_delete_clears_it(client, service):
    room = free_room(service)
    until = today_vn() + timedelta(days=14)
    assert put_promotion(client, room.id, valid_until=until).status_code == 200
    detail = client.get(f"/listings/{room.id}").json()
    assert detail["promotion"] == {"text": "Giảm giá tháng đầu", "valid_until": until.isoformat()}
    search = client.get("/listings", params={"city": room.city, "area": room.area}).json()
    target = next(item for item in search["items"] if item["id"] == room.id)
    assert target["promotion"]["text"] == "Giảm giá tháng đầu"
    own = client.get(f"/landlord/rooms/{room.id}", headers=OWNER_A).json()["room"]
    assert own["promotion"]["valid_until"] == until.isoformat()
    deleted = client.delete(f"/landlord/rooms/{room.id}/promotion", headers=OWNER_A)
    assert deleted.status_code == 204
    assert client.get(f"/listings/{room.id}").json()["promotion"] is None
    assert client.delete(f"/landlord/rooms/{room.id}/promotion", headers=OWNER_A).status_code == 404


def test_non_owners_get_404_and_renters_403(client):
    assert put_promotion(client, "demo-01", headers=OWNER_B).status_code == 404
    assert client.delete("/landlord/rooms/demo-01/promotion", headers=OWNER_B).status_code == 404
    assert put_promotion(client, "room-0000000000", headers=OWNER_A).status_code == 404
    assert put_promotion(client, "demo-01", headers=RENTER_A).status_code == 403
    assert client.delete("/landlord/rooms/demo-01/promotion", headers=RENTER_A).status_code == 403


def test_invalid_window_and_blank_text_are_rejected(client):
    yesterday = today_vn() - timedelta(days=1)
    past = put_promotion(client, "demo-01", valid_until=yesterday)
    assert past.status_code == 422 and past.json()["error"]["code"] == "invalid_promotion"
    too_far = today_vn() + timedelta(days=91)
    far = put_promotion(client, "demo-01", valid_until=too_far)
    assert far.status_code == 422 and far.json()["error"]["code"] == "invalid_promotion"
    assert put_promotion(client, "demo-01", valid_until=today_vn() + timedelta(days=90)).status_code == 200
    blank = put_promotion(client, "demo-01", text="   ")
    assert blank.status_code == 422
    missing = client.put("/landlord/rooms/demo-01/promotion", headers=OWNER_A,
                         json={"text": "Chỉ có text"})
    assert missing.status_code == 422


def test_phone_number_and_email_in_text_are_masked(client):
    response = put_promotion(client, "demo-01", text="Gọi 0912345678 hoặc mail abc@gmail.com để xem nhà")
    assert response.status_code == 200, response.text
    text = response.json()["text"]
    assert "0912345678" not in text and "abc@gmail.com" not in text
    assert "[SĐT đã che]" in text and "[email đã che]" in text
    # The stored and served copies are masked as well.
    assert client.get("/listings/demo-01").json()["promotion"]["text"] == text


def ranked_room_ids(service, renter, profile):
    """The run's own ranked room_ids (pre-review order), as in diagnostics."""
    session = service.create_session(renter)
    service.confirm(session["session_id"], renter, profile, 0)
    run = service.repo.run(service.repo.session(session["session_id"])["active_run_id"])
    return [item["room_id"] for item in run["items"]]


def test_ranking_is_identical_with_and_without_promotion(client, service, renter, profile):
    ids_without = ranked_room_ids(service, renter, profile)
    assert ids_without  # the fixture profile matches demo rooms
    until = today_vn() + timedelta(days=30)
    for room_id in ids_without:  # promotions on every visible room, plus an unseen one
        assert put_promotion(client, room_id, valid_until=until).status_code == 200
    assert put_promotion(client, "demo-09", valid_until=until).status_code == 200
    ids_with = ranked_room_ids(service, renter, profile)
    assert ids_with == ids_without
