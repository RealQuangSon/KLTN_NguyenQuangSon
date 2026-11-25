"""18/11 — ba lỗi do probe live bằng câu mới (không có trong bộ đo hội thoại) bắt được:

1. "lương mình 12 triệu thì nên thuê bao nhiêu?" bị đọc thành trần 12 triệu.
2. "đặt lịch xem căn 1" không nhận ra căn dù câu trả lời gọi các căn là "Căn 1/2/3".
3. Câu so sánh đúng ("rẻ hơn 15.000 ₫" = hiệu hai giá) bị hậu kiểm số thay bằng template.
"""
import pytest

from backend.app.agent_guard import resolve_room_reference
from backend.app.agent_loop import check_numbers
from backend.app.costs import income_housing_levels
from backend.app.interpreter import (OpenAIInterpreter, budget_approx_hint, budget_hint, budget_range,
                                     income_amount, income_question, relative_budget, rent_budget_hint)
from backend.app.service import HomeMatchService
from backend.tests.test_multi_agent import FakeClient

SAFE_TEMPLATE = "Mình vừa kiểm tra nhu cầu của bạn qua các bước bên dưới"


# --- 1. Lương/thu nhập không phải mức tiền thuê ---

@pytest.mark.parametrize("text, income", [
    ("lương mình 12 triệu một tháng thì nên thuê phòng tầm bao nhiêu?", 12_000_000),
    ("thu nhập 15 triệu thì thuê được phòng bao nhiêu", 15_000_000),
    ("mình kiếm được 10tr/tháng", 10_000_000),
    ("luong 9tr5 thi thue phong bao nhieu", 9_500_000),
    ("lương khoảng 12tr", 12_000_000),
])
def test_income_amount_is_never_read_as_a_budget(text, income):
    assert income_amount(text) == income
    assert budget_hint(text) is None and rent_budget_hint(text) is None
    assert budget_range(text) is None and relative_budget(text) is None
    assert budget_approx_hint(text) is None


@pytest.mark.parametrize("text, budget", [
    # Câu có cả lương lẫn mức thuê: mức thuê vẫn được đọc.
    ("lương 12 triệu, tìm phòng Gò Vấp dưới 4 triệu", 4_000_000),
    ("thu nhập của mình tầm 20 củ, tìm studio tổng tháng 6 triệu", 6_000_000),
    # Từ khoá cách số bởi từ nói về phòng/mức thuê → số đó là mức thuê.
    ("lương thấp nên cần phòng dưới 3 triệu", 3_000_000),
    # "chất lượng"/"chat luong" không phải lương.
    ("phòng chất lượng 4 triệu", 4_000_000),
    ("chat luong tot 4 trieu", 4_000_000),
    ("phòng Quận 7 dưới 4 triệu cho 2 người", 4_000_000),
])
def test_rent_amounts_next_to_income_words_still_read(text, budget):
    assert budget_hint(text) == budget
    assert not income_question(text)


def test_income_question_needs_a_question_and_no_rent_amount():
    assert income_question("lương mình 12 triệu thì nên thuê phòng tầm bao nhiêu?")
    assert income_question("thu nhập 15 triệu thuê phòng nào hợp lý")
    assert not income_question("mình kiếm được 10tr/tháng")  # chỉ kể, không hỏi
    assert not income_question("lương 12 triệu thì thuê 3 đến 4 triệu được không?")  # đã nêu khoảng thuê
    assert not income_question("phòng bao nhiêu tiền?")
    assert not income_question("lương 12tr thì vay thêm được không?")  # câu vay → nhánh tài chính


def test_income_housing_levels_round_down_to_stay_under_the_threshold():
    assert income_housing_levels(12_000_000) == {"phu_hop": 3_600_000, "can_nhac": 4_800_000}
    assert income_housing_levels(12_500_000) == {"phu_hop": 3_700_000, "can_nhac": 5_000_000}
    assert income_housing_levels(9_500_000) == {"phu_hop": 2_800_000, "can_nhac": 3_800_000}


