"""Đợt 1 sửa luồng UX (12/11/2026): UX-01 tiền thuê/tổng tháng, UX-02 tự xác nhận ở
backend, UX-03 điểm chi phí + diện tích, UX-04 tin ở ghép / giới hạn đối tượng."""
import json
from pathlib import Path

import pytest

from backend.app.catalog import RANKING_CONFIG, Catalog, listing_flags
from backend.app.interpreter import area_m2_hint, budget_approx_hint, budget_range, wants_cheapest
from backend.app.models import Profile, Room, Scenario

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo_rooms.json"


def make_rooms(tmp_path, specs):
    base = json.loads(DEMO.read_text(encoding="utf-8"))["rooms"][0]
    rooms = []
    for index, spec in enumerate(specs):
        room = json.loads(json.dumps(base))
        room.update(id=f"t-{index:02d}", title=spec.get("title", f"Phòng {index}"),
                    area_m2=spec.get("area_m2"), capacity=spec.get("capacity", 4))
        room["quote"]["rent_vnd"] = spec["rent"]
        room["amenities"] = spec.get("amenities", room["amenities"])
        if "description" in spec:
            room["description"] = spec["description"]
        rooms.append(room)
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps({"rooms": rooms}), encoding="utf-8")
    return Catalog(path)


def profile(**kw):
    values = dict(city="TP.HCM", area="Quận 7", scenario=Scenario(people=1))
    values.update(kw)
    return Profile(**values)


# --- parsers ---

def test_parsers_read_range_area_and_cheapest():
    assert budget_range("giá thuê 3 đến 4 triệu") == (3_000_000, 4_000_000)
    assert budget_range("tầm 4 triệu") is None
    assert area_m2_hint("rộng khoảng 20m2") == {"value": 20, "hard": False}
    assert area_m2_hint("ít nhất 25 m² nhé") == {"value": 25, "hard": True}
    assert wants_cheapest("tìm phòng rẻ nhất") and not wants_cheapest("tầm 4 triệu")


# --- UX-01 ---

def test_profile_needs_some_cap():
    with pytest.raises(ValueError):
        profile()


def test_rent_scope_keeps_a_room_whose_total_exceeds_the_rent_cap(tmp_path):
    catalog = make_rooms(tmp_path, [{"rent": 3_500_000}])
    # Tổng tháng ≈ tiền thuê + phí > 4 triệu; chỉ trần THUÊ thì vẫn giữ.
    rent_only = catalog.rank(profile(max_rent_vnd=4_000_000))[0]
    assert [c.room_id for c in rent_only] == ["t-00"]
    assert rent_only[0].cost.monthly_total_vnd > 4_000_000
    # "Tổng tháng 4 triệu" vẫn lọc theo tổng như cũ.
    assert catalog.rank(profile(max_monthly_cost_vnd=4_000_000))[0] == []


def test_below_range_is_kept_but_scored_lower(tmp_path):
    catalog = make_rooms(tmp_path, [{"rent": 1_200_000}, {"rent": 3_500_000}])
    ranked = catalog.rank(profile(min_rent_vnd=3_000_000, max_rent_vnd=4_000_000))[0]
    assert [c.room_id for c in ranked] == ["t-01", "t-00"]
    assert "Tiền thuê thấp hơn khoảng bạn nêu." in ranked[1].tradeoffs


# --- UX-03 ---

def test_cheapest_room_no_longer_wins_inside_the_budget(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 1_500_000, "amenities": {"window": False}},
        {"rent": 3_800_000, "amenities": {"window": True}}])
    base = dict(max_rent_vnd=4_000_000, preferences=["window"])
    ranked = catalog.rank(profile(**base))[0]
    assert ranked[0].room_id == "t-01"  # hợp sở thích hơn dù đắt hơn
    by_id = {c.room_id: c for c in ranked}
    assert by_id["t-00"].components["cost"] == by_id["t-01"].components["cost"] == 1.0
    cheap = {c.room_id: c for c in catalog.rank(profile(prefer_cheapest=True, **base))[0]}
    assert cheap["t-00"].components["cost"] > cheap["t-01"].components["cost"]
    assert RANKING_CONFIG["version"] == "b1-p-v2"


def test_area_is_a_soft_score_with_a_label_and_unknown_is_neutral(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 3_000_000, "area_m2": 10}, {"rent": 3_000_000, "area_m2": 20},
        {"rent": 3_000_000, "area_m2": None}])
    ranked = {c.room_id: c for c in catalog.rank(profile(max_rent_vnd=4_000_000, min_area_m2=20))[0]}
    assert ranked["t-01"].score > ranked["t-00"].score
    assert "Nhỏ hơn mong muốn 20 m²." in ranked["t-00"].tradeoffs
    assert "area" not in ranked["t-02"].components and "area_unknown" in ranked["t-02"].verification


def test_hard_area_filters_known_small_rooms_only(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 3_000_000, "area_m2": 10}, {"rent": 3_000_000, "area_m2": 25}, {"rent": 3_000_000}])
    ids = [c.room_id for c in catalog.rank(profile(max_rent_vnd=4_000_000, min_area_m2=20, min_area_hard=True))[0]]
    assert sorted(ids) == ["t-01", "t-02"]


def test_ties_are_broken_by_listing_completeness_then_room_id(tmp_path):
    # Cùng điểm 1.0: tin ghi sức chứa + diện tích đứng trước tin thiếu, dù mã lớn hơn.
    catalog = make_rooms(tmp_path, [
        {"rent": 3_000_000, "capacity": None, "area_m2": None},
        {"rent": 3_500_000, "capacity": None, "area_m2": 18},
        {"rent": 3_800_000, "capacity": 2, "area_m2": 20},
        {"rent": 3_200_000, "capacity": 2, "area_m2": 22}])
    ranked = catalog.rank(profile(max_rent_vnd=4_000_000))[0]
    assert len({c.score for c in ranked}) == 1
    assert [c.room_id for c in ranked] == ["t-02", "t-03", "t-01", "t-00"]


