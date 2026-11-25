"""HN-11: phân vai agent theo pha — interview/results/transaction lọc bộ tool."""
import json
from types import SimpleNamespace

import pytest

from backend.app.agent_loop import build_tools
from backend.app.agent_tools import phase_tools, tool_specs
from backend.app.agents import ToolBox
from backend.app.interpreter import OpenAIInterpreter
from backend.app.models import Actor, Profile, Scenario
from backend.app.service import HomeMatchService


def message(content="ok", tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))], usage=SimpleNamespace(total_tokens=7))


def call(id_, name, **arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name,
                                                            arguments=json.dumps(arguments, ensure_ascii=False)))


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.turns:
            raise AssertionError("hết kịch bản")
        return self.turns.pop(0)


@pytest.fixture
def agent(tmp_path):
    service = HomeMatchService(tmp_path / "phase.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="fixture"))
    yield service
    service.close()


def spec_names(phase):
    return {spec["function"]["name"] for spec in tool_specs(phase)}


def test_interview_phase_hides_transaction_and_result_tools(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    assert agent._agent_phase(sid) == "interview"
    specs = spec_names("interview")
    # Pha phỏng vấn không thấy tool kết quả/giao dịch (PLAN HN-11 test bắt buộc).
    for banned in ("room_details", "estimate_cost", "prepare_viewing", "open_landlord_chat"):
        assert banned not in specs
    handlers = build_tools(agent, agent.repo.session(sid), renter, "", ToolBox(max_steps=6), "interview")
    assert "prepare_viewing" not in handlers and "open_landlord_chat" not in handlers
    assert {"find_place", "update_needs", "search_rooms", "confirm_and_search", "ask_user"} <= set(handlers)


def test_results_phase_after_confirm_has_result_tools(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000,
        scenario=Scenario(people=2)), 0)
    assert agent._agent_phase(sid) == "results"
    specs = spec_names("results")
    assert {"room_details", "estimate_cost"} <= specs
    # 18/11: prepare_viewing không tạo bản ghi nên có từ pha results (trước đó chỉ ở
    # transaction — pha chỉ có khi đã có lịch xem, nên model không chuẩn bị được lịch
    # đầu tiên). open_landlord_chat tạo hội thoại nên vẫn chỉ ở transaction.
    assert "prepare_viewing" in specs
    assert "open_landlord_chat" not in specs


def test_transaction_phase_after_viewing_or_handover(agent, renter, landlord):
    sid = agent.create_session(renter)["session_id"]
    agent.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000,
        scenario=Scenario(people=2)), 0)
    room_id = agent.results(sid, renter)["results"][0]["room_id"]
    from datetime import datetime, timezone, timedelta
    agent.request_viewing(sid, renter, room_id,
                          datetime.now(timezone.utc) + timedelta(days=3), "key-phase-1")
    assert agent._agent_phase(sid) == "transaction"
    assert {"prepare_viewing", "open_landlord_chat"} <= spec_names("transaction")


def test_turn_sends_phase_filtered_specs_to_model(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message("Đã hiểu nhu cầu.")])
    agent.message(sid, renter, "phòng gần HUST đi")
    sent_names = {spec["function"]["name"] for spec in agent.interpreter.client.requests[0]["tools"]}
    assert "prepare_viewing" not in sent_names and "open_landlord_chat" not in sent_names
    assert "confirm_and_search" in sent_names


def test_phase_recorded_in_durable_trace(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message("Đã hiểu nhu cầu.")])
    agent.message(sid, renter, "phòng gần HUST đi")
    turn = agent.agent_trace(sid, renter)["chat"]
    assert turn["phase"] == "interview"


def test_model_calling_tool_outside_phase_gets_structured_error(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "prepare_viewing", room_ref="demo-01")]),
        message("Mình chưa chuẩn bị được lịch vì chưa có kết quả."),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["agent_mode"] == "loop"
    assert any("prepare_viewing" in step and "Lỗi" in step for step in reply["steps"])
