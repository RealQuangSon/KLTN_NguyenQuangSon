"""HN-07: đường lui và độ bền — retry, model dự phòng, circuit breaker.

Mọi provider là client giả; breaker test bằng cách monkeypatch đồng hồ."""
import json
from types import SimpleNamespace

import pytest

from backend.app import provider_breaker
from backend.app.interpreter import OpenAIInterpreter
from backend.app.service import HomeMatchService


def call(id_, name, **arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name,
                                                            arguments=json.dumps(arguments, ensure_ascii=False)))


def message(content="ok", tokens=7):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=None))], usage=SimpleNamespace(total_tokens=tokens))


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        self.models = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        self.models.append(kwargs.get("model"))
        if not self.turns:
            raise AssertionError("hết kịch bản phản hồi")
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


@pytest.fixture
def agent(tmp_path):
    service = HomeMatchService(tmp_path / "resilience.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="primary-model"))
    provider_breaker.reset()
    yield service
    service.close()


def test_transient_error_retries_once_then_succeeds(agent, renter):
    agent.interpreter.client = FakeClient([
        ConnectionError("gateway hiccup"),
        message("Đã hiểu nhu cầu của bạn."),
    ])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["agent_mode"] == "loop"
    assert len(agent.interpreter.client.requests) == 2  # đúng 1 lần thử lại
    assert any(step.startswith("retry:") for step in reply["steps"])


def test_non_transient_error_goes_straight_to_graph_fallback(agent, renter):
    agent.interpreter.client = FakeClient([ValueError("logic bug")])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["agent_mode"] == "graph_fallback"
    assert len(agent.interpreter.client.requests) == 1  # lỗi không tạm thời: không retry


def test_fallback_model_takes_over_after_primary_fails(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AGENT_FALLBACK_MODEL", "backup-model")
    agent.interpreter.client = FakeClient([
        ConnectionError("primary down"),
        ConnectionError("primary down again"),
        message("Trả lời từ model dự phòng."),
    ])
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["agent_mode"] == "loop"
    assert agent.interpreter.client.models == ["primary-model", "primary-model", "backup-model"]
    assert any(step.startswith("fallback_model:") for step in reply["steps"])


def test_all_levels_exhausted_falls_back_to_graph(agent, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AGENT_FALLBACK_MODEL", "backup-model")
    agent.interpreter.client = FakeClient([ConnectionError("down")] * 4)
    sid = agent.create_session(renter)["session_id"]
    reply = agent.message(sid, renter, "phòng gần HUST đi")
    assert reply["agent_mode"] == "graph_fallback"
    assert len(agent.interpreter.client.requests) == 4  # 2 model × 2 lần (retry)


def test_circuit_breaker_opens_after_five_consecutive_failures(agent, renter):
    key = "chat:primary-model"
    sid = agent.create_session(renter)["session_id"]
    calls = 0
    for index in range(4):
        agent.interpreter.client = FakeClient([ValueError("down")])
        reply = agent.message(sid, renter, f"phòng gần HUST đi {index}", turn_id=f"fail-{index}")
        assert reply["agent_mode"] == "graph_fallback"
        calls += 1
    assert not provider_breaker.open_(key)  # 4 lỗi: chưa mở
    # Lỗi thứ 5 liên tiếp → breaker mở.
    agent.interpreter.client = FakeClient([ValueError("down")])
    agent.message(sid, renter, "phòng gần HUST đi nữa", turn_id="fail-5")
    assert provider_breaker.open_(key)
    # Khi mở: provider bị bỏ qua hoàn toàn (không chạm client); bước guard
    # circuit_open nằm trong trace bền.
    calls_before = len(agent.interpreter.client.requests)
    reply = agent.message(sid, renter, "phòng gần HUST đi lần cuối", turn_id="after-open")
    assert reply["agent_mode"] == "graph_fallback"
    trace = agent.agent_trace(sid, renter)["chat"]
    assert any(step["name"] == "circuit_open" for step in trace["steps"])
    assert len(agent.interpreter.client.requests) == calls_before  # không chạm provider


def test_breaker_closes_after_open_window(monkeypatch):
    key = "chat:probe"
    provider_breaker.reset(key)
    clock = {"now": 1000.0}
    monkeypatch.setattr(provider_breaker, "_now", lambda: clock["now"])
    for _ in range(5):
        provider_breaker.record(key, False)
    assert provider_breaker.open_(key)
    clock["now"] += 119.0
    assert provider_breaker.open_(key)
    clock["now"] += 2.0  # quá 120 s
    assert not provider_breaker.open_(key)
    provider_breaker.reset(key)


def test_success_resets_failure_streak():
    key = "probe-reset"
    provider_breaker.reset(key)
    for _ in range(4):
        provider_breaker.record(key, False)
    assert not provider_breaker.open_(key)  # 4 lỗi: chưa mở
    provider_breaker.record(key, True)  # một lần thành công → chuỗi Reset
    for _ in range(4):
        provider_breaker.record(key, False)
    assert not provider_breaker.open_(key)
    provider_breaker.record(key, False)  # lỗi thứ 5 LIÊN TIẾP sau thành công → mở
    assert provider_breaker.open_(key)
    provider_breaker.reset(key)


def test_jev_breaker_skips_provider_and_uses_rules(renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_DECISION_MODE", "jev")
    key = "jev"
    provider_breaker.reset(key)
    for _ in range(5):
        provider_breaker.record(key, False)
    assert provider_breaker.open_(key)
    from backend.app import decisions
    import httpx
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kwargs:
                        (_ for _ in ()).throw(AssertionError("breaker mở phải bỏ qua provider")))
    clarification = {"field": "budget_scope", "options": [
        {"id": "opt-0", "label": "Tổng", "probability": 0.9, "patch": {"set": {"budget_scope": "total"}}},
        {"id": "opt-1", "label": "Thuê", "probability": 0.1, "patch": {"set": {"budget_scope": "rent"}}}]}
    decision, best, decided_by, error = decisions.decide(clarification, {}, mode="jev")
    assert (decision, decided_by, error) == ("accept", "fallback", "RuntimeError")
    provider_breaker.reset(key)