def test_tie_break_never_outranks_a_higher_score(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 3_000_000, "capacity": None, "area_m2": None, "amenities": {"window": True}},
        {"rent": 3_000_000, "capacity": 2, "area_m2": 20, "amenities": {"window": False}}])
    ranked = catalog.rank(profile(max_rent_vnd=4_000_000, preferences=["window"]))[0]
    assert [c.room_id for c in ranked] == ["t-00", "t-01"]


def test_budget_approx_hint_reads_only_what_the_renter_said():
    assert budget_approx_hint("tìm phòng ở bình thạnh tầm 4 triệu cho 2 người") is True
    assert budget_approx_hint("khoảng 3,5tr thôi") is True
    assert budget_approx_hint("phòng dưới 4 triệu") is False
    assert budget_approx_hint("giá thuê 3 đến 4 triệu") is False
    # "khoảng 20m2" là diện tích, không phải tiền; câu không nêu tiền → None.
    assert budget_approx_hint("rộng khoảng 20m2 có máy lạnh") is None
    assert budget_approx_hint("có máy lạnh") is None


def test_approx_budget_ranks_rooms_near_the_stated_amount_first(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 1_800_000}, {"rent": 3_900_000}, {"rent": 3_000_000}, {"rent": 4_500_000}])
    ranked = catalog.rank(profile(max_rent_vnd=4_000_000, budget_approx=True))[0]
    # 4,5 triệu vẫn bị loại (trần cứng không nới); còn lại gần 4 triệu đứng trước.
    assert [c.room_id for c in ranked] == ["t-01", "t-02", "t-00"]
    # "dưới 4 triệu" (không approx): điểm chi phí bằng nhau như trước.
    flat = catalog.rank(profile(max_rent_vnd=4_000_000))[0]
    assert {c.components["cost"] for c in flat} == {1.0}
    # "rẻ nhất" thắng "tầm": căn rẻ đứng trước.
    cheap = catalog.rank(profile(max_rent_vnd=4_000_000, budget_approx=True, prefer_cheapest=True))[0]
    assert cheap[0].room_id == "t-00"


def test_approx_budget_does_not_outweigh_a_stated_preference(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 3_900_000, "amenities": {"window": False}},
        {"rent": 3_000_000, "amenities": {"window": True}}])
    ranked = catalog.rank(profile(max_rent_vnd=4_000_000, budget_approx=True, preferences=["window"]))[0]
    assert ranked[0].room_id == "t-01"


# --- UX-04 ---

TITLES = [
    ("Tìm 1 bạn ở ghép có thể dọn vào ngay", {"roommate_wanted", "shared_listing"}),
    ("CHO NỮ THUÊ PHÒNG TRỌ Quận 7", {"gender_female_only"}),
    ("Phòng chỉ nhận nam, sạch sẽ", {"gender_male_only"}),
    ("Share phòng gần Lotte Mart", {"shared_listing"}),
    ("Phòng riêng Nam Từ Liêm yên tĩnh", set()),
]


@pytest.mark.parametrize("title,expected", TITLES)
def test_listing_flags(title, expected):
    room = Room.model_validate({**json.loads(DEMO.read_text())["rooms"][0], "title": title})
    assert listing_flags(room) == expected


def test_roommate_listing_excluded_for_two_people_only_and_labels_do_not_change_score(tmp_path):
    catalog = make_rooms(tmp_path, [
        {"rent": 3_000_000, "title": "Tìm 1 bạn ở ghép"},
        {"rent": 3_000_000, "title": "CHO NỮ THUÊ PHÒNG"},
        {"rent": 3_000_000, "title": "Phòng thường"}])
    one = {c.room_id: c for c in catalog.rank(profile(max_rent_vnd=4_000_000))[0]}
    assert set(one) == {"t-00", "t-01", "t-02"}
    two = {c.room_id: c for c in catalog.rank(
        profile(max_rent_vnd=4_000_000, scenario=Scenario(people=2)))[0]}
    assert set(two) == {"t-01", "t-02"}
    assert "gender_female_only" in two["t-01"].verification
    assert two["t-01"].score == two["t-02"].score


# --- UX-02 ---

def test_chat_turn_confirms_and_ranks_in_the_same_turn(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "tìm phòng Quận 7 TP.HCM giá thuê 3 đến 4 triệu cho 1 người")
    session = service.repo.session(sid)
    assert session["profile_json"], "backend phải tự xác nhận hồ sơ trong lượt chat"
    confirmed = json.loads(session["profile_json"])
    assert confirmed["max_rent_vnd"] == 4_000_000 and confirmed["min_rent_vnd"] == 3_000_000
    assert confirmed["max_monthly_cost_vnd"] is None
    results = service.results(sid, renter)
    assert results["status"] in {"published", "no_match"}
    assert reply.get("status") in {"published", "no_match"}
    assert reply.get("confirmed_profile") or service.session(sid, renter)["confirmed_profile"]


def test_chat_turn_without_enough_data_does_not_confirm(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "mình cần tìm phòng")
    assert not service.repo.session(sid)["profile_json"]


def test_total_scope_phrase_sets_a_total_cap(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "tìm phòng Quận 7 TP.HCM tổng tháng 6 triệu")
    confirmed = json.loads(service.repo.session(sid)["profile_json"])
    assert confirmed["max_monthly_cost_vnd"] == 6_000_000 and confirmed["max_rent_vnd"] is None
