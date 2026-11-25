"""Phỏng vấn khi khách nói chưa rõ (kiểm 17/11, sửa 18/11).

Lỗ hổng 1 — số người viết bằng chữ ("hai người", "2 vợ chồng") bị bỏ qua và cụm ở
chung không số ("mấy đứa bạn", "gia đình") bị tìm lặng lẽ theo mặc định 1 người.
Lỗ hổng 2 — "gần trường đại học" chưa nêu tên không được hỏi trường nào; nút gợi ý
là các điểm mốc nhiều căn nhất (trung tâm thương mại), không phải trường.
Lỗ hổng 3 — bấm nút khi chưa đủ dữ liệu: không có câu hỏi tiếp theo kèm nút, và
câu trả lời hứa "kết quả sẽ tự hiện" dù chưa tìm.
Mọi model là client giả — không gọi mạng, không provider trả phí.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.catalog import Catalog
from backend.app.agent_loop import no_match_scope, unrepeated_question
from backend.app.interpreter import (DemoInterpreter, OpenAIInterpreter, destination_dropped, destination_kind_hint,
                                     near_place_text, people_hint)
from backend.app.locations import _PLACES, place_kind, resolve_place
from backend.app.main import create_app
from backend.app.models import DraftPatch, DraftProfile, Profile, Scenario
from backend.app.service import HomeMatchService


def call(id_, name, **arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name,
                                                            arguments=json.dumps(arguments, ensure_ascii=False)))


def message(content=None, tool_calls=None, tokens=7):
    usage = SimpleNamespace(total_tokens=tokens)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))], usage=usage)


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        if not self.turns:
            raise AssertionError("FakeClient hết kịch bản phản hồi")
        return self.turns.pop(0)


# Kho tổng hợp 220 căn cố định trong repo (TP.HCM 120, Hà Nội 100): đủ trường, quận
# và mức giá để kho dựng được nút như khi chạy thật.
CATALOG = "data/catalog/rooms.json"


@pytest.fixture
def service(tmp_path):
    agent = HomeMatchService(tmp_path / "interview-unclear.sqlite", catalog=Catalog(CATALOG))
    yield agent
    agent.close()


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    agent = HomeMatchService(tmp_path / "interview-unclear-loop.sqlite", catalog=Catalog(CATALOG),
                             interpreter=OpenAIInterpreter(client=SimpleNamespace(), model="fixture-model"))
    yield agent
    agent.close()


def _patch(service, sid, renter, option):
    revision = service.repo.session(sid)["draft_revision"]
    return service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision,
                                                       set=option["patch"]["set"], source="clarify"))


def _profile_people(service, sid):
    return json.loads(service.repo.session(sid)["profile_json"])["scenario"]["people"]


# --- Lỗ hổng 1: số người ---


@pytest.mark.parametrize("text, expected", [
    ("phòng cho hai người", (2, False)),
    ("ba người ở", (3, False)),
    ("2 vợ chồng", (2, False)),
    ("vợ chồng mình", (2, False)),
    ("cặp đôi", (2, False)),
    ("gia đình 4 người", (4, False)),
    ("3 đứa sinh viên", (3, False)),
    ("ở một mình", (1, False)),
    ("dưới 4 triệu cho 1 người", (1, False)),
    # 18/11 (sửa lỗi đo live K): nêu SỐ con thì tổng là 2 + số con; chỉ "vợ chồng có
    # con nhỏ" không số mới chưa rõ (test_agent_fixes_1118b).
    ("vợ chồng và 2 đứa con", (4, False)),
    ("vợ chồng có con nhỏ", (None, True)),
    ("mấy đứa bạn ở chung", (None, True)),
    ("gia đình nhỏ", (None, True)),
    ("mình với bạn", (None, True)),
    ("mình với 2 đứa bạn", (None, True)),
    # Không phải nói về số người.
    ("phòng có ban công", (None, False)),
    ("phòng với chi phí thấp", (None, False)),
    ("không chung chủ", (None, False)),
    ("ở chung với chủ được không", (None, False)),
    ("phòng 25m2 2 phòng ngủ", (None, False)),
    ("ở ghép", (None, False)),
])
def test_people_hint_reads_words_couples_and_flags_groups(text, expected):
    assert people_hint(text) == expected


def test_demo_interpreter_reads_people_in_words():
    assert DemoInterpreter().extract("tìm phòng quận 7 cho hai vợ chồng").people == 2


def test_group_without_count_asks_people_before_searching(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "phòng ở quận 7 cho mấy đứa bạn ở chung, tổng tháng 6 triệu")
    dto = reply["clarification"]
    assert reply["status"] == "needs_clarification"
    assert dto["field"] == "people" and dto["question"] == "Bạn ở chung tổng cộng mấy người?"
    # Khách đã nói ở chung → lựa chọn từ 2 người, không có "1 người".
    assert [option["detail"] for option in dto["options"]] == ["Ở 2 người", "Ở 3 người", "Ở 4 người"]
    assert service.repo.session(sid)["active_run_id"] is None
    picked = _patch(service, sid, renter, dto["options"][1])
    assert picked["status"] in {"published", "no_match"}
    assert _profile_people(service, sid) == 3
    assert service._draft(sid).needs_people is False


def test_people_in_words_search_for_that_many(service, renter):
    for text in ("phòng Quận 7 TP.HCM tổng tháng dưới 6 triệu cho 2 vợ chồng",
                 "phòng Quận 7 TP.HCM tổng tháng dưới 6 triệu cho hai người"):
        sid = service.create_session(renter)["session_id"]
        reply = service.message(sid, renter, text)
        assert reply["status"] == "published", (text, reply.get("questions"))
        assert _profile_people(service, sid) == 2, text


def test_people_question_is_not_cut_by_the_question_limit(service, renter):
    """Câu hỏi làm rõ LỜI KHÁCH ("mấy đứa bạn") không bị giới hạn 2 câu hỏi thay bằng
    một lượt tìm theo mặc định 1 người."""
    sid = service.create_session(renter)["session_id"]
    service.repo.db.execute("UPDATE hm_sessions SET clarification_questions=2 WHERE id=?", (sid,))
    reply = service.message(sid, renter, "phòng ở quận 7 cho mấy đứa bạn ở chung, tổng tháng 6 triệu")
    assert reply["clarification"]["field"] == "people"
    assert service.repo.session(sid)["active_run_id"] is None
    assert service.repo.session(sid)["clarification_questions"] == 2


def test_fast_path_asks_people_without_calling_the_model(agent, renter):
    agent.interpreter.client = FakeClient([])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng Quận 7 TP.HCM tổng tháng 6 triệu cho mấy đứa bạn ở chung")
    assert reply["agent_mode"] == "fast_path"
    assert reply["clarification"]["field"] == "people"
    assert agent.repo.session(sid)["active_run_id"] is None


def test_model_cannot_guess_people_when_renter_did_not_say(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"people": 3})]),
        message(content="Bạn ở chung tổng cộng mấy người?"),
    ])
    agent.message(sid, renter, "mình với mấy đứa bạn cần phòng ở Bình Thạnh")
    draft = agent._draft(sid)
    assert draft.people is None and draft.needs_people is True


# --- Lỗ hổng 2: "gần trường" chưa nêu tên ---


def test_destination_kind_hint():
    assert destination_kind_hint("cần phòng gần trường đại học") == "school"
    assert destination_kind_hint("gần bệnh viện") == "hospital"
    assert destination_kind_hint("gần bến xe Mỹ Đình") == "transit"
    # "gần chỗ làm" là chỗ riêng của khách chưa nêu tên, không phải loại địa danh.
    assert destination_kind_hint("gần chỗ làm") == "personal"


def test_place_kind_reads_the_leading_name():
    kinds = {place["names"][0]: place_kind(place) for place in _PLACES}
    assert kinds["Đại học Bách Khoa Hà Nội"] == "school"
    assert kinds["Bệnh viện Đại học Y Dược TP.HCM"] == "hospital"
    assert kinds["Bến xe Mỹ Đình"] == "transit"
    assert kinds["Vincom Nguyễn Chí Thanh"] == "mall"  # LOC-001: đọc trường kind


def test_near_school_without_name_offers_only_schools_even_with_a_district(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "cần phòng gần trường đại học ở Cầu Giấy, tổng tháng 4 triệu")
    dto = reply["clarification"]
    assert dto["field"] == "destination" and dto["question"] == "Bạn muốn ở gần trường nào?"
    names = {place["names"][0]: place for place in _PLACES}
    assert dto["options"]
    for option in dto["options"]:
        name = option["detail"].removeprefix("Gần ")
        assert place_kind(names[name]) == "school", option["detail"]
    assert service.repo.session(sid)["active_run_id"] is None


def test_landmark_followed_by_money_keeps_the_destination(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "phòng gần Đại học Quốc gia Hà Nội tầm 4 triệu")
    draft = service._draft(sid)
    assert draft.destination is not None and draft.destination.label == "Đại học Quốc gia Hà Nội"


# --- Lỗ hổng 3: bấm nút khi chưa đủ dữ liệu ---


def test_city_chip_without_budget_asks_budget_with_chips(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "tìm giúp mình một phòng")
    city = next(option for option in reply["clarification"]["options"]
                if option["patch"]["set"].get("city") == "Hà Nội")
    after = _patch(service, sid, renter, city)
    assert after["status"] == "needs_clarification"
    assert after["message"] == "Bạn muốn chi bao nhiêu mỗi tháng?"
    assert after["clarification"]["field"] == "budget_cap" and after["clarification"]["options"]
    assert after["questions"] == ["Bạn muốn chi bao nhiêu mỗi tháng?"]
    assert service.repo.session(sid)["active_run_id"] is None


def test_chip_that_searches_returns_the_result_sentence(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "phòng ở Cầu Giấy tầm 4 triệu")
    assert reply["clarification"]["field"] == "budget_scope"
    total = next(option for option in reply["clarification"]["options"]
                 if option["patch"]["set"].get("budget_scope") == "total")
    after = _patch(service, sid, renter, total)
    assert after["status"] in {"published", "no_match"}
    assert "căn" in after["message"]


def test_api_patch_returns_message_and_follow_up_chips(service):
    with TestClient(create_app(lambda: service)) as client:
        _api_patch_flow(client)


def _api_patch_flow(client):
    headers = {"Authorization": "Bearer demo-renter"}
    sid = client.post("/sessions", headers=headers).json()["session_id"]
    reply = client.post(f"/sessions/{sid}/messages", headers=headers,
                        json={"text": "tìm giúp mình một phòng"}).json()
    city = reply["clarification"]["options"][0]
    after = client.patch(f"/sessions/{sid}/draft", headers=headers, json={
        "expected_draft_revision": reply["draft_revision"], "set": city["patch"]["set"],
        "clear_fields": [], "remove_preferences": [], "source": "clarify"})
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["message"] == "Bạn muốn chi bao nhiêu mỗi tháng?"
    assert body["clarification"]["field"] == "budget_cap"


# --- Đo live 18/11: bốn vấn đề lộ ra sau khi sửa ba lỗ hổng ---


@pytest.mark.parametrize("template", ["gần {}", "phòng gần {}, tầm 4 triệu",
                                      "cần phòng gần {} cho 2 người", "gần {}. Tổng tháng 5 triệu"])
def test_every_landmark_name_reads_back_as_that_landmark(template):
    """D: tên có "TP.HCM", " - ", "(…)" bị cắt ("Đại học Y Dược TP") → bấm chip điểm
    đến không ra điểm đến (15/68 điểm mốc trước khi sửa)."""
    failed = []
    for place in _PLACES:
        for name in place["names"]:
            text = DemoInterpreter().extract(template.format(name)).destination_text
            found = resolve_place(text or "", place["city"])
            if not found or found["id"] != place["id"]:
                failed.append((name, text))
    assert failed == []


def test_near_place_text_stops_at_sentence_end_and_money():
    assert near_place_text("gần ĐH Quốc gia Hà Nội tầm 4 triệu") == "ĐH Quốc gia Hà Nội"
    assert near_place_text("gần Bệnh viện Đại học Y Dược TP.HCM. Tầm 5 triệu") \
        == "Bệnh viện Đại học Y Dược TP.HCM"
    assert near_place_text("phòng (gần chợ Bến Thành)") == "chợ Bến Thành"
    assert near_place_text("phòng có ban công") is None


def test_clicking_a_dotted_hospital_chip_sets_the_destination(service, renter):
    """D, demo/rơi về graph: trước khi sửa chip "Gần Bệnh viện Đại học Y Dược TP.HCM"
    gửi đi rồi nhận lại đúng bộ chip đó (vòng lặp)."""
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "phòng gần bệnh viện ở TP.HCM, tổng tháng 5 triệu")
    # LOC-001: tọa độ đã đối chiếu OSM nên bệnh viện này không còn nằm trong 4 chip đầu;
    # chip chữ chỉ là "gần <tên>", gửi đúng chuỗi đó.
    assert all(item["text"].startswith("gần ") for item in reply["clarification"]["options"])
    after = service.message(sid, renter, "gần Bệnh viện Đại học Y Dược TP.HCM")
    assert service._draft(sid).destination.label == "Bệnh viện Đại học Y Dược TP.HCM"
    assert (after.get("clarification") or {}).get("field") != "destination"


def test_no_match_rerun_with_only_a_new_description_says_conditions_are_unchanged(agent, renter):
    """A (landmark-ho-guom#2): model chỉ viết lại mô tả → câu no_match lặp nguyên văn."""
    sid = agent.create_session(renter)["session_id"]
    before = Profile(city="Hà Nội", area="Quận Hoàn Kiếm", max_monthly_cost_vnd=5_000_000,
                     max_rent_vnd=5_000_000, scenario=Scenario())
    after = before.model_copy(update={"soft_description": "Gần Hồ Gươm, ở Hoàn Kiếm cũng được",
                                      "preferences": ["balcony"], "prefer_cheapest": True})
    assert no_match_scope(agent, sid, after, before.model_dump_json())["unchanged"] is True
    tighter = before.model_copy(update={"max_monthly_cost_vnd": 4_000_000})
    assert no_match_scope(agent, sid, tighter, before.model_dump_json())["unchanged"] is False


def test_repeated_catalog_question_acknowledges_what_was_just_noted(agent, renter):
    """B (answer-free-text#2): khách trả lời "tổng tháng, 1 người", model gọi lại
    ask_user(city) không kèm câu riêng → trước đây lặp nguyên văn câu lượt trước."""
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="city")]),
        message(tool_calls=[call("c2", "ask_user", field="city")]),
    ])
    first = agent.message(sid, renter, "cần phòng gần trường đại học, 3 triệu")
    second = agent.message(sid, renter, "tổng tháng, 1 người")
    assert first["message"] == "Bạn muốn thuê tại thành phố nào?"
    assert second["message"] != first["message"]
    assert second["message"] == ("Mình đã ghi nhận 1 người, tính theo tổng tháng. "
                                 "Bạn muốn thuê tại thành phố nào?")
    assert second["questions"] == ["Bạn muốn thuê tại thành phố nào?"]
    assert second["clarification"]["field"] == "city" and second["clarification"]["options"]


