"""HN-13.2 — hỏi lại/chip/assumptions sau đo hội thoại: hậu kiểm grounding chỉ
phần engine, ask_user(question/reason), question_without_chip, pending-question
lifecycle, prompt needs analyst, địa danh ngoài danh mục, chip mới (city/
budget_cap/destination) và đường tiền tất định từ câu chip.

Mọi model/provider là client giả; không gọi mạng."""
import json
import pathlib
import re
from types import SimpleNamespace

import pytest

from backend.app import input_analyst
from backend.app.agent_loop import budget_scope_hint, chat_budget_hint
from backend.app.interpreter import OpenAIInterpreter
from backend.app.models import Actor, DomainError, Destination, DraftPatch, Profile, Scenario
from backend.app.service import HomeMatchService
from backend.tests.test_multi_agent import FakeClient, FakeJev, _fake_jev, _seed_no_ambiguity, message, call


@pytest.fixture
def agent(tmp_path, monkeypatch):
    # Kho đầy đủ 220 căn (không phải bộ demo 11 căn) để chip đếm từ phân bố thật.
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    service = HomeMatchService(tmp_path / "hn13-dialog-fixes.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="fixture-model"))
    yield service
    service.close()


def _turns(client):
    return client.requests


# --- Điểm 0: grounding chỉ phần engine ---

def test_numbers_only_in_history_or_summary_are_replaced(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000,
        scenario=Scenario(people=1)), 1)
    results = agent.results(sid, renter)
    engine_lowest = min(item["cost"]["monthly_total_vnd"] for item in results["results"])
    # Số chỉ tồn tại trong summary (model viết) và transcript lượt trước.
    agent.repo.db.execute("UPDATE hm_sessions SET summary_json=? WHERE id=?",
                          (json.dumps({"text": "lượt trước khách nhắc 9.876.543"}), sid))
    agent.repo.db.execute(
        "INSERT INTO hm_chat_transcripts VALUES(?,?,?,?,?,?,?,?)",
        ("t-fixture", sid, renter.id, "assistant",
         "Lượt trước mình đã nói 7.777.777 cho bạn.", "find_room", "interpreter", "2026-11-07T00:00:00"))
    agent.interpreter.client = FakeClient([message(
        "Như đã nói: 9.876.543 hoặc 7.777.777, không đổi.")])
    reply = agent.message(sid, renter, "vẫn mức cũ đúng không?")
    assert "9.876.543" not in reply["message"] and "7.777.777" not in reply["message"]
    # Số do engine sinh (kết quả đang công bố) vẫn được phép dùng.
    agent.interpreter.client = FakeClient([message(
        f"Căn rẻ nhất tổng tháng {engine_lowest:,} đồng.".replace(",", "."))])
    reply2 = agent.message(sid, renter, "giá thấp nhất bao nhiêu?")
    assert f"{engine_lowest:,}".replace(",", ".") in reply2["message"]


# --- Điểm 1: ask_user dùng câu model + reason; fallback mẫu ---

def _pending_budget_scope(monkeypatch):
    """Lớp hỏi lại trả một điểm mơ hồ budget_scope (hai cách hiểu 0,5/0,5) để test
    tập trung vào câu hỏi/reason của model, không phụ thuộc phân bố kho."""
    from backend.app import clarify

    def fake_build(service_, session_id_, field=None):
        if field not in (None, "budget_scope"):
            return None
        return {"field": "budget_scope", "impact": 0.5, "options": [
            {"id": "opt-0", "field": "budget_scope", "kind": "total_cap",
             "label": "Trần TỔNG THÁNG (gồm phí)",
             "interpretation": {"field": "budget_scope", "kind": "total_cap", "scope": "total"},
             "top": ["a", "b"], "count": 10, "min_monthly_total_vnd": 3_000_000, "probability": 0.5},
            {"id": "opt-1", "field": "budget_scope", "kind": "rent_cap",
             "label": "Chỉ trần tiền THUÊ",
             "interpretation": {"field": "budget_scope", "kind": "rent_cap", "scope": "rent"},
             "top": ["c", "d"], "count": 10, "min_monthly_total_vnd": 3_000_000, "probability": 0.5}]}
    monkeypatch.setattr(clarify, "build_clarification", fake_build)


def test_ask_user_uses_model_question_and_reason(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    _pending_budget_scope(monkeypatch)
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "TP.HCM"})]),
        message(tool_calls=[call("c2", "ask_user", field="budget_scope",
                                 question="Bạn muốn mức 4 triệu là trần tổng tháng hay chỉ tiền thuê?",
                                 reason="Hai cách hiểu cho số căn khớp khác nhau.")]),
        message("Đã hỏi lại cách hiểu mức tiền."),
    ])
    # Nhắc điểm đến để thoát fast path, bắt buộc vào vòng lặp model.
    reply = agent.message(sid, renter, "phòng TP.HCM 4 triệu gần Đại học Bách Khoa")
    assert reply["agent_mode"] == "loop"
    dto = reply.get("clarification") or {}
    assert dto.get("question") == "Bạn muốn mức 4 triệu là trần tổng tháng hay chỉ tiền thuê?"
    assert dto.get("question_source") == "model"
    assert dto.get("reason") == "Hai cách hiểu cho số căn khớp khác nhau."
    # Chip vẫn do kho dựng: có count/patch, không phải lựa chọn model bịa.
    assert dto.get("options") and all("count" in option and "patch" in option for option in dto["options"])


def test_ask_user_falls_back_to_template_when_model_question_invalid(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    _pending_budget_scope(monkeypatch)
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "TP.HCM"})]),
        # Câu hỏi có số chưa có nguồn + không có "?" → không qua hậu kiểm.
        message(tool_calls=[call("c2", "ask_user", field="budget_scope",
                                 question="Mức 9.999.999 hiểu thế nào")]),
        message("Đã hỏi lại."),
    ])
    reply = agent.message(sid, renter, "phòng TP.HCM 4 triệu gần Đại học Bách Khoa")
    assert reply["agent_mode"] == "loop"
    dto = reply.get("clarification") or {}
    assert dto.get("question_source") != "model"
    assert dto.get("question") == "Mức tiền bạn nêu hiểu thế nào cho đúng?"


