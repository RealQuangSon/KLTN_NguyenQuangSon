import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.catalog import DEFAULT_CATALOG
from backend.app.main import create_app
from backend.app.models import Actor, CatalogStatus, DomainError, Profile, RoomInput, RoomUpdate, Scenario
from backend.app.service import HomeMatchService

DEMO = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))["rooms"]
OWNER_2, OWNER_B = Actor(id="owner2", role="owner"), Actor(id="owner3", role="owner")


@pytest.fixture
def two_landlords(tmp_path, monkeypatch):
    """Quận 7 demo rooms split between owner2 and owner3, stored so landlords can edit."""
    rooms = [{**room, "landlord_id": "owner3" if index % 2 else "owner2"} for index, room in enumerate(DEMO)]
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps({"rooms": rooms}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", str(path))
    service = HomeMatchService(tmp_path / "ledger.sqlite")
    yield service
    service.close()


def shortlist(service, renter):
    profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=5_000_000, scenario=Scenario())
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    return sid, run_id


def test_published_results_mix_both_landlords_in_agent_order(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    run = two_landlords.repo.run(run_id)
    assert run["status"] == "published"
    assert {item["landlord_id"] for item in run["items"]} == {"owner2", "owner3"}
    # Kết quả tới khách ngay, đúng thứ tự xếp hạng của trợ lý, không còn chờ duyệt.
    visible = [item["room_id"] for item in two_landlords.results(sid, renter)["results"]]
    assert visible == [item["room_id"] for item in run["items"]]
    # Thu nhập không bao giờ xuất hiện trong dữ liệu phòng trả cho khách.
    assert all("monthly_income_vnd" not in item for item in two_landlords.results(sid, renter)["results"])


def test_landlord_creates_edits_and_sets_occupancy_of_own_rooms_only(two_landlords):
    quote = DEMO[0]["quote"]
    created = two_landlords.create_room(OWNER_2, RoomInput(
        title="Studio mới Quận 7", city="TP.HCM", area="Quận 7", room_type="studio", area_m2=28,
        capacity=2, published=True, occupancy="vacant", quote=quote, house_rules="Cổng đóng 23:00."))["room"]
    assert created["landlord_id"] == "owner2" and created["available"] is True and created["revision"] == 1
    assert created["id"] in {room["id"] for room in two_landlords.rooms(OWNER_2)["rooms"]}
    assert created["id"] not in {room["id"] for room in two_landlords.rooms(OWNER_B)["rooms"]}
    editable = {key: created[key] for key in RoomInput.model_fields}
    edit = RoomUpdate.model_validate({**editable, "expected_revision": 1, "title": "Studio mới Quận 7 (đã sửa)"})
    updated = two_landlords.update_room(created["id"], OWNER_2, edit)["room"]
    assert updated["revision"] == 2 and updated["title"].endswith("(đã sửa)")
    with pytest.raises(DomainError) as stale:
        two_landlords.update_room(created["id"], OWNER_2, edit)
    assert stale.value.code == "catalog_conflict"
    with pytest.raises(DomainError) as foreign:
        two_landlords.change_room_status(created["id"], OWNER_B, CatalogStatus(expected_revision=2, published=False))
    assert foreign.value.code == "not_found"
    rented = two_landlords.change_room_status(created["id"], OWNER_2,
                                              CatalogStatus(expected_revision=2, occupancy="rented"))["room"]
    assert rented["occupancy"] == "rented" and rented["available"] is False


def test_online_viewing_goes_to_the_rooms_landlord_with_a_meeting_link(two_landlords, renter):
    sid, _ = shortlist(two_landlords, renter)
    room = two_landlords.results(sid, renter)["results"][0]
    when = datetime.now(timezone.utc) + timedelta(days=1)
    viewing = two_landlords.request_viewing(sid, renter, room["room_id"], when, "v1", mode="online")
    assert viewing["landlord_id"] == room["landlord_id"] and viewing["meeting_url"].startswith("https://meet.jit.si/")
    other = OWNER_B if room["landlord_id"] == "owner2" else OWNER_2
    with pytest.raises(DomainError):
        two_landlords.respond_viewing(viewing["id"], other, "confirmed")
    owner = Actor(id=room["landlord_id"], role="owner")
    assert [item["id"] for item in two_landlords.viewings(owner)] == [viewing["id"]]
    assert two_landlords.respond_viewing(viewing["id"], owner, "confirmed")["status"] == "confirmed"


def test_published_run_notifies_renter_and_nothing_to_landlords(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    owner_id = renter.id
    rows = two_landlords.repo.db.execute(
        "SELECT kind,dedup_key FROM hm_notifications WHERE user_id=?", (owner_id,)).fetchall()
    assert any(row["kind"] == "rooms_ready" and row["dedup_key"] == f"run:{run_id}:ready" for row in rows)
    # 19/11/2026: bỏ khách tiềm năng — phòng lọt top 5 không tạo lead, không báo chủ nhà.
    assert two_landlords.repo.db.execute("SELECT COUNT(*) AS n FROM hm_leads").fetchone()["n"] == 0
    top5_landlords = {(item.get("landlord_id") or "owner2") for item in two_landlords.repo.run(run_id)["items"][:5]}
    landlord_notes = two_landlords.repo.db.execute(
        "SELECT COUNT(*) AS n FROM hm_notifications WHERE user_id IN (%s)" % ",".join("?" * len(top5_landlords)),
        tuple(top5_landlords)).fetchone()
    assert landlord_notes["n"] == 0
    # Chạy lần 2 (run mới) không nhân đôi thông báo của run cũ: dedup theo run.
    two_landlords.repo.mark_published(run_id)
    rows = two_landlords.repo.db.execute(
        "SELECT COUNT(*) AS n FROM hm_notifications WHERE dedup_key=?", (f"run:{run_id}:ready",)).fetchone()
    assert rows["n"] == 1


def test_old_snapshot_rooms_move_to_the_trial_landlord_of_their_city(tmp_path, monkeypatch):
    # Snapshots crawled before migration 24 still name owner-a..d; importing one
    # hands its rooms to owner1 (Hà Nội) / owner2 (TP.HCM) so landlords see them.
    rooms = [{**DEMO[0], "landlord_id": "owner-a"},
             {**DEMO[1], "landlord_id": "owner-c", "city": "Hà Nội", "area": "Cầu Giấy"},
             {**DEMO[2], "landlord_id": "owner3"}]
    path = tmp_path / "old-snapshot.json"
    path.write_text(json.dumps({"rooms": rooms}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", str(path))
    service = HomeMatchService(tmp_path / "ledger.sqlite")
    try:
        owners = {room.id: room.landlord for room in service.catalog.rooms()}
        assert owners == {DEMO[0]["id"]: "owner2", DEMO[1]["id"]: "owner1", DEMO[2]["id"]: "owner3"}
    finally:
        service.close()


def test_stored_rooms_of_retired_landlords_are_released_on_startup(storage):
    service = HomeMatchService(storage)
    try:
        first, second = service.catalog.rooms()[:2]
        legacy = {first.id: first.model_copy(update={"landlord_id": "owner-a"}),
                  second.id: second.model_copy(update={"landlord_id": "owner-d", "city": "Hà Nội"})}
        with service.repo.db:
            for room in legacy.values():
                service.repo.db.execute("UPDATE hm_rooms SET payload_json=? WHERE id=?",
                                        (room.model_dump_json(), room.id))
        before = service.catalog.version
    finally:
        service.close()
    service = HomeMatchService(storage)
    try:
        rooms = {room.id: room for room in service.catalog.rooms()}
        assert rooms[first.id].landlord == "owner2" and rooms[second.id].landlord == "owner1"
        # Normalization, not an edit: revisions stay, the catalog version moves on.
        assert rooms[first.id].revision == first.revision and rooms[second.id].revision == second.revision
        assert service.catalog.version != before
        assert not any(room.landlord_id in {"owner-a", "owner-b", "owner-c", "owner-d"}
                       for room in rooms.values())
    finally:
        service.close()