def test_repeated_question_without_new_information_says_why_it_is_still_needed():
    draft = DraftProfile(city="TP.HCM", area="Quận 7", budget_hint_vnd=4_000_000)
    question = "Mức tiền bạn nêu hiểu thế nào cho đúng?"
    pending = {"field": "budget_scope", "question": question}
    assert unrepeated_question(question, {"question_source": "catalog"}, pending, draft, draft) \
        == "Mình cần bạn chốt điều này trước khi tìm phòng. " + question
    # Câu do model tự viết, hoặc câu hỏi mới → giữ nguyên.
    assert unrepeated_question(question, {"question_source": "model"}, pending, draft, draft) == question
    assert unrepeated_question(question, {"question_source": "catalog"}, None, draft, draft) == question


def test_city_named_in_the_sentence_is_not_asked_again(agent, renter):
    """C: model hỏi điểm đến trước khi ghi thành phố → hệ thống đổi sang "thành phố
    nào?" dù khách đã nói "ở TP.HCM"."""
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="destination")]),
    ])
    reply = agent.message(sid, renter, "phòng gần bệnh viện ở TP.HCM, tổng tháng 5 triệu")
    draft = agent._draft(sid)
    assert draft.city == "TP.HCM" and draft.field_status["city"] == "inferred"
    dto = reply["clarification"]
    assert dto["field"] == "destination" and dto["question"] == "Bạn muốn ở gần bệnh viện nào?"
    names = {place["names"][0]: place for place in _PLACES}
    assert all(place_kind(names[option["detail"].removeprefix("Gần ")]) == "hospital"
               for option in dto["options"])