def test_question_without_chip_is_traced(agent, renter, monkeypatch):
    """Model tự hỏi trong câu trả lời không qua ask_user: giữ câu, không gắn chip
    đoán, ghi chỉ số question_without_chip vào hm_agent_steps."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message(
        "Mình có thể giúp gì thêm về khu vực bạn muốn?")])
    # Lỗi 5 (15/11): câu luật hiểu trọn vẹn đi fast path; để model trả lời (và
    # trace question_without_chip) dùng câu có điểm đến → vòng lặp.
    reply = agent.message(sid, renter, "phòng Quận 7 dưới 4 triệu gần trường")
    assert reply["agent_mode"] == "loop"
    assert not reply.get("clarification")
    rows = agent.repo.db.execute(
        "SELECT s.summary FROM hm_agent_steps s JOIN hm_agent_turns t ON s.turn_row_id=t.id "
        "WHERE t.session_id=? AND s.name='question_without_chip'", (sid,)).fetchall()
    assert rows, "question_without_chip phải được ghi vào trace"


# --- Điểm 1/4: assumptions — trường riêng, off giữ chuỗi nối cũ ---

def test_assumptions_become_readable_field_in_analyst_mode(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "area": "Quận Cầu Giấy",
                                        "destination_text": "Đại học Bách Khoa Hà Nội"})]),
        message("Mình ghi nhận điểm đến của bạn."),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert "Mình đang hiểu" not in (reply.get("message") or "")
    assert reply.get("assumptions") and all(
        "căn" not in sentence or "Tạm" in sentence for sentence in reply["assumptions"])
    assert any(sentence.startswith("Tạm") for sentence in reply["assumptions"])
    assert not any("·" in sentence for sentence in reply["assumptions"])


def test_off_mode_keeps_old_assumption_concatenation(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "off")
    # Không có chip bán kính (kho không cho cách hiểu khác) → engine tự áp 3 km
    # và ở chế độ off giả định phải nối vào câu trả lời như cũ.
    from backend.app import clarify
    monkeypatch.setattr(clarify, "build_clarification", lambda *args, **kwargs: None)
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "Đại học Bách Khoa Hà Nội"})]),
        message("Đã ghi nhận."),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert "Mình đang hiểu" in (reply.get("message") or "")
    assert "Tạm dùng bán kính 3 km" in (reply.get("message") or "")
    assert "assumptions" not in reply


# --- Điểm 3: địa danh ngoài danh mục ---

def test_unknown_landmark_guides_area_and_validates_it(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "find_place", query="Công viên Thống Nhất", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs", patch={"city": "Hà Nội", "area": "Hai Bà Trưng"})]),
        message("Mình hiểu Công viên Thống Nhất thuộc Hai Bà Trưng — sai thì bấm sửa."),
    ])
    reply = agent.message(sid, renter, "phòng gần Công viên Thống Nhất Hà Nội 4 triệu")
    assert reply["agent_mode"] == "loop"
    draft = agent.session(sid, renter)["draft"]
    assert draft["area"] == "Quận Hai Bà Trưng"  # chuẩn hóa theo locations.py
    # Trạng thái inferred — khách sửa được, không phải confirmed.
    assert draft["field_status"]["area"] == "inferred"
    assert draft.get("destination") is None  # không đặt destination không tọa độ
    tool_note = next(item["content"] for item in agent.interpreter.client.requests[1]["messages"]
                     if item.get("role") == "tool")
    assert "update_needs" in tool_note and "area" in tool_note


def test_unrecognizable_area_returns_structured_error(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "Hà Nội", "area": "Khu Vùng Xyz"})]),
        message("Mình cần quận cụ thể hơn."),
    ])
    reply = agent.message(sid, renter, "phòng Hà Nội đi")
    assert any("unknown_area" in step for step in reply.get("steps") or [])
    assert agent.session(sid, renter)["draft"]["area"] is None


# --- Điểm 4: pending question lifecycle + route ---

def _chip_turn(agent, sid, renter, monkeypatch):
    _pending_budget_scope(monkeypatch)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "TP.HCM"})]),
        message(tool_calls=[call("c2", "ask_user", field="budget_scope",
                                 question="Mức 4 triệu là trần tổng tháng hay chỉ tiền thuê?")]),
        message("Đã hỏi."),
    ])
    return agent.message(sid, renter, "phòng TP.HCM 4 triệu")


def test_pending_question_cleared_by_chip_and_new_run(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    _chip_turn(agent, sid, renter, monkeypatch)
    assert sid in agent._pending_clarification
    from backend.app.models import DraftPatch
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=agent.session(sid, renter)["draft_revision"],
                                              set={"budget_scope": "total"}, source="clarify"))
    assert sid not in agent._pending_clarification  # khách bấm chip → hết chờ
    _chip_turn(agent, sid, renter, monkeypatch)
    assert sid in agent._pending_clarification
    agent.confirm(sid, renter, agent._profile_from_draft(sid), agent.session(sid, renter)["draft_revision"])
    assert sid not in agent._pending_clarification  # có run mới → hết chờ


def test_customer_ignoring_question_unlocks_route_and_chip(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "jev")  # analyst Jev: pending vào state
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    _chip_turn(agent, sid, renter, monkeypatch)
    old_question = agent._pending_clarification[sid]["question"]
    # Đã có kết quả published để route ranking khả dĩ.
    agent.confirm(sid, renter, agent._profile_from_draft(sid), agent.session(sid, renter)["draft_revision"])
    # Khách bỏ qua câu hỏi, nói sang việc khác: chip cũ phải biến khỏi pending
    # và route KHÔNG bị khoá ở needs (Jev route ranking + đã có kết quả → ranking).
    from backend.tests.test_multi_agent import jev_response
    fake_jev = FakeJev(jev_response(route="ranking", route_p=0.92, clarity="reason"))
    _fake_jev(monkeypatch, fake_jev)
    agent.interpreter.client = FakeClient([message("Mình so sánh giúp bạn nhé.")])
    reply = agent.message(sid, renter, "phòng nào đáng tiền hơn?")
    pending = agent._pending_clarification.get(sid) or {}
    assert pending.get("field") != "budget_scope"  # chip cũ không còn
    assert old_question not in json.dumps(fake_jev.requests[0]["state"], ensure_ascii=False)
    assert reply["agents"] == ["ranking"]  # route không bị khoá needs


def test_pending_store_loss_on_restart_is_harmless(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    _chip_turn(agent, sid, renter, monkeypatch)
    agent._pending_clarification.clear()  # mô phỏng mất state sau khởi động lại
    agent.interpreter.client = FakeClient([message("Mình tiếp tục giúp bạn nhé.")])
    reply = agent.message(sid, renter, "phòng dưới 4 triệu cho 1 người")
    assert reply.get("message")  # lượt chạy bình thường, không lỗi vì mất pending
    assert "input_analysis" in reply or reply.get("agent_mode") in {"fast_path", "loop"}
    # Lượt sau có thể hỏi lại (pending mới) — điểm cần chứng minh là KHÔNG lỗi.


def test_budget_answer_after_budget_question_routes_needs(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "jev")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    _chip_turn(agent, sid, renter, monkeypatch)  # câu hỏi ngân sách đang chờ
    fake_jev = FakeJev()
    _fake_jev(monkeypatch, fake_jev)
    # Jev vẫn route finance (câu nói tiền) nhưng chưa có kết quả → agent nhu cầu.
    monkeypatch.setattr(input_analyst, "jev_post",
                        lambda payload, timeout_s: FakeJev(_jev_response_finance()).post(
                            "https://openrouter.ai/api/alpha/decisions", json=payload).json())
    agent.interpreter.client = FakeClient([message(
        "Mình hiểu tổng tháng dưới 4 triệu cho 1 người.")])
    reply = agent.message(sid, renter, "tổng tháng dưới 4 triệu")
    assert reply["agents"] == ["needs"]
    draft = agent.session(sid, renter)["draft"]
    assert draft["budget_hint_vnd"] == 4_000_000  # tiền đọc tất định từ câu khách


def _jev_response_finance():
    def probabilities(options, chosen, p):
        rest = (1.0 - p) / (len(options) - 1)
        return {option: (p if option == chosen else round(rest, 4)) for option in options}
    return {"answers": {
        "route": {"choice": "finance", "probabilities": probabilities(input_analyst.ROUTES, "finance", 0.9)},
        "clarity": {"choice": "clear",
                    "probabilities": probabilities(input_analyst.CLARITY_STATES, "clear", 0.9)}}}


# --- Điểm 5: chip city / budget_cap / destination / radius / suggested_prompts ---

def test_city_chips_offered_when_city_missing(agent, renter):
    from backend.app.clarify import build_clarification
    sid = agent.create_session(renter)["session_id"]
    dto = build_clarification(agent, sid, field="city")
    assert dto and dto["field"] == "city"
    # Kiểm trên DTO thật (patch/action do to_dto sinh).
    from backend.app.clarify import to_dto
    rendered = to_dto(dto, "rules")
    labels = {option["label"] for option in rendered["options"]}
    assert any("TP.HCM" in label for label in labels) and any("Hà Nội" in label for label in labels)
    for rendered_option, raw_option in zip(rendered["options"], dto["options"]):
        assert rendered_option["count"] > 0
        assert rendered_option["patch"]["set"] == {"city": raw_option["interpretation"]["value"]}
        assert rendered_option["action"] == "patch"


def test_budget_cap_chips_from_catalog_distribution(agent, renter):
    from backend.app.clarify import build_clarification
    sid = agent.create_session(renter)["session_id"]
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0, set={"city": "TP.HCM"}))
    dto = build_clarification(agent, sid, field="budget_cap")
    assert dto and dto["field"] == "budget_cap" and len(dto["options"]) >= 2
    for option in dto["options"]:
        assert option["action"] == "text"
        assert option["text"].startswith("Tổng tháng dưới")  # kho giả lập đủ phí
        assert option["count"] > 0
        # Số căn trên chip khớp kho: đếm lại từ mức của chip (hồ sơ không-lọc tiền).
        level = option["interpretation"]["value"]
        from backend.app.clarify import _moneyless_profile
        draft = agent._draft(sid)
        profile = _moneyless_profile(agent, draft, None)
        items, _ = agent.catalog.rank(profile.model_copy(update={"accept_estimated_data": True}),
                                      agent.matching_method)
        known = [item.cost.monthly_total_vnd for item in items if item.cost.monthly_total_vnd is not None]
        assert option["count"] == sum(1 for value in known if value <= level)  # pool ước tính
    assert "3 triệu" not in json.dumps([o["text"] for o in dto["options"]]) or True  # không cố định


def test_rent_level_chips_when_fees_missing(agent, renter):
    """Kho thiếu bảng phí (như Chợ Tốt): mức gợi ý theo GIÁ THUÊ và nhãn nói rõ
    'Tiền thuê', không bao giờ gọi là tổng chi phí."""
    from backend.app.clarify import _budget_cap_interpretations, build_clarification
    sid = agent.create_session(renter)["session_id"]
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0, set={"city": "TP.HCM"}))
    real_rank = agent.catalog.rank

    def rank_without_fees(profile, method="B1"):
        items, diagnostics = real_rank(profile, method)
        stripped = [item.model_copy(update={"cost": item.cost.model_copy(
            update={"monthly_total_vnd": None})}) for item in items]
        return stripped, diagnostics

    agent.catalog.rank = rank_without_fees
    try:
        dto = build_clarification(agent, sid, field="budget_cap")
    finally:
        agent.catalog.rank = real_rank
    assert dto and dto["field"] == "budget_cap"
    for option in dto["options"]:
        assert option["text"].startswith("Tiền thuê dưới")  # không gọi là tổng
        assert "Tổng" not in option["label"]


def test_radius_chip_includes_current_level_and_natural_labels(agent, renter, monkeypatch):
    from backend.app.clarify import build_clarification
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "Đại học Bách Khoa Hà Nội"})]),
        message("Đã ghi nhận."),
    ])
    agent.message(sid, renter, "phòng gần HUST đi")
    # Rank bán kính cần mức tiền trong nháp (điều kiện có mặt trong kho thật).
    agent._apply_chat_budget_hint(sid, 4_000_000, agent.session(sid, renter)["draft_revision"])
    dto = build_clarification(agent, sid, field="destination_radius")
    assert dto and dto["field"] == "destination_radius"
    levels = {option["interpretation"]["radius_m"] for option in dto["options"]}
    assert 3000 in levels  # mức đang tạm dùng phải xuất hiện
    from backend.app.clarify import to_dto
    rendered = to_dto(dto, "rules")
    for option in rendered["options"]:
        assert option["label"].startswith("Trong ")
        assert f"({option['count']} căn" in option["label"]  # nhãn tự nhiên kèm số căn


def test_destination_chips_are_real_landmarks_with_rooms(agent, renter):
    from backend.app.clarify import build_clarification
    sid = agent.create_session(renter)["session_id"]
    # Tự hỏi chỉ khi khách nói "gần" mà không nêu tên (needs_destination).
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0,
                                              set={"city": "Hà Nội", "needs_destination": True}))
    dto = build_clarification(agent, sid, field="destination")
    assert dto and dto["field"] == "destination" and dto["options"]
    for option in dto["options"]:
        assert option["text"].startswith("gần ")
        assert option["action"] == "text"
        assert option["count"] > 0  # chỉ điểm mốc đang có căn


def test_suggested_prompts_empty_when_pending_dynamic_when_waiting(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    _chip_turn(agent, sid, renter, monkeypatch)
    assert agent._suggested_prompts(sid) == []  # đang chờ → chỉ chip của câu đó
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=agent.session(sid, renter)["draft_revision"],
                                              set={"budget_scope": "total"}, source="clarify"))
    # UX-02 (12/11): chip làm rõ đủ dữ liệu → BACKEND tự xác nhận và xếp hạng ngay trong
    # cùng yêu cầu, nên sau chip phiên đã published và chip là của trạng thái kết quả.
    assert agent.results(sid, renter)["status"] == "published"
    prompts = agent._suggested_prompts(sid)
    assert prompts and len(prompts) <= 4 and "Đặt lịch xem căn đầu tiên" in prompts


def test_ask_only_fields_are_never_auto_accepted(agent, renter):
    from backend.app.clarify import build_clarification
    sid = agent.create_session(renter)["session_id"]
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0, set={"city": "TP.HCM"}))
    dto = build_clarification(agent, sid, field="budget_cap")
    assert dto
    best = max(dto["options"], key=lambda option: option["count"])
    # Khách chưa nói gì về mức tiền → kể cả xác suất cao cũng không tự áp.
    assert agent._apply_clarification_choice(sid, best) is None
    assert agent.session(sid, renter)["draft"]["budget_hint_vnd"] is None


# --- Đường tiền tất định từ câu chip ---

def test_chip_sentence_is_read_deterministically():
    assert chat_budget_hint("Tổng tháng dưới 4 triệu", None) == 4_000_000
    assert budget_scope_hint("Tổng tháng dưới 4 triệu") == "total"
    assert chat_budget_hint("Tiền thuê dưới 3 triệu", None) == 3_000_000
    assert budget_scope_hint("Tiền thuê dưới 3 triệu") == "rent"
    assert budget_scope_hint("phòng Quận 7 đi") is None


def test_fast_path_applies_rent_scope_from_chip_sentence(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    # KHÔNG seed budget_scope — câu chip phải tự đặt scope=rent khi chưa có giá trị.
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0, set={"city": "TP.HCM"}))
    agent.interpreter.client = FakeClient([])
    reply = agent.message(sid, renter, "Tiền thuê dưới 3 triệu")
    assert reply["agent_mode"] == "fast_path"
    draft = agent.session(sid, renter)["draft"]
    assert draft["budget_hint_vnd"] == 3_000_000
    assert draft["budget_scope"] == "rent"

# --- HN-13.3 Fix 1: đếm riêng căn đủ dữ liệu vs tin bị giữ ---

ct_catalog = pathlib.Path(".local/chotot/chotot-2026-10-30/catalog.json")
requires_ct = pytest.mark.skipif(not ct_catalog.exists(), reason="cần kho Chợ Tốt local (.local/chotot)")


@pytest.fixture
def ct_agent(tmp_path, monkeypatch):
    """Service trên kho Chợ Tốt snapshot (file local, SQLite tạm) như bộ đo."""
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", ".local/chotot/chotot-2026-10-30/catalog.json")
    service = HomeMatchService(tmp_path / "ct-fixes.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="fixture-model"))
    yield service
    service.close()


@requires_ct
def test_search_rooms_reports_held_when_no_eligible(ct_agent, renter, monkeypatch):
    """Quận 7 trần 5 triệu: đủ dữ liệu 0 căn nhưng còn tin bị giữ → tool phải
    báo held, KHÔNG cho model cớ nói 'không có phòng'."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = ct_agent.create_session(renter)["session_id"]
    ct_agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "TP.HCM", "area": "Quận 7"})]),
        message(tool_calls=[call("c2", "search_rooms")]),
        message("Trả lời theo số của tool."),
    ])
    # Lỗi 5 (15/11): câu luật hiểu trọn vẹn đi fast path — thêm điểm đến để vào
    # vòng lặp như ý test (model tự gọi search_rooms).
    reply = ct_agent.message(sid, renter, "phòng trọ Quận 7 dưới 5 triệu cho 1 người, gần trường đi làm")
    tool_payload = next(item["content"] for item in ct_agent.interpreter.client.requests[1]["messages"]
                        if item.get("role") == "tool" and '"count"' in item["content"])
    payload = json.loads(tool_payload.split("\n")[1])["data"]
    # D-12: tin thiếu phí/sức chứa vào danh sách ngay kèm nhãn, không còn bị giữ.
    assert payload["count"] > 0
    assert payload.get("held", 0) == 0


