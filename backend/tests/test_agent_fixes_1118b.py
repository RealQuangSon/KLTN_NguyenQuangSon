"""Sửa 4 lỗi lặp lại 3/3 lần đo live held-out K (18/11).

1. "cho mình gặp nhân viên hỗ trợ" phải tạo phiếu hỗ trợ; model không được hứa
   chuyển nhân viên khi không có phiếu.
2. "cho mình đi xem căn đầu tiên" là chuẩn bị lịch xem; model gọi căn bằng số thứ
   tự trần ("3", "thứ ba") vẫn ra đúng căn, và mã căn không lọt vào câu trả lời.
3. "2 vợ chồng với 1 em bé" là 3 người.
4. "under 8 million" là mức 8 triệu.

Tất cả offline: model là FakeClient kịch bản hóa, không gọi mạng.
"""
import pytest

from backend.app.agent_guard import resolve_model_room_ref, viewing_intent
from backend.app.agent_loop import SUPPORT_HINT_REPLY, guard_output, scrub_room_codes
from backend.app.agent_tools import tool_specs
from backend.app.interpreter import OpenAIInterpreter, budget_hint, fixed_intent, people_hint, redact
from backend.app.models import Profile, Scenario
from backend.app.service import HomeMatchService
from backend.tests.test_multi_agent import FakeClient, call, message


@pytest.fixture
def full_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    service = HomeMatchService(tmp_path / "fixes-1118b.sqlite")
    yield service
    service.close()


def openai_service(tmp_path, monkeypatch, turns, analyst="off"):
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", analyst)
    client = FakeClient(turns)
    service = HomeMatchService(tmp_path / f"fixes-1118b-{analyst}.sqlite",
                               interpreter=OpenAIInterpreter(client=client, model="fixture-model"))
    return service, client


def published_session(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=6_000_000,
                                         max_initial_cash_vnd=8_000_000, scenario=Scenario(people=1)), 0)
    results = service.results(sid, renter)["results"]
    assert len(results) >= 3
    return sid, results


# --- 1. Gặp nhân viên hỗ trợ ---

@pytest.mark.parametrize("text", [
    "cho mình gặp nhân viên hỗ trợ",
    "cho em gặp nhân viên",
    "liên hệ admin giúp mình",
    "cho mình nói chuyện với tư vấn viên",
    "chuyển mình sang bộ phận hỗ trợ",
    "mình muốn gọi tổng đài",
    "chăm sóc khách hàng ơi",
    "mình cần người thật",
])
def test_asking_for_platform_staff_is_human_support(text):
    assert fixed_intent(text) == "human_support"


@pytest.mark.parametrize("text, expected", [
    ("mình là nhân viên văn phòng, tìm phòng Quận 1 tầm 4 triệu", None),
    ("chat với chủ nhà căn 2", "landlord_handover"),
    ("tìm phòng gần công ty, ở với đồng nghiệp", None),
])
def test_other_mentions_of_staff_are_not_support(text, expected):
    assert fixed_intent(text) == expected


def test_support_request_creates_a_ticket_without_calling_the_model(tmp_path, monkeypatch, renter):
    service, client = openai_service(tmp_path, monkeypatch, [], analyst="rules")
    try:
        sid = service.create_session(renter)["session_id"]
        reply = service.message(sid, renter, "cho mình gặp nhân viên hỗ trợ")
        assert reply["status"] == "support_requested" and reply["ticket_id"]
        assert client.requests == []
    finally:
        service.close()


@pytest.mark.parametrize("answer", [
    "Mình sẽ chuyển bạn đến nhân viên hỗ trợ ngay nhé.",
    "Mình đã kết nối bạn với bộ phận chăm sóc khách hàng.",
    "Nhân viên sẽ liên hệ bạn trong ít phút.",
])
def test_model_promise_of_staff_handoff_is_replaced(answer):
    checked, violation = guard_output(answer, [])
    assert (checked, violation) == (SUPPORT_HINT_REPLY, "unbacked_claim")


@pytest.mark.parametrize("answer", [
    "Bạn bấm “Báo cáo tin” để báo quản trị viên kiểm tra tin đăng.",
    "Mình chuyển câu hỏi này cho chủ nhà khi bạn bấm Chat với chủ nhà.",
])
def test_instructions_that_are_not_handoff_promises_are_kept(answer):
    assert guard_output(answer, []) == (answer, None)


# --- 2. Đi xem căn đầu tiên ---

@pytest.mark.parametrize("text, expected", [
    ("cho mình đi xem căn đầu tiên", True),
    ("qua xem căn 2 chiều mai được không", True),
    ("ghé xem căn này cuối tuần", True),
    ("mình muốn xem trực tiếp căn cuối", True),
    ("đặt lịch xem phòng giúp mình", True),  # cụm cũ: hỏi lại căn nào
    # Chưa nhắc căn cụ thể → vẫn là câu tìm phòng.
    ("cuối tuần mình muốn đi xem phòng ở Quận 7 tầm 4 triệu", False),
    ("tìm căn hộ để đi xem cuối tuần", False),
    # "xem căn thứ ba" không có động từ đi xem — để agent hiểu (xem chi tiết hay đi xem).
    ("xem căn thứ ba được không", False),
])
def test_viewing_intent_needs_a_go_see_verb_and_a_specific_room(text, expected):
    assert viewing_intent(text) is expected


ITEMS = [{"room_id": f"room-{index}"} for index in range(1, 6)]


