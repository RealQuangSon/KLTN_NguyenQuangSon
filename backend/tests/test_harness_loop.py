"""HN-01: giới hạn vòng lặp, tool chỉ đọc chạy song song, timeout, fast path.

Mọi model/provider đều là client giả kịch bản hóa; không gọi mạng. Đo thời gian
bằng tool giả có sleep để chứng minh chạy song song mà không đụng provider."""
import json
import time
from types import SimpleNamespace

import pytest
from pydantic import Field

from backend.app import agent_loop
from backend.app.agent_loop import (MAX_LLM_CALLS, SAFE_REPLY, chat_budget_hint,
                                    confirm_template)
from backend.app.agent_tools import TOOL_REGISTRY, ToolArgs, ToolDefinition
from backend.app.interpreter import OpenAIInterpreter
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
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.turns:
            raise AssertionError("FakeClient hết kịch bản phản hồi")
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


@pytest.fixture
def agent(tmp_path):
    service = HomeMatchService(tmp_path / "harness-loop.sqlite", interpreter=OpenAIInterpreter(
        client=SimpleNamespace(), model="fixture-model"))
    yield service
    service.close()


def _register_probe(monkeypatch, timeout_s: float) -> None:
    """Đăng ký tool giả sleep_probe theo đúng hợp đồng: registry + allowlist + roster."""
    from backend.app.agents import AGENT_TOOLS
    from backend.app.agent_tools import ROLE_ROSTER

    class ProbeArgs(ToolArgs):
        ms: int = Field(gt=0, le=5000)

    probe = ToolDefinition(
        name="sleep_probe", agent="needs", description="Chờ ms rồi trả kết quả (chỉ đọc).",
        Args=ProbeArgs, writes=False, timeout_s=timeout_s, view=None, capability="chat:message",
        sample_args={"ms": 1}, exposed=False, success_summary="Đã chờ xong.",
        handler=lambda service, session, actor, toolbox, ms: (time.sleep(ms / 1000), {"slept_ms": ms})[1])
    monkeypatch.setitem(TOOL_REGISTRY, "sleep_probe", probe)
    monkeypatch.setitem(AGENT_TOOLS, "needs", AGENT_TOOLS["needs"] | {"sleep_probe"})
    monkeypatch.setitem(ROLE_ROSTER, "needs",
                        {"system": ROLE_ROSTER["needs"]["system"],
                         "tools": ROLE_ROSTER["needs"]["tools"] + ("sleep_probe",)})


def test_read_only_tools_in_one_response_run_in_parallel(agent, renter, monkeypatch):
    _register_probe(monkeypatch, timeout_s=8.0)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "sleep_probe", ms=350), call("c2", "sleep_probe", ms=350)]),
        message(content="Đã kiểm tra xong."),
    ])
    sid = agent.create_session(renter)["session_id"]
    started = time.monotonic()
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    elapsed = time.monotonic() - started
    assert reply["agent_mode"] == "loop"
    # Handler thật sự chạy (không phải lỗi allowlist) và đủ hai bước.
    assert all("Đã chờ xong" in step for step in reply["steps"]), reply["steps"]
    # Chạy song song: hai tool 350 ms phải xong dưới 0,6 s (tuần tự là >= 0,7 s).
    assert elapsed < 0.6, elapsed


def test_write_tools_stay_sequential_in_model_order(agent, renter):
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "Hà Nội"}),
                            call("c2", "update_needs", patch={"area": "Quận Cầu Giấy"})]),
        message(content="Đã ghi nhu cầu."),
    ])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["agent_mode"] == "loop"
    draft = agent.session(sid, renter)["draft"]
    assert draft["city"] == "Hà Nội" and draft["area"] == "Quận Cầu Giấy"
    # Thứ tự model gọi: city ở r1 trước, area ở r2 sau.
    assert draft["evidence_ref"]["city"] == "agent:r1"
    assert draft["evidence_ref"]["area"] == "agent:r2"


def test_slow_tool_returns_structured_tool_timeout(agent, renter, monkeypatch):
    _register_probe(monkeypatch, timeout_s=0.05)
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "sleep_probe", ms=600)]),
        message(content="Bước chậm đã bỏ, mình trả lời trực tiếp."),
    ])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert any("tool_timeout" in step for step in reply["steps"])
    assert reply["message"] == "Bước chậm đã bỏ, mình trả lời trực tiếp."


def test_loop_stops_after_four_llm_calls(agent, renter):
    agent.interpreter.client = FakeClient(
        [message(tool_calls=[call(f"c{i}", "search_rooms")]) for i in range(8)])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["message"] == SAFE_REPLY
    assert len(agent.interpreter.client.requests) == MAX_LLM_CALLS
    assert len(reply["steps"]) == MAX_LLM_CALLS