@pytest.fixture
def full_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    service = HomeMatchService(tmp_path / "fixes-1118.sqlite")
    yield service
    service.close()


def test_income_question_gets_reference_levels_and_writes_no_budget(full_catalog, renter):
    sid = full_catalog.create_session(renter)["session_id"]
    reply = full_catalog.message(sid, renter, "lương mình 12 triệu một tháng thì nên thuê phòng tầm bao nhiêu?")
    assert reply["status"] == "needs_clarification"
    assert reply["provenance"]["node"] == "income_advice"
    assert "3,6 triệu" in reply["message"] and "4,8 triệu" in reply["message"]
    assert "12" not in reply["message"]  # không nhắc lại số tiền khách kiếm được
    texts = [option["text"] for option in reply["clarification"]["options"]]
    assert texts == ["Tổng tháng dưới 3,6 triệu", "Tổng tháng dưới 4,8 triệu"]
    assert all(option["action"] == "text" for option in reply["clarification"]["options"])
    # Chưa biết thành phố → nhãn không kèm số căn (không đoán).
    assert all("căn" not in option["label"] for option in reply["clarification"]["options"])
    draft = full_catalog._draft(sid)
    assert draft.budget_hint_vnd is None
    assert full_catalog.repo.session(sid)["profile_json"] is None
    # Bấm chip = gửi câu chip; mức tiền đọc tất định từ câu đó.
    assert budget_hint(texts[0]) == 3_600_000


def test_income_chips_count_rooms_once_the_city_is_known(full_catalog, renter):
    sid = full_catalog.create_session(renter)["session_id"]
    full_catalog.message(sid, renter, "phòng Quận 7 TP.HCM")
    reply = full_catalog.message(sid, renter, "thu nhập 12 triệu thì thuê được phòng bao nhiêu")
    labels = [option["label"] for option in reply["clarification"]["options"]]
    assert labels[0].startswith("Tổng tháng dưới 3,6 triệu (") and labels[0].endswith("căn)")
    counts = [option["count"] for option in reply["clarification"]["options"]]
    assert counts[0] <= counts[1]


def test_income_question_takes_no_llm_call_in_openai_mode(tmp_path, monkeypatch, renter):
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    client = FakeClient([])  # gọi model là lỗi
    service = HomeMatchService(tmp_path / "fixes-1118-openai.sqlite",
                               interpreter=OpenAIInterpreter(client=client, model="fixture-model"))
    try:
        sid = service.create_session(renter)["session_id"]
        reply = service.message(sid, renter, "lương mình 12 triệu thì nên thuê phòng tầm bao nhiêu?")
        assert client.requests == []
        assert reply["usage"]["logical_calls"] == 0
        assert reply["provenance"]["node"] == "income_advice"
    finally:
        service.close()


# --- 2. "căn 1" là số thứ tự trong danh sách gợi ý ---

ITEMS = [{"room_id": f"room-{index}"} for index in range(1, 6)]


@pytest.mark.parametrize("text, expected", [
    ("đặt lịch xem căn 1 chiều mai 3 giờ giúp mình", "room-1"),
    ("hẹn xem căn 5 nhé", "room-5"),
    ("Căn 4 mình thích", "room-4"),
    ("căn 3 tiền vào ở hết bao nhiêu?", "room-3"),
    ("xem căn số 2", "room-2"),
    ("căn thứ hai", "room-2"),
    # Số theo sau là đơn vị — không phải số thứ tự.
    ("cho mình xem căn 2 phòng ngủ", None),
    ("căn 1 người ở", None),
    ("tìm căn 30m2", None),
    ("căn 3 triệu", None),
    ("căn 1,5 triệu", None),
    ("căn 2 vợ chồng ở", None),
    ("xem căn 9", None),  # ngoài danh sách
])
def test_plain_room_ordinal_resolves(text, expected):
    assert resolve_room_reference(text, ITEMS) == expected