@pytest.mark.parametrize("ref, expected", [
    ("3", "room-3"), ("thứ ba", "room-3"), ("đầu tiên", "room-1"), ("phòng 2", "room-2"),
    ("#1", "room-1"), ("căn số 2", "room-2"), ("cuối", "room-5"), ("Căn thứ 4", "room-4"),
    ("9", None), ("căn hộ", None),
])
def test_model_room_reference_accepts_bare_ordinals(ref, expected):
    assert resolve_model_room_ref(ref, ITEMS) == expected


def test_go_see_first_room_prepares_it_deterministically(full_catalog, renter):
    sid, results = published_session(full_catalog, renter)
    reply = full_catalog.message(sid, renter, "cho mình đi xem căn đầu tiên")
    assert reply["provenance"]["outcome"] == "prepared"
    assert reply["view_payload"]["room_id"] == results[0]["room_id"]
    assert results[0]["room_id"] not in reply["message"]
    assert full_catalog.viewings(renter) == []  # chat chỉ chuẩn bị


def test_prepare_viewing_is_offered_once_results_exist():
    assert "prepare_viewing" not in {spec["function"]["name"] for spec in tool_specs("interview")}
    results_tools = {spec["function"]["name"] for spec in tool_specs("results")}
    assert "prepare_viewing" in results_tools and "open_landlord_chat" not in results_tools


def test_model_prepares_viewing_by_bare_ordinal_and_no_room_code_leaks(tmp_path, monkeypatch, renter):
    service, client = openai_service(tmp_path, monkeypatch, [])
    try:
        sid, results = published_session(service, renter)
        third = results[2]["room_id"]
        client.turns = [
            message(tool_calls=[call("c1", "prepare_viewing", room_ref="thứ ba")]),
            message(f"Mình đã mở căn {third} để bạn chọn giờ xem."),
        ]
        reply = service.message(sid, renter, "xem căn thứ ba được không")
        assert reply["view"] == "detail" and reply["view_payload"]["room_id"] == third
        assert reply["provenance"]["outcome"] == "prepared"
        assert third not in reply["message"] and "Căn 3" in reply["message"]
        assert service.viewings(renter) == []
        # Tool có trong bộ tool gửi model ở pha results.
        sent = {spec["function"]["name"] for spec in client.requests[0]["tools"]}
        assert "prepare_viewing" in sent
    finally:
        service.close()


def test_room_codes_in_answers_become_list_positions():
    answer = "Liên hệ chủ nhà qua tin đăng chotot-22 hoặc (chotot-99); căn chotot-11 rẻ hơn."
    assert scrub_room_codes(answer, ["chotot-11", "chotot-22"]) == \
        "Liên hệ chủ nhà qua Căn 2 hoặc căn này; Căn 1 rẻ hơn."


# --- 3. Số người theo thành phần gia đình ---

@pytest.mark.parametrize("text, expected", [
    ("Mình 2 vợ chồng với 1 em bé, cần căn hộ Thanh Xuân", (3, False)),
    ("vợ chồng và 2 đứa con", (4, False)),
    ("vợ chồng mình với hai bé", (4, False)),
    ("gia đình 2 vợ chồng 1 con", (3, False)),
    ("2 vợ chồng", (2, False)),
    ("vợ chồng có con nhỏ", (None, True)),  # không nêu số con → hỏi lại
    ("mình với 2 đứa bạn", (None, True)),
    # Câu tiếng Anh: đọc được mức tiền nên đi đường tắt luật — số người cũng phải đọc được.
    ("find a studio in Saigon under 8 million for 1 person", (1, False)),
    ("room for 2 people in Hanoi", (2, False)),
])
def test_people_from_family_composition_and_english(text, expected):
    assert people_hint(text) == expected


def test_family_sentence_records_three_people(full_catalog, renter):
    sid = full_catalog.create_session(renter)["session_id"]
    full_catalog.message(sid, renter, "Mình 2 vợ chồng với 1 em bé, cần căn hộ Thanh Xuân Hà Nội khoảng 8 triệu")
    session = full_catalog.repo.session(sid)
    if session.get("profile_json"):
        assert Profile.model_validate_json(session["profile_json"]).scenario.people == 3
    else:
        assert full_catalog._draft(sid).people == 3


# --- 4. Mức tiền viết bằng tiếng Anh ---

@pytest.mark.parametrize("text, amount", [
    ("find a studio in Saigon under 8 million for 1 person", 8_000_000),
    ("budget 6.5 million", 6_500_000),
    ("max 7 mil", 7_000_000),
    ("phòng 30 m2", None),
])
def test_english_million_reads_as_budget(text, amount):
    assert budget_hint(text) == amount


def test_english_million_is_redacted_before_the_model():
    assert "8 million" not in redact("find a studio in Saigon under 8 million")


def test_english_budget_sentence_records_the_budget(full_catalog, renter):
    sid = full_catalog.create_session(renter)["session_id"]
    full_catalog.message(sid, renter, "find a studio in Saigon under 8 million for 1 person")
    session = full_catalog.repo.session(sid)
    if session.get("profile_json"):
        profile = Profile.model_validate_json(session["profile_json"])
        assert 8_000_000 in {profile.max_monthly_cost_vnd, profile.max_rent_vnd}
    else:
        assert full_catalog._draft(sid).budget_hint_vnd == 8_000_000
    draft_people = full_catalog._draft(sid).people
    profile_people = (Profile.model_validate_json(session["profile_json"]).scenario.people
                      if session.get("profile_json") else None)
    assert 1 in {draft_people, profile_people}