def test_turn_deadline_stops_before_more_llm_calls(agent, renter, monkeypatch):
    monkeypatch.setattr(agent_loop, "TURN_DEADLINE_S", 0.0)
    client = FakeClient([message(content="không bao giờ được gọi")])
    agent.interpreter.client = client
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["message"] == SAFE_REPLY
    assert client.requests == []  # deadline chạm ngay khi vào lượt


def test_model_request_carries_harness_params(agent, renter):
    client = FakeClient([message(content="Đã hiểu nhu cầu.")])
    agent.interpreter.client = client
    sid = agent.create_session(renter)["session_id"]
    agent.message(sid, renter, "phòng gần HUST đi")
    params = client.requests[0]
    assert params["parallel_tool_calls"] is True
    assert params["reasoning_effort"] == "low"
    # FakeClient nhận mọi khóa; đối chiếu với SDK thật để không lọt tham số nó từ chối.
    from inspect import signature
    from openai.resources.chat.completions import Completions
    assert set(params) <= set(signature(Completions.create).parameters)
    assert params["max_completion_tokens"] == 800
    assert "temperature" not in params  # model reasoning không nhận temperature


def test_turn_ends_with_template_after_confirm_without_extra_llm_call(agent, renter):
    from backend.app.models import DraftPatch
    agent.interpreter.client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"city": "TP.HCM", "area": "Quận 7"})]),
        message(tool_calls=[call("c2", "confirm_and_search")]),
    ])
    sid = agent.create_session(renter)["session_id"]
    # HN-08: confirm phải hỏi các trường mơ hồ (scope/room_type/people — gold
    # CL15 và preflight HN-02) — seed sẵn để test này tập trung vào "gộp lượt cuối".
    agent.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0,
        set={"budget_scope": "total", "room_type": "room", "people": 2}, source="clarify"))
    reply = agent.message(sid, renter, "phòng dưới 5 triệu")
    assert reply["agent_mode"] == "loop"
    # needs_verification từ 07/11 nói đúng thực tế "Chưa công bố được căn nào"
    # (không còn "Đã có kết quả" mâu thuẫn) và nhắc đúng tên nút thật.
    assert reply["message"].startswith(("Đã xác nhận nhu cầu", "Có ", "Chưa có căn nào"))
    # D-12: không còn mẫu mời "chấp nhận dữ liệu ước tính".
    assert "needs_verification" not in agent_loop.CONFIRM_TEMPLATES
    assert len(agent.interpreter.client.requests) == 2  # không gọi LLM lần 3 chỉ để "nói lại"


def test_confirm_template_only_uses_tool_numbers():
    from backend.app.agent_loop import CONFIRM_TEMPLATES
    assert "12" in confirm_template({"status": "published", "count": 12})
    assert confirm_template({"status": "published", "count": 0}) == CONFIRM_TEMPLATES["published"].format(count=0)
    # D-12: không còn câu mời "chấp nhận dữ liệu ước tính"; nhiều hơn top 5 căn khớp
    # thì nói thật tổng số và rằng đây là các căn xếp đầu.
    more = confirm_template({"status": "published", "count": 5, "total_matches": 51})
    assert "51 căn khớp" in more and "5 căn hợp nhất" in more and "Chấp nhận" not in more
    assert confirm_template({"status": "published", "count": 5, "total_matches": 5}) == \
        CONFIRM_TEMPLATES["published"].format(count=5)
    # run lịch sử needs_verification đọc như không có căn, không mời ước tính.
    legacy = confirm_template({"status": "needs_verification", "count": 0, "held": 55})
    assert legacy == CONFIRM_TEMPLATES["no_match"].format(count=0) and "ước tính" not in legacy
    assert confirm_template({"status": "no_match", "count": 0, "held": 12}) == CONFIRM_TEMPLATES["no_match"]
    assert confirm_template({"status": "weird", "count": 0, "held": 0}) == CONFIRM_TEMPLATES["no_match"].format(count=0)


def test_chat_budget_hint_relative_wins_over_absolute():
    # AG-02: tương đối ưu tiên trước tuyệt đối trong cùng câu.
    assert chat_budget_hint("nới thêm 1 triệu, phòng dưới 4 triệu", 4_000_000) == 5_000_000
    assert chat_budget_hint("phòng dưới 4 triệu", None) == 4_000_000
    assert chat_budget_hint("giảm xuống 3,5 triệu", 4_000_000) == 3_500_000
    assert chat_budget_hint("tìm phòng đi", 4_000_000) is None