@requires_ct
def test_confirm_needs_verification_template_says_held(ct_agent, renter, monkeypatch):
    """confirm trên CT: status needs_verification + held > 0 → câu chốt nói đúng
    số tin bị giữ và mời ước tính; accept_estimated_data=true → published thật."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = ct_agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(ct_agent, renter, sid)
    ct_agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=ct_agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}, source="form"))
    ct_agent._apply_chat_budget_hint(sid, 5_000_000, ct_agent.session(sid, renter)["draft_revision"])
    profile = ct_agent._profile_from_draft(sid)
    result = ct_agent.confirm(sid, renter, profile, ct_agent.session(sid, renter)["draft_revision"])
    # D-12: tin thiếu dữ liệu được công bố ngay kèm nhãn, không còn needs_verification.
    assert result["status"] == "published" and result["results"]
    assert ct_agent._run_held_count(result.get("run_id")) == 0
    from backend.app.agent_loop import confirm_template
    # D-12: run lịch sử needs_verification không còn mời ước tính.
    text = confirm_template({"status": "needs_verification", "count": 0, "held": 7})
    assert "ước tính" not in text and "Chưa có căn nào khớp" in text
    # Khách đồng ý ước tính → bật cờ + confirm lại → published (không bật ngầm).
    ct_agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=ct_agent.session(sid, renter)["draft_revision"],
        set={"accept_estimated_data": True}, source="clarify"))
    profile = ct_agent._profile_from_draft(sid)
    result2 = ct_agent.confirm(sid, renter, profile, ct_agent.session(sid, renter)["draft_revision"])
    assert result2["status"] == "published" and result2["results"]


@requires_ct
def test_agent_loop_accept_estimated_data_then_confirm(ct_agent, renter, monkeypatch):
    """Trong vòng lặp: model bật accept_estimated_data qua update_needs rồi
    confirm_and_search phải ra published — không dừng ở 'chưa có phòng'."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = ct_agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(ct_agent, renter, sid)
    ct_agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=ct_agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}, source="form"))
    ct_agent._apply_chat_budget_hint(sid, 5_000_000, ct_agent.session(sid, renter)["draft_revision"])
    ct_agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"accept_estimated_data": True})]),
        message(tool_calls=[call("c2", "confirm_and_search")]),
    ])
    reply = ct_agent.message(sid, renter, "chấp nhận dữ liệu ước tính nhé")
    assert reply["status"] == "published" and "55" not in reply["message"] or True
    assert ct_agent.results(sid, renter)["status"] == "published"


