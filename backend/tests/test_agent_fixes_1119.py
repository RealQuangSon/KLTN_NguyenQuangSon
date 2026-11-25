"""Sửa 2 lỗi ổn định khi đo chất lượng đề xuất trên LLM thật (18/11, r06 và r12).

r06. "bắt buộc có máy lạnh và máy giặt" là yêu cầu CỨNG (must_amenities), không phải
     ưu tiên; "thì tốt/ưu tiên" vẫn là ưu tiên; "không cần máy giặt nữa" gỡ yêu cầu.
r12. Sau khi đã có kết quả, "rẻ hơn nữa, dưới 3,5 triệu thôi" phải tìm lại với trần mới
     (trước đây luật đọc ý định "unknown", rơi vào vòng LLM và model không tìm lại).

Tất cả offline: model là FakeClient không kịch bản, đường tắt không được gọi model.
"""
import pytest

from backend.app.agent_loop import is_budget_refinement
from backend.app.interpreter import OpenAIInterpreter, dropped_amenities_hint, must_amenities_hint
from backend.app.models import Profile, Scenario
from backend.app.service import HomeMatchService
from backend.tests.test_multi_agent import FakeClient


@pytest.fixture
def demo_service(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    service = HomeMatchService(tmp_path / "fixes-1119-demo.sqlite")
    yield service
    service.close()


@pytest.fixture
def fast_service(tmp_path, monkeypatch):
    """Chế độ openai với model không có lượt nào: mọi lần gọi model đều lộ ra ở client.requests.
    Analyst tắt để lượt công bố không có lần gọi handover (giải thích top căn) — test chỉ
    kiểm rằng việc tìm không đi qua vòng LLM."""
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "off")
    client = FakeClient([])
    service = HomeMatchService(tmp_path / "fixes-1119-openai.sqlite",
                               interpreter=OpenAIInterpreter(client=client, model="fixture-model"))
    yield service, client
    service.close()


def confirmed(service, session_id) -> Profile:
    return Profile.model_validate_json(service.repo.session(session_id)["profile_json"])


# --- r06: tiện ích bắt buộc ---

@pytest.mark.parametrize("text, expected", [
    ("phòng Đống Đa bắt buộc có máy lạnh và máy giặt, tổng tháng dưới 5 triệu, 1 người",
     ["air_conditioning", "washing_machine"]),
    ("phải có máy lạnh, ban công thì tốt", ["air_conditioning"]),
    ("máy lạnh là bắt buộc nhưng máy giặt thì không cần", ["air_conditioning"]),
    ("chỉ lấy phòng có thang máy", ["elevator"]),
    ("nhất định phải có chỗ để xe", ["parking"]),
    # Dấu hiệu mềm hoặc không có dấu hiệu mạnh → vẫn là ưu tiên.
    ("phòng Nam Từ Liêm có ban công thì tốt, tiền thuê dưới 4 triệu", []),
    ("phòng có máy lạnh, máy giặt", []),
    ("cần có máy lạnh", []),
    ("không bắt buộc có máy giặt", []),
])
def test_strong_wording_marks_amenities_as_required(text, expected):
    assert must_amenities_hint(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("thôi không cần máy giặt nữa", ["washing_machine"]),
    ("bỏ yêu cầu máy lạnh", ["air_conditioning"]),
    ("phòng có máy giặt", []),
])
def test_dropping_an_amenity_is_read_deterministically(text, expected):
    assert dropped_amenities_hint(text) == expected


def test_required_amenities_filter_the_fast_path_search(fast_service, renter):
    service, client = fast_service
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter,
                            "phòng trọ Quận 7 bắt buộc có máy lạnh và máy giặt, tổng tháng dưới 8 triệu, 1 người")
    assert reply["agent_mode"] == "fast_path" and client.requests == []
    profile = confirmed(service, sid)
    assert profile.must_amenities == ["air_conditioning", "washing_machine"]
    assert not set(profile.preferences) & {"air_conditioning", "washing_machine"}
    results = service.results(sid, renter)["results"]
    assert results
    rooms = {room.id: room for room in service.catalog.rooms()}
    for item in results:
        amenities = rooms[item["room_id"]].amenities
        assert amenities.get("air_conditioning") is True and amenities.get("washing_machine") is True