def test_district_pins_the_city_but_two_cities_pin_nothing(service):
    draft = DraftProfile()
    service._text_needs_into_draft(draft, service._parse_text_needs("phòng gần trường ở Bình Thạnh"))
    assert draft.city == "TP.HCM"
    other = DraftProfile()
    service._text_needs_into_draft(other, service._parse_text_needs(
        "mình đang ở Hà Nội, muốn thuê phòng ở TP.HCM"))
    assert other.city is None
    kept = DraftProfile(city="Hà Nội")
    service._text_needs_into_draft(kept, service._parse_text_needs("thôi đổi sang TP.HCM"))
    assert kept.city == "Hà Nội"  # không ghi đè — đổi thành phố đi cùng quận, do model/khách xử lý


@pytest.mark.parametrize("text", ["Tìm phòng trọ gần Bách Khoa TP.HCM 3 triệu cho 1 người",
                                  "Tìm phòng trọ gần Bách Khoa TP.HCM [TIEN_DA_TACH] cho 1 người"])
def test_dotted_landmark_followed_by_money_stops_before_the_money(text):
    """Bắt khi chạy lại eval (AE35): tiền ngay sau "TP.HCM" — bản thô và bản đã che."""
    assert near_place_text(text) == "Bách Khoa TP.HCM"


def test_model_cannot_drop_a_destination_the_renter_asked_for(agent, renter):
    """Đo live 18/11 lần P2 (near-school-district): model ghi needs_destination=false →
    bấm nút số người là tìm luôn, không hỏi trường nào."""
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"area": "Quận Cầu Giấy", "needs_destination": False})]),
        message(tool_calls=[call("c2", "ask_user", field="destination")]),
    ])
    reply = agent.message(sid, renter, "cần phòng gần trường đại học ở Cầu Giấy, tổng tháng 4 triệu")
    draft = agent._draft(sid)
    assert draft.needs_destination is True and draft.destination_kind == "school"
    assert reply["clarification"]["field"] == "destination"


@pytest.mark.parametrize("text", ["không cần gần trường nữa", "thôi bỏ gần bệnh viện đi",
                                  "khỏi cần ở gần bến xe"])
def test_renter_can_drop_the_destination_themself(text):
    assert destination_kind_hint(text) is None
    assert destination_dropped(text)


def test_near_school_is_not_a_drop():
    assert not destination_dropped("cần phòng gần trường đại học")