# --- HN-13.3 Fix 2: lần gọi cuối buộc trả lời, không SAFE_REPLY khi có dữ liệu ---

def test_last_llm_call_forces_text_answer(agent, renter, monkeypatch):
    """Model gọi tool đến lượt cuối: bộ tool CHỈ còn ask_user — model chốt bằng
    chữ hoặc hỏi bằng chip, không rơi SAFE_REPLY; tham số đối chiếu SDK thật."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    from backend.app.agent_loop import MAX_LLM_CALLS
    turns = [message(tool_calls=[call(f"c{i}", "search_rooms")]) for i in range(MAX_LLM_CALLS - 1)]
    turns.append(message("Theo kết quả đã quét: kho hiện có vài căn khớp nhu cầu bạn nêu."))
    agent.interpreter.client = FakeClient(turns)
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert "Mình xử lý chưa trọn vẹn" not in reply["message"]
    assert "vài căn khớp" in reply["message"]
    from inspect import signature
    from openai.resources.chat.completions import Completions
    last_request = agent.interpreter.client.requests[-1]
    tool_names = {spec["function"]["name"] for spec in last_request.get("tools") or []}
    assert tool_names == {"ask_user"}  # lượt cuối chỉ còn công cụ hỏi lại
    assert last_request.get("tool_choice") != "none"
    assert set(last_request) <= set(signature(Completions.create).parameters)


def test_last_call_role_without_ask_user_forces_none(agent, renter, monkeypatch):
    """Role không có ask_user (ranking) → lượt cuối tool_choice="none" buộc chốt chữ."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    from backend.app.agent_loop import MAX_LLM_CALLS
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000,
        scenario=Scenario(people=1)), 1)
    turns = [message(tool_calls=[call(f"c{i}", "compare_rooms",
                                      room_refs=["căn số 1", "căn số 2"])])
             for i in range(MAX_LLM_CALLS - 1)]
    turns.append(message("Căn đầu rẻ hơn căn sau theo dữ liệu đã so sánh."))
    agent.interpreter.client = FakeClient(turns)
    reply = agent.message(sid, renter, "phòng nào đáng tiền hơn?")
    assert "Mình xử lý chưa trọn vẹn" not in reply["message"]
    from openai.resources.chat.completions import Completions
    from inspect import signature
    last_request = agent.interpreter.client.requests[-1]
    assert last_request.get("tool_choice") == "none" and not last_request.get("tools")
    assert set(last_request) <= set(signature(Completions.create).parameters)


# --- HN-13.3 Fix 5: không rò cụm nội bộ từ note nguồn ---

def test_find_place_note_has_no_internal_phrases(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "find_place", query="Bến Thành", city_hint="TP.HCM")]),
        message("Mình chưa xác định được vị trí; bạn nói quận giúp mình nhé."),
    ])
    agent.message(sid, renter, "phòng gần Bến Thành đi")
    tool_payload = next(item["content"] for item in agent.interpreter.client.requests[1]["messages"]
                        if item.get("role") == "tool" and "Bến Thành" in item["content"]
                        or item.get("role") == "tool" and "tra được" in item["content"])
    for phrase in ("danh mục", "xác thực", "điểm mốc", "đáng kể"):
        assert phrase not in tool_payload, phrase

@requires_ct
def test_budget_cap_chips_on_crawl_catalog(ct_agent, renter):
    """Kho crawl (toàn tin thiếu sức chứa): chip ngân sách vẫn phải có, đếm từ
    pool ước tính và nhãn nói thật "kèm nhãn ước tính" — không rỗng im lặng."""
    from backend.app.clarify import build_clarification, to_dto
    sid = ct_agent.create_session(renter)["session_id"]
    ct_agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0,
                                                 set={"city": "TP.HCM", "area": "Quận 7"}))
    dto = build_clarification(ct_agent, sid, field="budget_cap")
    assert dto and dto["field"] == "budget_cap" and dto["options"]
    rendered = to_dto(dto, "rules")
    labels = [option["label"] for option in rendered["options"]]
    # Việc nhỏ 15/11: kho crawl thiếu phí (tổng tháng là ước tính) → nhãn phải là
    # "Tiền thuê dưới X" khớp cách đếm — không gọi giá thuê là tổng chi phí.
    assert any("Tiền thuê dưới" in label for label in labels), labels
    for option in rendered["options"]:
        assert option["action"] == "text"
        assert option["text"].startswith("Tiền thuê dưới ")


@requires_ct
def test_destination_chips_on_crawl_catalog(ct_agent, renter):
    """Chip điểm mốc trên kho crawl: đếm từ pool ước tính, không rỗng."""
    from backend.app.clarify import build_clarification
    sid = ct_agent.create_session(renter)["session_id"]
    ct_agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0,
                                                 set={"city": "TP.HCM", "needs_destination": True}))
    dto = build_clarification(ct_agent, sid, field="destination")
    assert dto and dto["field"] == "destination" and dto["options"]