def test_soft_wording_stays_a_preference(fast_service, renter):
    service, _ = fast_service
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "phòng Nam Từ Liêm có ban công thì tốt, tiền thuê dưới 4 triệu, 1 người")
    profile = confirmed(service, sid)
    assert profile.must_amenities == [] and "balcony" in profile.preferences


def test_required_amenity_can_be_dropped_in_chat(demo_service, renter):
    sid = demo_service.create_session(renter)["session_id"]
    demo_service.message(sid, renter,
                         "phòng Quận 1 TP.HCM bắt buộc có máy lạnh và máy giặt, tổng tháng dưới 8 triệu, 1 người")
    assert confirmed(demo_service, sid).must_amenities == ["air_conditioning", "washing_machine"]
    demo_service.message(sid, renter, "thôi không cần máy giặt nữa")
    assert demo_service._draft(sid).must_amenities == ["air_conditioning"]
    assert confirmed(demo_service, sid).must_amenities == ["air_conditioning"]


def test_chat_must_keeps_requirements_already_on_the_profile(demo_service, renter):
    sid = demo_service.create_session(renter)["session_id"]
    demo_service.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 1", max_monthly_cost_vnd=9_000_000,
                                              must_amenities=["parking"], scenario=Scenario(people=1)), 0)
    demo_service.message(sid, renter, "tìm phòng bắt buộc có máy lạnh")
    assert demo_service._draft(sid).must_amenities == ["parking", "air_conditioning"]
    assert confirmed(demo_service, sid).must_amenities == ["parking", "air_conditioning"]


# --- r12: chỉnh mức tiền sau khi đã có kết quả ---

def test_cheaper_follow_up_re_runs_the_search_without_the_model(fast_service, renter):
    service, client = fast_service
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "phòng Quận 7 tổng tháng dưới 8 triệu cho 1 người")
    first = service.results(sid, renter)
    assert first["results"]
    reply = service.message(sid, renter, "rẻ hơn nữa, dưới 5 triệu thôi")
    assert reply["agent_mode"] == "fast_path" and client.requests == []
    profile = confirmed(service, sid)
    assert profile.max_monthly_cost_vnd == 5_000_000
    second = service.results(sid, renter)
    assert second["run_id"] != first["run_id"]
    for item in second["results"]:
        assert item["cost"]["monthly_total_vnd"] <= 5_000_000


@pytest.mark.parametrize("text, expected", [
    ("rẻ hơn nữa, dưới 3,5 triệu thôi", True),
    ("giảm xuống 4 triệu", True),
    ("3 triệu thôi", True),
    # Tiền không phải mức tìm, hoặc câu nói về một căn cụ thể → không tìm lại.
    ("cọc 3 triệu được không", False),
    ("lương mình 12 triệu", False),
    ("mình làm ra 12 triệu", False),
    ("điện 4k một số", False),
    ("căn thứ hai dưới 3 triệu", False),
    ("ok cảm ơn", False),
])
def test_budget_refinement_needs_a_budget_cue_and_no_specific_room(fast_service, renter, text, expected):
    service, _ = fast_service
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "phòng Quận 7 tổng tháng dưới 8 triệu cho 1 người")
    assert is_budget_refinement(service, service.repo.session(sid), text) is expected


def test_budget_refinement_needs_an_existing_search(fast_service, renter):
    service, _ = fast_service
    sid = service.create_session(renter)["session_id"]
    assert is_budget_refinement(service, service.repo.session(sid), "rẻ hơn nữa, dưới 3,5 triệu thôi") is False
