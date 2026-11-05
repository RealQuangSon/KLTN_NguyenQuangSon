import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.catalog import DEFAULT_CATALOG
from backend.app.main import create_app
from backend.app.models import Actor, CatalogStatus, DomainError, Profile, RoomInput, RoomUpdate, Scenario
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


def shortlist(service, renter):
    profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=5_000_000, scenario=Scenario())
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    return sid, run_id


def test_published_results_mix_both_landlords_in_agent_order(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    run = two_landlords.repo.run(run_id)
    assert run["status"] == "published"
    assert {item["landlord_id"] for item in run["items"]} == {"owner-a", "owner-b"}
    # Kết quả tới khách ngay, đúng thứ tự xếp hạng của trợ lý, không còn chờ duyệt.
    visible = [item["room_id"] for item in two_landlords.results(sid, renter)["results"]]
    assert visible == [item["room_id"] for item in run["items"]]
    # Thu nhập không bao giờ xuất hiện trong dữ liệu phòng trả cho khách.
    assert all("monthly_income_vnd" not in item for item in two_landlords.results(sid, renter)["results"])


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
    sid, _ = shortlist(two_landlords, renter)
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


def test_published_run_notifies_renter_and_touches_top5_landlord_leads(two_landlords, renter):
    sid, run_id = shortlist(two_landlords, renter)
    owner_id = renter.id
    rows = two_landlords.repo.db.execute(
        "SELECT kind,dedup_key FROM hm_notifications WHERE user_id=?", (owner_id,)).fetchall()
    assert any(row["kind"] == "rooms_ready" and row["dedup_key"] == f"run:{run_id}:ready" for row in rows)
    leads = two_landlords.repo.db.execute("SELECT landlord_id,renter_id,sources_json FROM hm_leads").fetchall()
    top5_landlords = {(item.get("landlord_id") or "owner-a") for item in two_landlords.repo.run(run_id)["items"][:5]}
    assert {lead["landlord_id"] for lead in leads} == top5_landlords
    assert all(lead["renter_id"] == owner_id for lead in leads)
    assert all("recommended" in json.loads(lead["sources_json"]) for lead in leads)
    # Chạy lần 2 (run mới) không nhân đôi thông báo của run cũ: dedup theo run.
    two_landlords.repo.mark_published(run_id)
    rows = two_landlords.repo.db.execute(
        "SELECT COUNT(*) AS n FROM hm_notifications WHERE dedup_key=?", (f"run:{run_id}:ready",)).fetchone()
    assert rows["n"] == 1