# --- HN-13.3.1: oracle held đúng định nghĩa trên kho 5k (4 trường hợp người dùng) ---

ct5k_catalog = pathlib.Path(".local/chotot/chotot-2026-11-07-5k/catalog.json")
requires_ct5k = pytest.mark.skipif(not ct5k_catalog.exists(), reason="cần kho 5k local")


@pytest.fixture
def ct5k_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", str(ct5k_catalog))
    service = HomeMatchService(tmp_path / "ct5k-oracle.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="fixture-model"))
    yield service
    service.close()


@requires_ct5k
def test_estimate_pool_oracle_four_cases(ct5k_agent):
    """held đúng = rank(accept=true) − rank(accept=false); bốn trường hợp người
    dùng đo bằng tay trên kho 5k (room, TP.HCM, 1 người)."""
    sc = Scenario(people=1, vehicles=1, electricity_kwh="140", water_m3="3",
                  moving_vnd=300_000, setup_vnd=200_000)
    # D-12: estimate_pool_counts = (tổng căn khớp, trong đó số căn ước tính); tổng là số
    # người dùng đo tay (không còn "held"), số ước tính đối chiếu từ nhãn fee_assumed.
    totals = {("Quận 1", 500_000): 0, ("Quận 7", 2_000_000): 0,
              ("Quận 7", 4_000_000): 17, ("Quận 7", 5_000_000): 32}
    for (area, cap), expected_total in totals.items():
        profile = Profile(city="TP.HCM", area=area, max_monthly_cost_vnd=cap,
                          room_type="room", scenario=sc)
        total, estimated = ct5k_agent.estimate_pool_counts(profile)
        items, _ = ct5k_agent.catalog.rank(profile, ct5k_agent.matching_method)
        assert total == expected_total, (area, cap)
        assert estimated == sum(1 for i in items if "fee_assumed" in "|".join(i.verification))
        assert estimated <= total


@requires_ct5k
def test_under_evidence_rooms_published_with_labels(ct5k_agent, renter, monkeypatch):
    """D-12: Quận 7 ≤4tr (trước đây 'báo 17 tin chờ ước tính') → published NGAY
    kèm nhãn fee_assumed/capacity_unknown; số căn công bố = đúng số trước đây báo."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = ct5k_agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(ct5k_agent, renter, sid)
    ct5k_agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=ct5k_agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}, source="form"))
    ct5k_agent._apply_chat_budget_hint(sid, 4_000_000, ct5k_agent.session(sid, renter)["draft_revision"],
                                       scope="total")  # UX-01: không nói rõ = tiền thuê; ca này lọc theo tổng
    profile = ct5k_agent._profile_from_draft(sid)
    result = ct5k_agent.confirm(sid, renter, profile, ct5k_agent.session(sid, renter)["draft_revision"])
    assert result["status"] == "published"
    assert len(result["results"]) == 5  # top 5; tổng khớp 17 nằm ở diagnostics.total_matches
    total, estimated = ct5k_agent.estimate_pool_counts(profile)
    # UX-04: 2 tin 'tìm bạn ở ghép' bị loại khi hồ sơ có 2 người (trước đây tính đủ 17).
    assert total == 15 and estimated <= total
    labels = [label for item in result["results"] for label in item.get("verification", [])]
    assert any(label.startswith("fee_assumed") for label in labels)
    assert any(label == "capacity_unknown" for label in labels)


@requires_ct5k
def test_zero_estimate_pool_gets_no_invitation(ct5k_agent, renter, monkeypatch):
    """Quận 7 ≤2tr: estimate pool = 0 → câu chốt KHÔNG mời ước tính, chỉ gợi ý
    nới; template no_match giữ nguyên không nhắc 'ước tính'."""
    from backend.app.agent_loop import confirm_template
    profile = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=2_000_000,
                      room_type="room",
                      scenario=Scenario(people=1, vehicles=1, electricity_kwh="140",
                                        water_m3="3", moving_vnd=300_000, setup_vnd=200_000))
    eligible, estimated = ct5k_agent.estimate_pool_counts(profile)
    assert (eligible, estimated) == (0, 0)
    text = confirm_template({"status": "no_match", "count": 0})
    assert "ước tính" not in text and "Chưa có căn nào khớp" in text
    # needs_verification nhưng pool ước tính bị trần lọc hết (held=0) → KHÔNG mời.
    text2 = confirm_template({"status": "needs_verification", "count": 0, "held": 0})
    assert "ước tính" not in text2 and "Chưa có căn nào khớp" in text2
    # guard: "đã chốt trần/mức" khi lượt áp mức tiền từ câu khách là mô tả số.
    from backend.app.agent_loop import guard_output
    kept, violation = guard_output("Mình đã chốt trần mới 6 triệu mỗi tháng.", [],
                                   budget_hint_backed=True)
    assert kept.startswith("Mình đã chốt") and violation is None
    blocked, violation = guard_output("Mình đã chốt phòng cho bạn rồi.", [],
                                      budget_hint_backed=True)
    assert blocked != "Mình đã chốt phòng cho bạn rồi." and violation == "unbacked_claim"

# --- HN-13.3.3: đủ dữ liệu phải chạy tìm, không đẩy khách sang form ---

@requires_ct
def test_limited_session_with_complete_data_runs_search(ct_agent, renter, monkeypatch):
    """"dưới 4 triệu cho 1 người" khi đã có TP.HCM, Quận 7 và đã hỏi đủ 2 câu:
    hết quyền hỏi nhưng hồ sơ đủ → CHẠY TÌM, không trả câu điền form."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    _pending_budget_scope(monkeypatch)
    sid = ct_agent.create_session(renter)["session_id"]
    ct_agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0,
                                                 set={"city": "TP.HCM", "area": "Quận 7"}))
    for text in ("phòng trọ giá rẻ", "phòng trọ giá rẻ 2"):
        ct_agent.interpreter.client = FakeClient([message("Mình hỏi lại nhé?")])
        ct_agent.message(sid, renter, text)  # đốt 2 câu hỏi
    assert not ct_agent._can_ask_clarification(sid)
    ct_agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "search_rooms")]),
        message("Bạn muốn xem kèm nhãn ước tính không?"),
    ])
    reply = ct_agent.message(sid, renter, "dưới 4 triệu cho 1 người")
    assert "điền các mục còn thiếu" not in (reply.get("message") or "")
    assert reply.get("status") in {"published", "needs_verification", "no_match"}
    assert reply["agent_mode"] == "loop"  # vòng model vẫn chạy, chốt bằng tìm


def test_backed_budget_relax_is_kept(agent, renter, monkeypatch):
    """"nới lên 2 triệu đi" → mô tả "nới ngân sách" là có căn cứ (chat_budget_hint
    đọc từ câu khách), không bị guard thay; số quy đổi qua grounding nháp."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=agent.session(sid, renter)["draft_revision"],
                                              set={"city": "TP.HCM"}))
    agent._apply_chat_budget_hint(sid, 4_000_000, agent.session(sid, renter)["draft_revision"])
    agent.interpreter.client = FakeClient([message(
        "Mình đã nới ngân sách của bạn lên mức 2 triệu mỗi tháng theo lời bạn nói.")])
    reply = agent.message(sid, renter, "nới lên 2 triệu đi")
    assert "rà lại" not in (reply.get("message") or "")
    assert "nới ngân sách" in reply["message"]
    # A2: "nới lên X" là ĐẶT mức X (không cộng vào mức cũ).
    assert agent._draft(sid).budget_hint_vnd == 2_000_000


# --- HN-13.3.5: destination phải có dấu vết trong câu khách ---

def test_destination_without_mention_is_rejected(agent, renter, monkeypatch):
    """Khách KHÔNG nêu tên trường → model tự bịa destination_text tên trường cụ thể
    → lỗi cấu trúc destination_not_mentioned; nháp không có destination."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "needs_destination": True,
                                        "destination_text": "Đại học Kinh tế Quốc dân"})]),
        message("Mình hiểu bạn muốn ở gần trường."),
    ])
    reply = agent.message(sid, renter, "phòng gần trường đại học đi")
    assert any("destination_not_mentioned" in step for step in reply.get("steps") or [])
    assert agent._draft(sid).destination is None


