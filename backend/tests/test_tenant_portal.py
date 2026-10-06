from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.advisor import advise
from backend.app.handbook import answer
from backend.app.listings import ListingQuery
from backend.app.main import create_app
from backend.app.models import Actor, DomainError

RENTER = {"Authorization": "Bearer demo-renter-a"}
LANDLORD = {"Authorization": "Bearer demo-owner-a"}


def test_filter_search_shows_only_published_matching_rooms_without_login(service):
    found = service.search_listings(ListingQuery(city="Sài Gòn", area="Q7", amenities=["window"], max_monthly=4_000_000))
    rooms = {room.id: room for room in service.catalog.rooms()}
    assert found["total"] == len(found["items"]) > 0
    for item in found["items"]:
        room = rooms[item["id"]]
        assert room.published and room.available is not False and room.area == "Quận 7"
        assert room.amenities["window"] is True  # unknown never satisfies a filter
        assert item["cost"]["monthly_total_vnd"] <= 4_000_000
        assert "published" not in item and item["location_accuracy"] != "exact"
    totals = [item["cost"]["monthly_total_vnd"] for item in found["items"]]
    assert totals == sorted(totals)
    with TestClient(create_app(lambda: service)) as client:
        response = client.get("/listings", params={"city": "TP.HCM", "amenities": ["window", "quiet"], "page_size": 2})
        assert response.status_code == 200 and len(response.json()["items"]) <= 2
        assert client.get("/listings", params={"unknown": "x"}).status_code == 422


def test_listing_detail_records_views_and_hides_unpublished(service):
    room = next(room for room in service.catalog.rooms() if room.published)
    hidden = next(room for room in service.catalog.rooms() if not room.published)
    with TestClient(create_app(lambda: service)) as client:
        detail = client.get(f"/listings/{room.id}", headers=RENTER).json()
        assert detail["id"] == room.id and detail["landlord_id"] == "owner-a" and "cost" in detail
        client.get(f"/listings/{room.id}")  # anonymous view
        assert client.get(f"/listings/{hidden.id}").status_code == 404
        views = service.repo.db.execute("SELECT user_id FROM hm_room_views WHERE room_id=?", (room.id,)).fetchall()
        assert sorted(str(row["user_id"]) for row in views) == ["None", "renter-a"]


def test_advisor_explains_and_never_recommends_over_budget_or_unknown():
    def item(room_id, monthly, area, band=None):
        return {"room_id": room_id, "title": f"Phòng {room_id}. mô tả", "area_m2": area,
                "amenities": {"window": room_id != "b"},
                "cost": {"monthly_total_vnd": monthly, "initial_total_vnd": monthly and monthly * 2,
                         "missing_monthly": [] if monthly else ["water"], "missing_initial": [],
                         "affordability": {"band": band, "renter_burden_vnd": monthly}}}
    result = advise([item("a", 3_000_000, 18, "can_nhac"), item("b", 2_500_000, 25, "phu_hop"),
                     item("c", None, 30)], budget=2_800_000, preferences=["window"])
    assert result["recommended_room_id"] == "b"
    rows = {row["room_id"]: row for row in result["rooms"]}
    assert any("Tổng tháng thấp nhất" in text for text in rows["b"]["pros"])
    assert any("Vượt ngân sách" in text for text in rows["a"]["cons"])
    assert any("chưa rõ" in text for text in rows["c"]["cons"])
    assert not any("thấp nhất" in text for text in rows["c"]["pros"])
    none = advise([item("a", 3_000_000, 18)], budget=1_000_000)
    assert none["recommended_room_id"] is None


def test_session_compare_returns_advice_within_confirmed_budget(service, renter, landlord, profile):
    from backend.app.models import Review
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    service.review(run_id, landlord, Review(decision="approve", expected_profile_version=1,
                                            reason="ok", idempotency_key="k"))
    ids = [item["room_id"] for item in service.results(sid, renter)["results"]][:2]
    compared = service.compare(sid, renter, ids)
    assert compared["advice"]["recommended_room_id"] in ids
    assert {row["room_id"] for row in compared["advice"]["rooms"]} == set(ids)


def test_direct_listing_viewing_goes_to_landlord_and_requires_a_free_room(service, renter, landlord):
    room = next(room for room in service.catalog.rooms() if room.published and room.available)
    when = datetime.now(timezone.utc) + timedelta(days=1)
    viewing = service.request_listing_viewing(renter, room.id, when, "direct-1", "online")
    assert viewing["session_id"] is None and viewing["landlord_id"] == "owner-a" and viewing["meeting_url"]
    assert service.request_listing_viewing(renter, room.id, when, "direct-1", "online")["id"] == viewing["id"]
    assert viewing["id"] in {item["id"] for item in service.viewings(renter)}
    assert service.viewing(viewing["id"], renter)["id"] == viewing["id"]
    with pytest.raises(DomainError):
        service.viewing(viewing["id"], Actor(id="renter-b", role="renter"))
    assert service.respond_viewing(viewing["id"], landlord, "confirmed")["status"] == "confirmed"
    taken = next(room for room in service.catalog.rooms() if room.published and room.available is False)
    with pytest.raises(DomainError) as unavailable:
        service.request_listing_viewing(renter, taken.id, when, "direct-2")
    assert unavailable.value.code == "not_available"


def test_handbook_answers_platform_questions_and_landlord_rules():
    rules = "Cổng đóng 23:00. Gửi xe máy miễn phí 1 xe. Điện theo công tơ, chốt số ngày 1."
    deposit = answer("Khi trả phòng có được hoàn cọc không?")
    assert deposit["answers"][0]["id"] == "deposit" and deposit["disclaimer"]
    parking = answer("Gửi xe ở đâu, mất phí không?", rules)
    assert parking["house_rules"] == ["Gửi xe máy miễn phí 1 xe."]
    assert len(answer("nội quy của phòng là gì", rules)["house_rules"]) == 3
    assert not answer("xyz không liên quan")["found"]


def test_handbook_is_reachable_from_chat_without_a_model_call(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Quy định về tạm trú khi thuê phòng thế nào?")
    assert reply["status"] == "handbook_answer" and reply["answers"][0]["id"] == "residence"
    assert reply["usage"]["logical_calls"] == 0 and reply["provenance"]["agent"] == "handbook"