def test_viewing_by_plain_ordinal_prepares_the_listed_room(full_catalog, renter):
    sid = full_catalog.create_session(renter)["session_id"]
    first = full_catalog.message(sid, renter, "tìm phòng trọ Quận 7 TP.HCM dưới 4 triệu tổng tháng cho 1 người")
    if first["status"] != "published":
        first = full_catalog.message(sid, renter, "chốt luôn giúp mình")
    results = full_catalog.results(sid, renter)["results"]
    assert len(results) >= 2
    reply = full_catalog.message(sid, renter, "đặt lịch xem căn 2 chiều mai 3 giờ giúp mình")
    assert reply["provenance"]["outcome"] == "prepared"
    assert reply["view_payload"]["room_id"] == results[1]["room_id"]
    assert full_catalog.viewings(renter) == []  # chat chỉ chuẩn bị, không tạo lịch


def test_viewing_without_a_reference_asks_by_ordinal_not_room_code(full_catalog, renter):
    sid = full_catalog.create_session(renter)["session_id"]
    no_results = full_catalog.message(sid, renter, "đặt lịch xem phòng giúp mình")
    assert no_results["provenance"]["outcome"] == "missing_room_reference"
    assert "chưa có danh sách gợi ý" in no_results["message"]
    full_catalog.message(sid, renter, "tìm phòng trọ Quận 7 TP.HCM dưới 4 triệu tổng tháng cho 1 người")
    if not full_catalog.results(sid, renter)["results"]:
        full_catalog.message(sid, renter, "chốt luôn giúp mình")
    reply = full_catalog.message(sid, renter, "đặt lịch xem phòng giúp mình")
    assert reply["provenance"]["outcome"] == "missing_room_reference"
    assert "căn 1" in reply["questions"][0] and "mã phòng" not in reply["questions"][0]
    assert "demo-01" not in reply["questions"][0]


# --- 3. Hiệu/tổng của hai số có căn cứ trong câu trả lời ---

PAYLOAD = ('{"rooms": [{"monthly_total_vnd": 3142000, "area_m2": 20}, '
           '{"monthly_total_vnd": 3157000, "area_m2": 28}], "budget": 5000000}')


def test_difference_of_two_grounded_numbers_in_the_answer_is_kept():
    answer = ("Căn 1: 3.142.000 ₫/tháng. Căn 3: 3.157.000 ₫/tháng. "
              "Căn 1 rẻ hơn 15.000 ₫/tháng.")
    assert check_numbers(answer, "so sánh căn 1 và căn 3", [PAYLOAD]) == answer
    total = "Hai căn cộng lại 6.299.000 ₫ (3.142.000 ₫ + 3.157.000 ₫)."
    assert check_numbers(total, "", [PAYLOAD]) == total


def test_wrong_or_unanchored_derived_numbers_are_still_replaced():
    wrong = "Căn 1: 3.142.000 ₫, căn 3: 3.157.000 ₫; căn 1 rẻ hơn 25.000 ₫."
    assert check_numbers(wrong, "so sánh", [PAYLOAD]).startswith(SAFE_TEMPLATE)
    # Hai giá không có trong câu trả lời → hiệu không kiểm được trong câu → thay.
    unanchored = "Căn 3 tổng tháng cao hơn 15.000 ₫."
    assert check_numbers(unanchored, "so sánh", [PAYLOAD]).startswith(SAFE_TEMPLATE)
    # Hai số bịa không tạo được hiệu hợp lệ.
    fabricated = "Căn 1: 2.000.000 ₫, căn 3: 2.500.000 ₫; chênh 500.000 ₫."
    assert check_numbers(fabricated, "so sánh", [PAYLOAD]).startswith(SAFE_TEMPLATE)