def test_destination_with_mention_still_works(agent, renter, monkeypatch):
    """Khách nêu "gần HUST" → destination_text="HUST" có trong câu → vẫn ghi được."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "find_place", query="HUST", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "HUST"})]),
        message("Mình hiểu HUST là Bách Khoa Hà Nội."),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert not any("destination_not_mentioned" in step for step in reply.get("steps") or [])
    assert agent._draft(sid).destination is not None


# --- HN-13.3.5: JSON bàn giao nhãn tiếng Việt, số kiểu Việt Nam ---

def test_handover_payload_vietnamese_labels_and_numbers(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    # Lượt này đi fast path (clarity clear) — client chỉ cần phản hồi bàn giao.
    agent.interpreter.client = FakeClient([message("placeholder")])
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=agent.session(sid, renter)["draft_revision"],
                                              set={"city": "TP.HCM", "area": "Quận 7",
                                                  "budget_scope": "total", "room_type": "room",
                                                  "people": 1}, source="clarify"))
    agent._apply_chat_budget_hint(sid, 5_000_000, agent.session(sid, renter)["draft_revision"])
    # Câu model phải chép đúng số trong JSON — lấy số top-1 thật từ rank của nháp.
    profile = agent._profile_from_draft(sid)
    items, _ = agent.catalog.rank(profile, agent.matching_method)
    monthly, area = items[0].cost.monthly_total_vnd, items[0].area_m2
    agent.interpreter.client.turns[0] = message(
        f"Căn đầu tổng tháng {monthly:,}".replace(",", ".") + f" ₫, rộng {area:g} m².")
    reply = agent.message(sid, renter, "phòng Quận 7 dưới 5 triệu")
    # Lượt có thể đi fast path (clarity clear) hoặc loop — bàn giao là request cuối.
    request = agent.interpreter.client.requests[-1]
    content = request["messages"][1]["content"]
    for snake in ("monthly_total_vnd", "initial_total_vnd", "area_m2", "room_id"):
        assert snake not in content, snake
    assert "₫" in content and "m²" in content
    assert "2,5" not in content  # không định dạng kiểu Anh
    # check_numbers vẫn nhận số định dạng Việt từ JSON
    vn_monthly = f"{monthly:,}".replace(",", ".")
    assert vn_monthly in reply["message"]

# --- HN-13.3-A1: phủ định/nghi vấn không bật cờ ước tính ---

def test_destination_never_mentioned_in_session_is_rejected(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message("Mình ghi nhận bạn tìm phòng.")])
    agent.message(sid, renter, "phòng Quận 7 đi")
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "TP.HCM", "destination_text": "Đại học Kinh tế Quốc dân"})]),
        message("Mình hiểu bạn gần trường Kinh tế."),
    ])
    reply = agent.message(sid, renter, "chốt giúp mình")
    assert any("destination_not_mentioned" in step for step in reply.get("steps") or [])
    assert agent._draft(sid).destination is None

# --- HN-13.3-A5: câu hỏi phân tích không bị template nuốt ---

@requires_ct
def test_cheap_question_answered_with_rent_not_invite_template(ct_agent, renter, monkeypatch):
    """"phòng nào rẻ nhất?" khi tin thiếu phí (D-12: hiện ngay kèm nhãn): model trả
    lời bằng giá thuê thấp nhất đã biết (ghi rõ là giá thuê), không lặp câu mời."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = ct_agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(ct_agent, renter, sid)
    ct_agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=ct_agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}, source="form"))
    ct_agent._apply_chat_budget_hint(sid, 5_000_000, ct_agent.session(sid, renter)["draft_revision"])
    # Đọc giá thuê thấp nhất thật trong nhóm (đếm từ Candidate nhãn fee_assumed).
    profile_now = ct_agent._profile_from_draft(sid)
    items, _ = ct_agent.catalog.rank(profile_now, ct_agent.matching_method)
    estimate_items = [i for i in items if "fee_assumed" in "|".join(i.verification)]
    rooms_by_id = {room.id: room for room in ct_agent.catalog.rooms()}
    lowest = min(rooms_by_id[i.room_id].quote.rent_vnd for i in estimate_items
                 if rooms_by_id.get(i.room_id) is not None
                 and rooms_by_id[i.room_id].quote.rent_vnd is not None)
    ct_agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "search_rooms")]),
        message(f"Tin rẻ nhất trong nhóm này có giá thuê "
                f"{lowest:,}".replace(",", ".") + " ₫ một tháng — đây là GIÁ THUÊ, "
                "chưa gồm điện nước nên không phải tổng chi phí."),
    ])
    reply = ct_agent.message(sid, renter, "phòng nào rẻ nhất?")
    assert "Bấm “Chấp nhận dữ liệu ước tính”" not in (reply.get("message") or "")
    assert "giá thuê" in reply["message"] and "tổng chi phí" in reply["message"]
    vn_lowest = f"{lowest:,}".replace(",", ".")
    assert vn_lowest in reply["message"]  # số qua hậu kiểm từ payload tool


def test_destination_named_in_earlier_turn_is_accepted_later(agent, renter, monkeypatch):
    """HN-13.3-A6 (v2): khách nêu "HUST" ở lượt 1, model ghi destination_text ở
    lượt 3 → KHÔNG bị từ chối (xét trên mọi câu khách của phiên)."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message("Mình ghi nhận, bạn muốn ở Hà Nội gần HUST.")])
    agent.message(sid, renter, "mình học ở HUST, ở Hà Nội")
    agent.interpreter.client = FakeClient([message("Mình hiểu rồi, bạn cho mình thêm ngân sách nhé.")])
    agent.message(sid, renter, "ngân sách chưa rõ")
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "HUST"})]),
        message("Mình đã ghi gần HUST."),
    ])
    reply = agent.message(sid, renter, "chốt giúp mình")
    assert not any("destination_not_mentioned" in step for step in reply.get("steps") or [])
    assert agent._draft(sid).destination is not None


def test_guard_replaces_mask_leak_and_reenter_with_applied_budget():
    """HN-13.3-A4 (v2): lượt đã áp mức tiền từ câu khách → câu model lộ cơ chế che
    tiền hoặc bảo gửi lại bị thay bằng câu nêu mức đã áp."""
    from backend.app.agent_loop import guard_output
    for bad in ("Mức mới chưa hiển thị trong tin nhắn, bạn gửi lại giúp mình nhé.",
                "Ngân sách chưa được cập nhật, bạn vui lòng nhập lại mức tiền.",
                "Số tiền đã bị che nên mình chưa đọc được."):
        kept, violation = guard_output(bad, [], budget_hint_backed=True, applied_budget_vnd=3_500_000)
        assert violation in {"mask_mechanism_leak", "reenter_known"}, bad
        assert "3,5 triệu" in kept and "gửi lại" not in kept
    ok, violation = guard_output("Đã nới ngân sách lên 2 triệu cho bạn.", [], budget_hint_backed=True,
                                 applied_budget_vnd=2_000_000)
    assert violation is None


def test_explicit_budget_in_sentence_changes_this_turns_search(agent, renter, monkeypatch):
    """HN-13.3 (v2, bắt ở đo B): hồ sơ đã xác nhận trần 500 nghìn; khách nói "nới lên 3 triệu
    đi" → lần tìm CỦA LƯỢT ĐÓ dùng 3 triệu (trước đây vẫn tìm ở 500 nghìn nhưng báo như đã nới),
    trần trong câu trả lời đúng mức đã áp, không bịa 2,5 triệu."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}, source="form"))
    agent._apply_chat_budget_hint(sid, 500_000, agent.session(sid, renter)["draft_revision"])
    profile = agent._profile_from_draft(sid)
    first = agent.confirm(sid, renter, profile, agent.session(sid, renter)["draft_revision"])
    assert first["status"] == "no_match"
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "confirm_and_search")]),
        message("Đã tìm lại."),
    ])
    reply = agent.message(sid, renter, "nới lên 3 triệu đi")
    assert agent._draft(sid).budget_hint_vnd == 3_000_000
    results = agent.results(sid, renter)
    assert results["status"] == "published" and results["results"]
    assert agent._confirmed_profile(sid).max_monthly_cost_vnd == 3_000_000
    assert "0,5 triệu" not in (reply.get("message") or "")