def _find_room_sentence() -> str:
    return "phòng trọ Quận 7 TP.HCM dưới 4 triệu cho 2 người, có máy lạnh"


def _no_ambiguity(monkeypatch):
    """Fast-path test không phụ thuộc dữ liệu kho: lớp hỏi lại được giả lập tường minh."""
    from backend.app import clarify
    monkeypatch.setattr(clarify, "build_clarification", lambda *args, **kwargs: None)


def _pending_budget_scope(monkeypatch):
    """Lớp hỏi lại trả một điểm mơ hồ chờ hỏi, hai cách hiểu 0,5/0,5 (luật sẽ hỏi)."""
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


def test_fast_path_confirms_without_any_llm_call(agent, renter, monkeypatch):
    _no_ambiguity(monkeypatch)
    client = FakeClient([])
    agent.interpreter.client = client
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, _find_room_sentence())
    assert reply["agent_mode"] == "fast_path"
    assert client.requests == []  # lượt không gọi model lần nào
    draft = agent.session(sid, renter)["draft"]
    assert draft["city"] == "TP.HCM" and draft["area"] == "Quận 7"
    assert draft["people"] == 2 and draft["budget_hint_vnd"] == 4_000_000
    assert draft["preferences"] == ["air_conditioning"]  # tiện ích ghi theo khóa, không văn bản thô
    assert agent.session(sid, renter)["active_run_id"]


def test_fast_path_skips_sentences_with_destination(agent, renter):
    client = FakeClient([message(content="Mình sẽ tìm gần HUST.")])
    agent.interpreter.client = client
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng dưới 4 triệu gần HUST")
    assert reply["agent_mode"] == "loop"  # cần find_place/kiểm chứng → vòng lặp LLM
    assert client.requests


def test_fast_path_returns_catalog_chip_when_ambiguous(agent, renter, monkeypatch):
    _pending_budget_scope(monkeypatch)
    client = FakeClient([])
    agent.interpreter.client = client
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, _find_room_sentence())
    assert reply["agent_mode"] == "fast_path"
    assert client.requests == []
    dto = reply["clarification"]
    assert dto and dto["question"]
    assert all({"count", "patch", "decided_by"} <= set(option) for option in dto["options"])
    assert dto["decided_by"] == "rules"  # hai cách hiểu 0,5/0,5 → luật chọn hỏi
    assert agent.repo.db.execute(
        "SELECT COUNT(*) AS c FROM hm_runs WHERE session_id=?", (sid,)).fetchone()["c"] == 0


def test_explicit_intent_runs_the_deterministic_graph_without_llm(agent, renter):
    from backend.app.interpreter import fixed_intent
    assert fixed_intent("nếu vay 12 tháng thì sao") == "simulate_finance"
    client = FakeClient([])
    agent.interpreter.client = client
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "nếu vay 12 tháng thì sao")
    assert reply["agent_mode"] == "fast_path"
    assert client.requests == []
    assert reply["intent"] == "simulate_finance"
    assert reply["usage"]["logical_calls"] == 0


def test_fast_path_reply_passes_the_http_response_schema(agent, monkeypatch):
    """POST /messages lọc qua MessageResult; stream thì không, nên lỗi này từng chỉ lộ khi stream đứt."""
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    _no_ambiguity(monkeypatch)
    agent.interpreter.client = FakeClient([])
    with TestClient(create_app(lambda: agent)) as client:
        headers = {"Authorization": "Bearer demo-renter-a"}
        sid = client.post("/sessions", headers=headers).json()["session_id"]
        response = client.post(f"/sessions/{sid}/messages", headers=headers, json={"text": _find_room_sentence()})
    assert response.status_code == 200
    assert response.json()["agent_mode"] == "fast_path"
    assert response.json()["status"] in ("published", "no_match", "needs_verification")


def test_fast_path_reply_states_the_real_result_count(agent, renter, monkeypatch):
    """Câu chốt lấy số căn từ kết quả thật; trước đây luôn đọc ra "0 căn" khi khung kết quả có căn."""
    _no_ambiguity(monkeypatch)
    agent.interpreter.client = FakeClient([])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng trọ Quận 7 TP.HCM dưới 5 triệu cho 1 người")
    results = agent.results(sid, renter)
    assert reply["agent_mode"] == "fast_path" and results["status"] == "published" and results["results"]
    # D-12: nhiều hơn 5 căn khớp → "N căn khớp, đây là 5 căn hợp nhất"; không thì "tìm được N căn".
    total = results.get("total_matches") or len(results["results"])
    assert (f"tìm được {len(results['results'])} căn" in reply["message"]
            or f"Có {total} căn khớp; đây là {len(results['results'])} căn hợp nhất" in reply["message"])
