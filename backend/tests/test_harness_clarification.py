"""HN-02: model chỉ chọn trường, kho/Jev tạo chip; không mạng."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app import clarify, decisions
from backend.app.agent_executor import execute_tool
from backend.app.agent_loop import build_tools
from backend.app.agents import ToolBox
from backend.app.catalog import Catalog
from backend.app.interpreter import OpenAIInterpreter
from backend.app.locations import resolve_place
from backend.app.models import Destination, DomainError, DraftPatch, Profile, Scenario
from backend.app.service import HomeMatchService


def tool(name, **args):
    return SimpleNamespace(id=name, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class ModelClient:
    def __init__(self, messages):
        self.messages = list(messages)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=self.messages.pop(0))],
                               usage=SimpleNamespace(total_tokens=7))


@pytest.fixture
def agent(tmp_path):
    service = HomeMatchService(tmp_path / "clarify.sqlite", catalog=Catalog(
        Path(__file__).resolve().parents[2] / "data/catalog/rooms.json"),
        interpreter=OpenAIInterpreter(client=ModelClient([]), model="fixture"))
    yield service
    service.close()


def prepare(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    place = resolve_place("Phú Mỹ Hưng", "TP.HCM")
    agent._apply_agent_patch(sid, {"city": "TP.HCM", "destination": Destination(
        label=place["label"], latitude=place["latitude"], longitude=place["longitude"],
        uncertainty_m=place["uncertainty_m"], max_distance_m=3000)})
    agent._apply_chat_budget_hint(sid, 6_000_000, agent.repo.session(sid)["draft_revision"])
    return sid


def force_ask(monkeypatch):
    monkeypatch.setattr(decisions, "decide", lambda clarification, *args, **kwargs:
        ("ask", clarification["options"][0], "jev", None))


def test_ask_user_uses_catalog_chips_and_stops_following_writes(agent, renter, monkeypatch):
    force_ask(monkeypatch)
    sid = prepare(agent, renter)
    agent.interpreter.client = ModelClient([SimpleNamespace(content=None, tool_calls=[
        tool("ask_user", field="destination_radius"),
        tool("update_needs", patch={"city": "Hà Nội"}),
        tool("ask_user", field="people")])])
    reply = agent.message(sid, renter, "gần điểm đến", turn_id="ask")
    dto = reply["clarification"]
    assert dto["field"] == "destination_radius" and dto["decided_by"] == "jev"
    assert all({"count", "patch", "decided_by"} <= set(option) for option in dto["options"])
    assert reply["questions"] == [dto["question"]]
    assert len(reply["steps"]) == 1 and reply["draft"]["city"] == "TP.HCM"
    assert agent.repo.session(sid)["clarification_questions"] == 1
    assert agent.message(sid, renter, "gần điểm đến", turn_id="ask") == reply


def test_confirm_requires_clarification_before_creating_run(agent, renter, monkeypatch):
    calls = []
    def decide(clarification, *args, **kwargs):
        calls.append(clarification["field"])
        return "ask", clarification["options"][0], "jev", None
    monkeypatch.setattr(decisions, "decide", decide)
    sid = prepare(agent, renter)
    box = ToolBox(max_steps=6)
    handlers = build_tools(agent, agent.repo.session(sid), renter, "", box)
    result = execute_tool(agent, box, sid, "turn", "confirm_and_search",
                          handlers["confirm_and_search"]["fn"], {}, actor=renter)
    assert result["ok"] is False and result["error"] == "needs_clarification"
    assert result["field"] == "destination_radius" and "ask_user" in result["hint"]
    assert agent.repo.db.execute("SELECT COUNT(*) AS c FROM hm_runs").fetchone()["c"] == 0
    question = execute_tool(agent, box, sid, "turn", "ask_user", handlers["ask_user"]["fn"],
                            {"field": "destination_radius"}, actor=renter)
    assert question["data"]["question"]
    assert calls == ["destination_radius"]


def test_jev_high_probability_applies_without_question(agent, renter, monkeypatch):
    original = decisions.decide
    def post(url, json):
        ids = list(json["questions"]["clarify"]["criteria"])
        probabilities = {key: (0.9 if index == 0 else 0.1 / (len(ids) - 1)) for index, key in enumerate(ids)}
        return SimpleNamespace(status_code=200, json=lambda: {"answers": {"clarify": {
            "choice": ids[0], "probabilities": probabilities}}})
    fake = SimpleNamespace(post=post)
    monkeypatch.setattr(decisions, "decide", lambda clarification, context, **kwargs:
                        original(clarification, context, client=fake, mode="jev"))
    sid = prepare(agent, renter)
    agent.interpreter.client = ModelClient([
        SimpleNamespace(content=None, tool_calls=[tool("ask_user", field="destination_radius")]),
        SimpleNamespace(content="Mình đã ghi nhận nhu cầu.", tool_calls=None)])
    reply = agent.message(sid, renter, "gần điểm đến")
    assert not reply.get("questions")
    assert reply["draft"]["evidence_ref"]["destination"].startswith("clarify:auto")
    assert "Mình đang hiểu" in reply["message"]
    assert agent.repo.session(sid)["clarification_questions"] == 0


def test_auto_choice_never_expands_a_confirmed_radius(agent, renter):
    sid = prepare(agent, renter)
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=agent.repo.session(sid)["draft_revision"],
        set={"destination_radius_m": 2000}, source="clarify"))
    destination = agent._draft(sid).destination.model_copy(update={"max_distance_m": 2000})
    agent.confirm(sid, renter, Profile(city="TP.HCM", destination=destination,
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000, scenario=Scenario()),
        agent.repo.session(sid)["draft_revision"])
    assert agent._apply_clarification_choice(sid, {"label": "5 km", "interpretation": {
        "field": "destination_radius", "radius_m": 5000}}) is None
    assert agent._profile_from_draft(sid).destination.max_distance_m == 2000


def test_same_place_update_preserves_confirmed_radius_and_evidence(agent, renter):
    sid = prepare(agent, renter)
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=agent.repo.session(sid)["draft_revision"],
        set={"destination_radius_m": 2000}, source="clarify"))
    before = agent.session(sid, renter)
    box = ToolBox()
    handlers = build_tools(agent, agent.repo.session(sid), renter, "Phú Mỹ Hưng", box)
    result = execute_tool(agent, box, sid, "same", "update_needs", handlers["update_needs"]["fn"],
                          {"patch": {"destination_text": "Phú Mỹ Hưng"}}, actor=renter)
    assert result["ok"]
    after = agent.session(sid, renter)
    assert after["draft"]["destination"] == before["draft"]["destination"]
    assert after["draft"]["evidence_ref"]["destination"] == before["draft"]["evidence_ref"]["destination"]
    assert after["draft"]["field_status"]["destination"] == "confirmed"
    assert after["draft_revision"] == before["draft_revision"]


def test_only_two_questions_before_first_results_survive_restart(agent, renter, monkeypatch):
    force_ask(monkeypatch)
    sid = prepare(agent, renter)
    for index in range(2):
        agent.interpreter.client = ModelClient([SimpleNamespace(content=None,
            tool_calls=[tool("ask_user", field="destination_radius")])])
        reply = agent.message(sid, renter, "gần điểm đến", turn_id=f"question-{index}")
        assert reply["clarification"]["question"]
    assert not agent._can_ask_clarification(sid)
    path, catalog = agent.repo.db.location, agent.catalog
    agent.close()
    restarted = HomeMatchService(path, catalog=catalog, interpreter=OpenAIInterpreter(
        client=ModelClient([SimpleNamespace(content=None, tool_calls=[tool("ask_user", field="destination_radius")]),
                           SimpleNamespace(content="Bạn điền biểu mẫu nhu cầu nhé.", tool_calls=None)]), model="fixture"))
    try:
        reply = restarted.message(sid, renter, "gần điểm đến", turn_id="third")
        # HN-13.3.3: hết 2 câu hỏi nhưng draft đã đủ tối thiểu (city + mức tiền)
        # → CHẠY TÌM trực tiếp (như auto-confirm của FE), không đẩy khách sang form.
        assert not reply.get("questions") and (
            "Đã xác nhận nhu cầu" in reply["message"] or "căn hợp nhất" in reply["message"]
            or "hợp nhu cầu" in reply["message"])  # D-12
        assert restarted.repo.session(sid)["clarification_questions"] == 2
    finally:
        restarted.close()


def test_other_question_cannot_launder_model_numbers(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    box = ToolBox()
    handlers = build_tools(agent, agent.repo.session(sid), renter, "tìm phòng", box)
    result = execute_tool(agent, box, sid, "other", "ask_user", handlers["ask_user"]["fn"],
        {"field": "other", "question": "Chọn gì?", "options": ["99 căn giá 1 triệu"]}, actor=renter)
    assert result["ok"] is False and result["error"] == "invalid_question"


def test_preflight_retains_auto_assumption_before_later_question(agent, renter, monkeypatch):
    def decide(clarification, *args, **kwargs):
        return ("accept" if clarification["field"] == "destination_radius" else "ask",
                clarification["options"][0], "jev", None)
    monkeypatch.setattr(decisions, "decide", decide)
    sid = prepare(agent, renter)
    agent.interpreter.client = ModelClient([
        SimpleNamespace(content=None, tool_calls=[tool("confirm_and_search")]),
        SimpleNamespace(content=None, tool_calls=[tool("ask_user", field="people")])])
    reply = agent.message(sid, renter, "gần điểm đến")
    assert reply["draft"]["destination"]["max_distance_m"] == 2000
    assert reply["draft"]["evidence_ref"]["destination"].startswith("clarify:auto")
    assert "2 km" in reply["message"] and reply["clarification"]["field"] == "people"
    assert agent.repo.db.execute("SELECT COUNT(*) AS c FROM hm_runs").fetchone()["c"] == 0


def test_questions_in_final_text_obey_turn_and_session_limits(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    for index in range(3):
        agent.interpreter.client = ModelClient([SimpleNamespace(
            content="Bạn muốn thành phố nào? Bạn ở mấy người? Bạn cần loại phòng nào?", tool_calls=None)])
        reply = agent.message(sid, renter, "tìm phòng", turn_id=f"free-{index}")
        if index < 2:
            assert reply["message"] == "Bạn muốn thành phố nào?"
        else:
            assert "?" not in reply["message"] and "Nhu cầu của tôi" in reply["message"]
    assert agent.repo.session(sid)["clarification_questions"] == 2


def test_model_question_without_ask_user_is_kept_without_guessing_chip(agent, renter, monkeypatch):
    """HN-13.2: model tự hỏi trong câu trả lời mà không qua ask_user → GIỮ câu của
    model, KHÔNG gắn chip kho đoán (chip có thể lệch câu hỏi); khách gõ tự do.
    Chỉ số question_without_chip được ghi vào trace để bộ đo tính tỉ lệ."""
    force_ask(monkeypatch)
    sid = prepare(agent, renter)
    agent.interpreter.client = ModelClient([SimpleNamespace(
        content="Bạn muốn loại phòng nào?", tool_calls=None)])
    reply = agent.message(sid, renter, "gần điểm đến")
    assert "loại phòng" in (reply.get("message") or "")  # câu model giữ nguyên
    assert not reply.get("clarification")  # không gắn chip đoán
    rows = agent.repo.db.execute(
        "SELECT s.summary FROM hm_agent_steps s JOIN hm_agent_turns t ON s.turn_row_id=t.id "
        "WHERE t.session_id=? AND s.name='question_without_chip'", (sid,)).fetchall()
    assert rows


def test_failed_write_restores_transient_assumptions(agent, renter):
    sid = prepare(agent, renter)
    box = ToolBox()
    build_tools(agent, agent.repo.session(sid), renter, "", box)
    def broken():
        agent._apply_clarification_choice(sid, {"label": "2 km", "interpretation": {
            "field": "destination_radius", "radius_m": 2000}})
        box.assumptions.append("Bán kính 2 km")
        box.question_asked = True
        raise DomainError("failed_write", "Không lưu được.")
    result = execute_tool(agent, box, sid, "failed", "confirm_and_search", broken, {}, actor=renter)
    assert not result["ok"]
    assert agent._draft(sid).destination.max_distance_m == 3000
    assert box.assumptions == [] and box.question_asked is False


def test_default_radius_is_disclosed_when_catalog_does_not_require_question(agent, renter, monkeypatch):
    sid = prepare(agent, renter)
    monkeypatch.setattr(clarify, "build_clarification", lambda *args, **kwargs: None)
    agent.interpreter.client = ModelClient([SimpleNamespace(content="Mình đã ghi nhận nhu cầu.", tool_calls=None)])
    reply = agent.message(sid, renter, "gần điểm đến")
    assert not reply.get("questions")
    assert "Tạm dùng bán kính 3 km" in reply["message"]
    assert reply["draft"]["destination"]["max_distance_m"] == 3000


@pytest.mark.parametrize("field, interpretation", [
    ("area", {"value": "Quận 1"}),
    ("room_type", {"value": "apartment"}),
    ("people", {"value": 1}),
    ("budget_scope", {"scope": "rent"}),
])
def test_auto_choices_cannot_relax_confirmed_profile(agent, renter, field, interpretation):
    sid = agent.create_session(renter)["session_id"]
    profile = Profile(city="TP.HCM", area="Quận 7", room_type="room", max_rent_vnd=4_000_000,
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000, scenario=Scenario(people=2))
    agent.confirm(sid, renter, profile, 0)
    agent._apply_chat_budget_hint(sid, 5_000_000, agent.repo.session(sid)["draft_revision"])
    before = agent.session(sid, renter)
    assert agent._apply_clarification_choice(sid, {"label": "Lựa chọn", "interpretation": {
        "field": field, **interpretation}}) is None
    assert agent.session(sid, renter) == before


def test_question_limit_is_lifted_after_first_published_results(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.repo.db.execute("UPDATE hm_sessions SET clarification_questions=2 WHERE id=?", (sid,))
    assert not agent._can_ask_clarification(sid)
    result = agent.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000, scenario=Scenario()), 0)
    assert result["status"] == "published"
    assert agent._can_ask_clarification(sid)