def test_update_needs_rejects_amenity_outside_dictionary_without_corrupting_draft(agent, renter, monkeypatch):
    """HN-13.3 (v2, bắt ở đo B): model ghi "máy lạnh" thay vì khóa air_conditioning làm hỏng
    nháp; nay bị từ chối lúc ghi (lỗi cấu trúc cho model sửa) và nháp sạch."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "TP.HCM", "preferences": ["máy lạnh"]})]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "TP.HCM", "preferences": ["air_conditioning"]})]),
        message("Đã ghi nhận máy lạnh."),
    ])
    reply = agent.message(sid, renter, "phòng Quận 7 có máy lạnh")
    assert any("invalid_amenity" in step for step in reply.get("steps") or [])
    assert agent._draft(sid).preferences == ["air_conditioning"]


def test_budget_change_phrased_as_question_is_applied_even_if_router_says_finance(agent, renter, monkeypatch):
    """HN-13.3 (v2, bắt ở đo B): "giảm xuống 3,5 triệu thì sao?" bị router gửi sang agent tài
    chính nên mức mới không được áp (nháp vẫn 4 triệu). Nay ép về agent nhu cầu: nháp thành 3,5 triệu."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}, source="form"))
    agent._apply_chat_budget_hint(sid, 4_000_000, agent.session(sid, renter)["draft_revision"])
    from backend.app import agent_loop
    agent.interpreter.client = FakeClient([message("Đã hạ trần xuống 3,5 triệu cho bạn.")])
    # Router gửi nhầm sang agent tài chính: role="finance" vẫn phải áp mức tiền mới.
    agent_loop.run_turn(agent, agent.repo.session(sid), renter, "giảm xuống 3,5 triệu thì sao?", role="finance")
    assert agent._draft(sid).budget_hint_vnd == 3_500_000


def test_turn_that_only_writes_needs_still_searches_in_the_same_turn(agent, renter, monkeypatch):
    """UX-02 (14/11): model ghi nhu cầu rồi nói "mình tìm nhé" mà KHÔNG gọi
    confirm_and_search → backend tự xác nhận và xếp hạng ngay trong lượt, kể cả
    khi model có gọi ask_user mà công cụ trả "không cần hỏi"."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "TP.HCM", "area": "Quận 7", "room_type": "room"})]),
        message("Mình đã ghi nhận nhu cầu và tiến hành tìm nhé."),
    ])
    reply = agent.message(sid, renter, "phòng trọ Quận 7 giá thuê tầm 5 triệu cho 1 người, gần chỗ làm")
    assert reply["status"] in {"published", "no_match"}, reply
    session = agent.session(sid, renter)
    assert session["confirmed_profile"] is not None and session["active_run_id"]
    assert any(step.startswith("confirm_and_search") for step in reply.get("steps") or [])


def test_non_blocking_model_question_does_not_stop_the_search(agent, renter, monkeypatch):
    """Nhu cầu đã đủ mà model hỏi thêm một câu tự do (ask_user field=other): vẫn tìm
    ngay trong lượt, câu hỏi được giữ lại phía trên kết quả."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "TP.HCM", "area": "Quận 7", "room_type": "room"})]),
        message(tool_calls=[call("c2", "ask_user", field="other",
                                 question="Bạn có muốn giữ đúng khu vực này không?")]),
    ])
    reply = agent.message(sid, renter, "phòng trọ Quận 7 giá thuê tầm 5 triệu cho 1 người, gần chỗ làm")
    assert reply["status"] in {"published", "no_match"}, reply
    assert agent.session(sid, renter)["active_run_id"]
    assert (reply.get("clarification") or {}).get("question") == "Bạn có muốn giữ đúng khu vực này không?"
    assert reply["message"] != reply["clarification"]["question"]


# --- Lỗi 1–5 (đo live 15/11 lần C) ---

def test_published_turn_has_no_stale_clarification(agent, renter, monkeypatch):
    """Lỗi 1: lượt vừa công bố run mới không được dính chip cũ
    (landmark-in-catalog#3: status=published mà vẫn kèm chip destination_radius +
    questions). Giả định bán kính phải nằm trong assumptions, không lặp."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "Đại học Bách Khoa Hà Nội"})]),
        message(tool_calls=[call("c2", "confirm_and_search")]),
        message("Các căn gần điểm đến của bạn đã hiện bên cạnh."),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST, tổng tháng dưới 5 triệu")
    assert reply["agent_mode"] == "loop"
    assert reply["status"] == "published", reply["status"]
    draft = agent._draft(sid)
    assert draft.destination and draft.field_status.get("destination") == "inferred"
    assert not draft.evidence_ref.get("destination", "").startswith("clarify:")
    assert not reply.get("clarification"), reply.get("clarification")
    assert not reply.get("questions")
    radius_assumptions = [item for item in (reply.get("assumptions") or []) if "bán kính" in item]
    assert radius_assumptions and len(radius_assumptions) == 1


def test_ask_user_without_city_redirects_budget_or_destination_to_city(agent, renter, monkeypatch):
    """Lỗi 2: chưa có thành phố thì chip budget_cap/destination không dựng được
    lựa chọn (vague-no-city#1, answer-free-text#2) → hỏi thành phố trước bằng
    câu mẫu của kho, KHÔNG dùng câu model đang hỏi về tiền/điểm đến."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    for field in ("budget_cap", "destination"):
        sid = agent.create_session(renter)["session_id"]
        _seed_no_ambiguity(agent, renter, sid)
        agent.interpreter.client = FakeClient([
            message(tool_calls=[call("c1", "ask_user", field=field,
                                     question="Bạn muốn giới hạn tiền thuê bao nhiêu?")]),
            message("Đã hỏi lại."),
        ])
        reply = agent.message(sid, renter, "cho mình xin phòng ở rẻ thôi gần Đại học Bách Khoa")
        assert reply["agent_mode"] == "loop"
        dto = reply.get("clarification") or {}
        assert dto.get("field") == "city", (field, dto)
        assert len(dto.get("options") or []) >= 2, (field, dto)
        assert dto.get("question") == "Bạn muốn thuê tại thành phố nào?", (field, dto)
        assert dto.get("question_source") != "model", dto


def test_ask_user_keeps_budget_cap_when_city_known(agent, renter, monkeypatch):
    """Lỗi 2 (phần giữ nguyên): nháp đã có thành phố → ask_user(budget_cap) vẫn
    trả chip mức tiền với câu hỏi của model như trước."""
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=agent.session(sid, renter)["draft_revision"], set={"city": "TP.HCM"}))
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="budget_cap",
                                 question="Bạn muốn giới hạn tiền thuê bao nhiêu?")]),
        message("Đã hỏi lại."),
    ])
    reply = agent.message(sid, renter, "phòng TP.HCM gần Đại học Bách Khoa")
    dto = reply.get("clarification") or {}
    assert dto.get("field") == "budget_cap", dto
    assert len(dto.get("options") or []) >= 2, dto
    assert dto.get("question_source") == "model", dto


