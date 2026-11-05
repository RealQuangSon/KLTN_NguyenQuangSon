"""AG-03: vòng đầu không rỗng vì thiếu sức chứa/bảng phí — hỏi rõ kèm số tin,
khách đồng ý thì vòng mới xem được (không bật ngầm accept_estimated_data)."""
import json

from backend.app.catalog import Catalog
from backend.app.models import Profile, Scenario
from backend.app.service import HomeMatchService


def catalog_missing_capacity(tmp_path, count=4):
    """Quận 7 rooms đủ điều kiện nhưng thiếu capacity → verification giữ lại."""
    base = {"id": None, "revision": 1, "title": "Phòng Q7 thiếu sức chứa. Gần chợ",
            "city": "TP.HCM", "area": "Quận 7", "room_type": "room", "area_m2": 20,
            "capacity": None, "published": True, "available": True,
            "amenities": {"private_bathroom": True, "window": True, "quiet": True},
            "quote": {"rent_vnd": 3000000, "deposit_vnd": 2000000, "one_time_vnd": 0,
                      "advance_months": 1,
                      "fees": [{"name": "electricity", "amount_vnd": 3000, "mode": "kwh",
                                "source": "synthetic", "included_in_rent": False},
                               {"name": "water", "amount_vnd": 80000, "mode": "person",
                                "source": "synthetic", "included_in_rent": False}]},
            "house_rules": "Cổng khóa 23:00.", "source": "synthetic://missing-capacity",
            "synthetic": True, "landlord_id": "owner-a"}
    rooms = []
    for index in range(count):
        room = {**base, "id": f"missing-cap-{index:02d}"}
        rooms.append(room)
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps({"rooms": rooms}, ensure_ascii=False), encoding="utf-8")
    return Catalog(path)


def test_empty_first_loop_asks_about_missing_capacity(tmp_path, renter):
    service = HomeMatchService(tmp_path / "ledger.sqlite", catalog=catalog_missing_capacity(tmp_path))
    try:
        sid = service.create_session(renter)["session_id"]
        profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=4_000_000,
                          max_initial_cash_vnd=6_500_000, scenario=Scenario())
        result = service.confirm(sid, renter, profile, 0)
        # Vòng đầu rỗng vì bị giữ lại chờ xác minh (thiếu sức chứa) — không published.
        assert result["status"] == "needs_verification" and result["results"] == []
        held = (result.get("diagnostics_summary") or {}).get("verification", {})
        total = sum(held.values())
        # Lượt chat KHÔNG đổi nhu cầu: câu hỏi nêu rõ số tin bị giữ + đề nghị ước tính.
        reply = service.message(sid, renter, "Tìm phòng Quận 7 cho 1 người")
        questions = " ".join(reply["questions"])
        assert str(total) in questions and "ước tính" in questions
        # Không bao giờ bật ngầm accept_estimated_data.
        assert reply["draft"]["accept_estimated_data"] is False
    finally:
        service.close()


def test_accepting_estimated_data_unlocks_a_new_run_with_results(tmp_path, renter):
    service = HomeMatchService(tmp_path / "ledger.sqlite", catalog=catalog_missing_capacity(tmp_path))
    try:
        sid = service.create_session(renter)["session_id"]
        profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=4_000_000,
                          max_initial_cash_vnd=6_500_000, scenario=Scenario(),
                          accept_estimated_data=False)
        service.confirm(sid, renter, profile, 0)
        # Khách đồng ý qua chat (lượt này ĐỔI nhu cầu → run mới khi FE xác nhận lại).
        reply = service.message(sid, renter, "chấp nhận dữ liệu ước tính")
        assert reply["draft"]["accept_estimated_data"] is True
        revision = reply["draft_revision"]
        confirmed = service.confirm(sid, renter, profile.model_copy(update={"accept_estimated_data": True}),
                                    revision)
        # Vòng mới có kết quả, dữ liệu giả định chuẩn được gắn nhãn ước tính.
        assert confirmed["status"] == "published" and confirmed["results"]
        assert all(item.get("verification") for item in confirmed["results"])
    finally:
        service.close()
