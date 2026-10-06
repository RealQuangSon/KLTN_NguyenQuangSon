import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.catalog import DEFAULT_CATALOG
from backend.app.models import (Actor, CatalogStatus, DomainError, Profile, Review, RoomInput, RoomUpdate,
                                Scenario)
from backend.app.service import HomeMatchService

DEMO = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))["rooms"]
OWNER_A, OWNER_B = Actor(id="owner-a", role="owner"), Actor(id="owner-b", role="owner")


@pytest.fixture
def two_landlords(tmp_path, monkeypatch):
    """Quận 7 demo rooms split between owner-a and owner-b, stored so landlords can edit."""
    rooms = [{**room, "landlord_id": "owner-b" if index % 2 else "owner-a"} for index, room in enumerate(DEMO)]
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps({"rooms": rooms}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", str(path))
    service = HomeMatchService(tmp_path / "ledger.sqlite")
    yield service
    service.close()


def approve(version=1, key="k", **changes):
    return Review(decision="approve", expected_profile_version=version, reason="Đã kiểm tra.",
                  idempotency_key=key, **changes)


def shortlist(service, renter):
    profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=5_000_000, scenario=Scenario())
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    return sid, run_id


def test_each_landlord_sees_and_reviews_only_own_rooms(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    run = two_landlords.repo.run(run_id)
    assert {item["landlord_id"] for item in run["items"]} == {"owner-a", "owner-b"}
    for landlord in (OWNER_A, OWNER_B):
        view = two_landlords.draft(run_id, landlord)
        assert view["items"] and all(item["landlord_id"] == landlord.id for item in view["items"])
        assert view["review_progress"] == {"landlords": 2, "decided": 0}
    with pytest.raises(DomainError):
        two_landlords.draft(run_id, Actor(id="owner-c", role="owner"))
    other = [item["room_id"] for item in run["items"] if item["landlord_id"] == "owner-b"]
    with pytest.raises(DomainError) as foreign:
        two_landlords.review(run_id, OWNER_A, approve(keep_room_ids=other[:1]))
    assert foreign.value.code == "invalid_selection"


def test_rooms_appear_as_each_landlord_approves_and_order_stays_in_own_slots(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    agent_order = [item["room_id"] for item in two_landlords.repo.run(run_id)["items"]]
    a_rooms = [room for room in agent_order if two_landlords.catalog.room(room).landlord == "owner-a"]
    b_rooms = [room for room in agent_order if room not in a_rooms]
    first = two_landlords.review(run_id, OWNER_A, approve(keep_room_ids=a_rooms[::-1],
                                                          override_reason="Khách thích căn rẻ hơn."))
    assert first["status"] == "partially_published"
    partial = two_landlords.results(sid, renter)
    assert partial["status"] == "partially_published"
    assert [item["room_id"] for item in partial["results"]] == a_rooms[::-1]
    # owner-b removes one room: the remaining rooms keep owner-b's slots in the agent order.
    final = two_landlords.review(run_id, OWNER_B, approve(keep_room_ids=b_rooms[1:],
                                                          override_reason="Phòng đầu đang sửa."))
    assert final["status"] == "published"
    visible = [item["room_id"] for item in two_landlords.results(sid, renter)["results"]]
    assert set(visible) == set(a_rooms) | set(b_rooms[1:])
    a_positions = [index for index, room in enumerate(visible) if room in a_rooms]
    assert [visible[i] for i in a_positions] == a_rooms[::-1]


def test_all_rejections_end_the_run_and_landlord_cannot_decide_twice(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    reject = Review(decision="reject", expected_profile_version=1, reason="Hết phòng.", idempotency_key="r")
    two_landlords.review(run_id, OWNER_A, reject)
    with pytest.raises(DomainError) as twice:
        two_landlords.review(run_id, OWNER_A, approve())
    assert twice.value.code == "review_conflict"
    assert two_landlords.results(sid, renter)["results"] == []
    two_landlords.review(run_id, OWNER_B, reject)
    assert two_landlords.results(sid, renter)["status"] == "rejected"


def test_landlord_creates_edits_and_sets_occupancy_of_own_rooms_only(two_landlords):
    quote = DEMO[0]["quote"]
    created = two_landlords.create_room(OWNER_A, RoomInput(
        title="Studio mới Quận 7", city="TP.HCM", area="Quận 7", room_type="studio", area_m2=28,
        capacity=2, published=True, occupancy="vacant", quote=quote, house_rules="Cổng đóng 23:00."))["room"]
    assert created["landlord_id"] == "owner-a" and created["available"] is True and created["revision"] == 1
    assert created["id"] in {room["id"] for room in two_landlords.rooms(OWNER_A)["rooms"]}
    assert created["id"] not in {room["id"] for room in two_landlords.rooms(OWNER_B)["rooms"]}
    editable = {key: created[key] for key in RoomInput.model_fields}
    edit = RoomUpdate.model_validate({**editable, "expected_revision": 1, "title": "Studio mới Quận 7 (đã sửa)"})
    updated = two_landlords.update_room(created["id"], OWNER_A, edit)["room"]
    assert updated["revision"] == 2 and updated["title"].endswith("(đã sửa)")
    with pytest.raises(DomainError) as stale:
        two_landlords.update_room(created["id"], OWNER_A, edit)
    assert stale.value.code == "catalog_conflict"
    with pytest.raises(DomainError) as foreign:
        two_landlords.change_room_status(created["id"], OWNER_B, CatalogStatus(expected_revision=2, published=False))
    assert foreign.value.code == "not_found"
    rented = two_landlords.change_room_status(created["id"], OWNER_A,
                                              CatalogStatus(expected_revision=2, occupancy="rented"))["room"]
    assert rented["occupancy"] == "rented" and rented["available"] is False


def test_online_viewing_goes_to_the_rooms_landlord_with_a_meeting_link(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    for landlord in (OWNER_A, OWNER_B):
        two_landlords.review(run_id, landlord, approve())
    room = two_landlords.results(sid, renter)["results"][0]
    when = datetime.now(timezone.utc) + timedelta(days=1)
    viewing = two_landlords.request_viewing(sid, renter, room["room_id"], when, "v1", mode="online")
    assert viewing["landlord_id"] == room["landlord_id"] and viewing["meeting_url"].startswith("https://meet.jit.si/")
    other = OWNER_B if room["landlord_id"] == "owner-a" else OWNER_A
    with pytest.raises(DomainError):
        two_landlords.respond_viewing(viewing["id"], other, "confirmed")
    owner = Actor(id=room["landlord_id"], role="owner")
    assert [item["id"] for item in two_landlords.viewings(owner)] == [viewing["id"]]
    assert two_landlords.respond_viewing(viewing["id"], owner, "confirmed")["status"] == "confirmed"