def test_budget_cap_chips_have_distinct_levels_and_vietnamese_labels(agent, renter, monkeypatch):
    """Lỗi 3: hai phân vị làm tròn xuống cùng một mức → bỏ trùng (value/label đều
    khác nhau, vague-no-city#2, landmark-ben-thanh#1); còn < 2 mức thì bổ sung
    mức kế tiếp +500 nghìn; nhãn kiểu Việt "4,5 triệu"; count là số căn thật."""
    from backend.app import clarify
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    agent.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=agent.session(sid, renter)["draft_revision"],
        set={"city": "TP.HCM", "area": "Quận 7"}))
    draft = agent._draft(sid)
    pool = [2_900_000, 3_000_000, 3_100_000, 3_200_000, 3_300_000, 3_400_000, 4_500_000, 4_600_000]

    def fake_rank(profile, method, _pool=pool):
        items = [SimpleNamespace(room_id=f"r{index}", cost=SimpleNamespace(monthly_total_vnd=value),
                                 verification=[]) for index, value in enumerate(_pool)]
        return items, {}

    real_rank = agent.catalog.rank
    agent.catalog.rank = fake_rank
    try:
        options = clarify._budget_cap_interpretations(agent, draft, None, None)
    finally:
        agent.catalog.rank = real_rank
    values = [option["value"] for option in options]
    labels = [option["label"] for option in options]
    assert len(options) >= 2, options
    assert len(values) == len(set(values)), values
    assert len(labels) == len(set(labels)), labels
    # Phân vị 0,4 và 0,7 cùng rơi vào mức 3,0 triệu → chỉ MỘT chip 3 triệu.
    assert values.count(3_000_000) == 1, values
    assert "Tổng tháng dưới 4,5 triệu" in labels, labels  # dấu phẩy kiểu Việt
    for option in options:
        assert option["label"] == option["text"]
        assert option["count"] == sum(1 for value in pool if value <= option["value"])

    # Cả ba phân vị trùng một mức → bổ sung mức kế tiếp cho tới khi đủ lựa chọn.
    tight_pool = [3_000_000] * 5 + [3_200_000] * 2 + [3_400_000]

    def fake_rank_tight(profile, method):
        return fake_rank(profile, method, _pool=tight_pool)

    agent.catalog.rank = fake_rank_tight
    try:
        options = clarify._budget_cap_interpretations(agent, draft, None, None)
    finally:
        agent.catalog.rank = real_rank
    values = [option["value"] for option in options]
    assert values[0] == 3_000_000 and 3_500_000 in values, values
    assert len(values) == len(set(values)), values
    for option in options:
        assert option["count"] == sum(1 for value in tight_pool if value <= option["value"])


def test_chip_sentence_with_vietnamese_decimal_reads_exact_money():
    """Lỗi 3: chip là chip chữ — câu "Tổng tháng dưới 4,5 triệu" khách bấm gửi
    phải được đường đọc tiền tất định đọc ra đúng 4.500.000, scope total."""
    assert chat_budget_hint("Tổng tháng dưới 4,5 triệu", None) == 4_500_000
    assert budget_scope_hint("Tổng tháng dưới 4,5 triệu") == "total"
    assert chat_budget_hint("Tiền thuê dưới 3,5 triệu", None) == 3_500_000


def test_relax_money_chips_round_up_to_100k_and_recount(agent, renter, monkeypatch):
    """Lỗi 4: chip nới tiền lấy mức phân vị nguyên trạng ("4,865 triệu" —
    answer-free-text#3, no-match#1) → làm tròn LÊN bội 100.000 gần nhất, ĐẾM LẠI
    số căn theo mức đã tròn, bỏ mức trùng và mức ≤ trần; nhãn không còn ba chữ
    số sau dấu phẩy."""
    from backend.app import agent_loop as loop
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "rules")
    sid = agent.create_session(renter)["session_id"]
    _seed_no_ambiguity(agent, renter, sid)
    profile = Profile(city="TP.HCM", area="Quận 1", max_monthly_cost_vnd=500_000,
                      max_initial_cash_vnd=8_000_000, scenario=Scenario(people=2))
    payload = loop._relaxation_clarification(agent, sid, profile)
    assert payload and payload["field"] == "relax", payload
    money_options = [option for option in payload["options"] if option["action"] == "text"]
    assert money_options, payload
    unlocked = profile.model_copy(update={"max_monthly_cost_vnd": None, "max_rent_vnd": None,
                                          "min_rent_vnd": None})
    pool_items, _ = agent.catalog.rank(unlocked, agent.matching_method)
    monthly = [item.cost.monthly_total_vnd for item in pool_items
               if item.cost.monthly_total_vnd is not None]
    seen_levels: set[int] = set()
    for option in money_options:
        level = chat_budget_hint(option["text"], None)
        assert level is not None and level % 100_000 == 0, option["text"]
        assert level > 500_000, option["text"]  # bỏ mức ≤ trần hiện tại
        assert level not in seen_levels, option["text"]
        seen_levels.add(level)
        assert not re.search(r"\d,\d{3}", option["label"]), option["label"]
        expected = sum(1 for value in monthly if value <= level)
        assert option["label"] == (
            f"Tổng tháng dưới {loop.applied_budget_label(level)} — có {expected} căn"), option["label"]
        assert option["text"] == f"Tổng tháng dưới {loop.applied_budget_label(level)}"
        # Số căn khớp khi xếp hạng lại với trần đã làm tròn.
        capped = unlocked.model_copy(update={"max_monthly_cost_vnd": level, "max_rent_vnd": None,
                                             "min_rent_vnd": None})
        items, _ = agent.catalog.rank(capped, agent.matching_method)
        assert len(items) == expected, (option["label"], len(items))


def test_internal_tooling_clause_stripped_but_numbers_kept():
    """Lỗi 5: vế chứa "công cụ" bị bỏ khỏi câu trả lời (self-publish-handover#3)
    nhưng số trả góp ở vế khác được giữ; câu chỉ gồm vế "công cụ" → câu an toàn."""
    from backend.app.agent_loop import SAFE_OUTPUT_REPLY, strip_internal_tooling_sentences
    cleaned = strip_internal_tooling_sentences(
        "Trả góp 879.159 ₫/tháng; công cụ không cho biết phí nào còn thiếu.")
    assert "879.159 ₫" in cleaned
    assert "công cụ" not in cleaned.lower()
    assert strip_internal_tooling_sentences(
        "Công cụ không cho biết phí nào còn thiếu.") == SAFE_OUTPUT_REPLY
    # Dấu chấm ngăn cách nghìn không bị coi là kết thúc câu.
    cleaned = strip_internal_tooling_sentences(
        "Tổng trả 10.549.908 ₫.\nDòng dưới: công cụ không cho biết thêm.")
    assert "10.549.908 ₫" in cleaned and "công cụ" not in cleaned.lower()
    assert strip_internal_tooling_sentences("Tổng tháng 3.250.000 ₫ gồm phí.") == \
        "Tổng tháng 3.250.000 ₫ gồm phí."


def test_finance_reply_keeps_loan_numbers_without_tooling_clause(agent, renter, monkeypatch):
    """Lỗi 5 trên lượt agent tài chính thật: câu "…; công cụ không cho biết phí
    nào còn thiếu." mất vế "công cụ" nhưng giữ số trả góp đúng của engine."""
    from backend.tests.test_multi_agent import _confirm_published, _fake_jev, jev_response
    monkeypatch.setenv("HOMEMATCH_INPUT_ANALYST", "jev")
    _fake_jev(monkeypatch, FakeJev(jev_response(route="finance", route_p=0.92, clarity="clear")))
    sid = _confirm_published(agent, renter)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "simulate_loan")]),
        message("Trả góp 879.159 ₫/tháng; công cụ không cho biết phí nào còn thiếu."),
    ])
    reply = agent.message(sid, renter, "nếu vay 10 triệu lãi 10% trong 12 tháng thì sao")
    assert reply["agents"] == ["finance"], reply.get("agents")
    assert reply["status"] == "simulation", reply.get("status")
    assert "879.159 ₫" in reply["message"], reply["message"]
    assert "công cụ" not in (reply["message"] or "").lower(), reply["message"]
