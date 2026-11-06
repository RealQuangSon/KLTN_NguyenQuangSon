"""HN-05: trace bền — hm_agent_turns/hm_agent_steps, tổng hợp admin, quyền.

Không mạng: model là FakeClient kịch bản."""
import json
from types import SimpleNamespace

import pytest

from backend.app.interpreter import OpenAIInterpreter
from backend.app.models import Actor, DomainError
from backend.app.service import HomeMatchService


def message(content=None, tool_calls=None, tokens=7, prompt=5, completion=2, cost=0.0001):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))],
        usage=SimpleNamespace(total_tokens=tokens, prompt_tokens=prompt,
                              completion_tokens=completion, cost=cost))


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
            raise AssertionError("FakeClient hết kịch bản phản hồi")
        return self.turns.pop(0)


@pytest.fixture
def agent(tmp_path):
    service = HomeMatchService(tmp_path / "trace.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="fixture-model"))
    yield service
    service.close()


def turn_rows(service):
    return [dict(row) for row in service.repo.db.execute(
        "SELECT * FROM hm_agent_turns ORDER BY started_at")]


def step_rows(service):
    return [dict(row) for row in service.repo.db.execute(
        "SELECT * FROM hm_agent_steps ORDER BY turn_row_id,seq")]


def test_one_turn_row_and_n_step_rows_per_turn(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "search_rooms")]),
        message("Đã kiểm tra kho theo nhu cầu hiện tại."),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    rows = turn_rows(agent)
    assert len(rows) == 1  # mỗi lượt đúng một dòng turn
    turn = rows[0]
    assert turn["turn_id"] == reply["turn_id"] and turn["session_id"] == sid
    assert turn["agent_mode"] == "loop" and turn["model"] == "fixture-model"
    assert turn["llm_calls"] == 2  # 2 lần gọi LLM trong lượt
    assert turn["input_tokens"] == 10 and turn["output_tokens"] == 4  # 2 × (5,2)
    assert turn["outcome"] == "answered" and turn["error_code"] is None
    assert turn["cost_usd"] == pytest.approx(0.0002)
    steps = step_rows(agent)
    kinds = [step["kind"] for step in steps]
    assert kinds == ["llm", "tool", "llm"]  # gọi model → tool → gọi model chốt
    assert steps[1]["name"] == "search_rooms" and steps[1]["ok"] == 1
    assert all("[TIEN_DA_TACH]" not in step["summary"] for step in steps)


def test_fast_path_records_tool_and_decision_steps(agent, renter, monkeypatch):
    from backend.app import clarify
    monkeypatch.setattr(clarify, "build_clarification", lambda *args, **kwargs: None)
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([])
    agent.message(sid, renter, "phòng trọ Quận 7 TP.HCM dưới 4 triệu cho 2 người")
    rows = turn_rows(agent)
    assert len(rows) == 1 and rows[0]["agent_mode"] == "fast_path"
    assert rows[0]["llm_calls"] == 0 and rows[0]["outcome"] == "answered"
    steps = step_rows(agent)
    assert [step["kind"] for step in steps] == ["tool"]
    assert steps[0]["name"] == "confirm_and_search"


def test_decision_step_records_jev_or_rules(agent, renter, monkeypatch):
    from backend.app import clarify, decisions
    monkeypatch.setattr(decisions, "decide", lambda clarification, *args, **kwargs:
                        ("ask", clarification["options"][0], "jev", None))

    def fake_build(service_, session_id_, field=None):
        if field not in (None, "destination_radius"):
            return None
        return {"field": "destination_radius", "impact": 0.5, "options": [
            {"id": "opt-0", "field": "destination_radius", "kind": "radius",
             "label": "Gần điểm đến · bán kính 2 km",
             "interpretation": {"field": "destination_radius", "kind": "radius", "radius_m": 2000},
             "top": ["a", "b"], "count": 5, "min_monthly_total_vnd": 3_000_000, "probability": 0.5},
            {"id": "opt-1", "field": "destination_radius", "kind": "radius",
             "label": "Gần điểm đến · bán kính 5 km",
             "interpretation": {"field": "destination_radius", "kind": "radius", "radius_m": 5000},
             "top": ["c", "d"], "count": 5, "min_monthly_total_vnd": 3_000_000, "probability": 0.5}]}
    monkeypatch.setattr(clarify, "build_clarification", fake_build)
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "ask_user", field="destination_radius")]),
    ])
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply.get("clarification")
    steps = step_rows(agent)
    decision = [step for step in steps if step["kind"] == "decision"]
    assert decision and "decided_by=jev" in decision[0]["summary"]
    assert turn_rows(agent)[0]["decided_by"] == "jev"


def test_trace_has_no_income_contact_or_raw_money(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([
        message("Đã ghi nhận nhu cầu của bạn, xem trong khung nhu cầu nhé."),
    ])
    agent.message(sid, renter, "gọi 0901234567, email a@b.com, thu nhập 20 triệu, ngân sách 4 triệu")
    blob = json.dumps({"turns": turn_rows(agent), "steps": step_rows(agent)}, ensure_ascii=False)
    assert "0901234567" not in blob and "a@b.com" not in blob
    assert "monthly_income_vnd" not in blob and "20 triệu" not in blob


def test_turn_trace_survives_restart(renter, tmp_path):
    path = tmp_path / "trace-restart.sqlite"
    service = HomeMatchService(path, interpreter=OpenAIInterpreter(client=FakeClient([]), model="fixture"))
    try:
        sid = service.create_session(renter)["session_id"]
        service.interpreter.client = FakeClient([message("Đã hiểu nhu cầu.")])
        service.message(sid, renter, "phòng gần HUST đi")
    finally:
        service.close()
    restarted = HomeMatchService(path, interpreter=OpenAIInterpreter(client=FakeClient([]), model="fixture"))
    try:
        trace = restarted.agent_trace(sid, renter)["chat"]
        assert trace and trace["agent_mode"] == "loop"
        assert isinstance(trace["steps"], list)
    finally:
        restarted.close()


def test_admin_agent_turns_aggregates_and_audits(agent, renter, admin):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message("Đã hiểu nhu cầu.", cost=0.0002)])
    agent.message(sid, renter, "phòng gần HUST đi")
    report = agent.admin_agent_turns(admin)
    assert report["count"] == 1
    assert report["turns"][0]["session_id"] == sid
    assert report["p50_ms"] is not None and report["p95_ms"] is not None
    assert report["fallback_ratio"] == 0.0
    assert report["cost_usd"] == pytest.approx(0.0002)
    assert report["cost_usd_per_day"] == pytest.approx(0.0002)
    audits = agent.repo.db.execute(
        "SELECT action FROM hm_audit_log WHERE actor_id=? ORDER BY created_at DESC LIMIT 1",
        (admin.id,)).fetchone()
    assert audits["action"] == "agent_turns.viewed"


def test_renter_cannot_read_admin_turns(agent, renter):
    with pytest.raises(DomainError) as error:
        agent.admin_agent_turns(renter)
    assert error.value.code == "forbidden"


def test_trace_follows_chat_retention(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    agent.interpreter.client = FakeClient([message("Đã hiểu nhu cầu.")])
    agent.message(sid, renter, "phòng gần HUST đi")
    agent.repo.db.execute("UPDATE hm_agent_turns SET started_at='2000-01-01T00:00:00+00:00'")
    agent.purge_transcripts()
    assert turn_rows(agent) == [] and step_rows(agent) == []
