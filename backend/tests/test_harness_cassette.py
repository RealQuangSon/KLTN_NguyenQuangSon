"""HN-09: cassette ghi/phát lại lượt live — record từ provider giả, replay không mạng."""
import json
from types import SimpleNamespace

import pytest

from backend.app import decisions
from backend.app.agent_loop import SAFE_REPLY
from backend.app.interpreter import OpenAIInterpreter
from backend.app.service import HomeMatchService


def call(id_, name, **arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name,
                                                            arguments=json.dumps(arguments, ensure_ascii=False)))


def message(content=None, tool_calls=None, tokens=7, prompt=5, completion=2, cost=0.0001):
    usage = SimpleNamespace(total_tokens=tokens, prompt_tokens=prompt,
                            completion_tokens=completion, cost=cost)
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
            raise AssertionError("provider bị gọi trong chế độ replay")
        return self.turns.pop(0)


class ExplodingClient:
    """Replay không được chạm provider."""

    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        raise AssertionError("replay phải dùng cassette, không gọi provider")


SENTENCE = "Tìm phòng trọ dưới 4 triệu gần HUST cho 1 người"


def scripted_client():
    return FakeClient([
        message(tool_calls=[call("c1", "find_place", query="HUST", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "Hà Nội", "destination_text": "HUST"})]),
        message(tool_calls=[call("c3", "confirm_and_search")]),
        message("Mình hiểu HUST ở Đại Cồ Việt, Hai Bà Trưng; kết quả đã hiện bên phải."),
    ])


def test_record_then_replay_reproduces_identical_turn(tmp_path, renter, monkeypatch):
    cassette = tmp_path / "cassette.json"
    monkeypatch.setenv("HOMEMATCH_AGENT_RECORD", str(cassette))
    service = HomeMatchService(tmp_path / "record.sqlite", interpreter=OpenAIInterpreter(
        client=scripted_client(), model="fixture-model"))
    sid = service.create_session(renter)["session_id"]
    first = service.message(sid, renter, SENTENCE)
    first_draft = service.session(sid, renter)["draft"]
    service.close()
    payload = json.loads(cassette.read_text(encoding="utf-8"))
    kinds = [entry["kind"] for entry in payload["entries"]]
    assert kinds == ["model", "model", "model"]  # HN-01: gộp lượt cuối, 3 lần gọi model
    # Request ghi lại là bản đã redact: không PII/thu nhập.
    blob = json.dumps(payload, ensure_ascii=False)
    assert "monthly_income_vnd" not in blob and "0901234567" not in blob

    # Replay trên service mới với provider nổ nếu bị chạm — không mạng.
    monkeypatch.setenv("HOMEMATCH_AGENT_RECORD", "")
    monkeypatch.setenv("HOMEMATCH_AGENT_REPLAY", str(cassette))
    replayed = HomeMatchService(tmp_path / "replay.sqlite", interpreter=OpenAIInterpreter(
        client=ExplodingClient(), model="fixture-model"))
    try:
        sid2 = replayed.create_session(renter)["session_id"]
        second = replayed.message(sid2, renter, SENTENCE)
        assert second["agent_mode"] == "loop"
        assert second["message"] == first["message"]
        assert second["steps"] == first["steps"]
        assert second["draft"] == first["draft"]
        assert second["view"] == first["view"]
        assert replayed.session(sid2, renter)["draft"] == first_draft
        # usage phát lại từ cassette (không ước lượng).
        assert second["usage"]["tokens"] == first["usage"]["tokens"] == 21  # 3 lần gọi × 7 token
    finally:
        replayed.close()


def test_replay_exhausted_cassette_falls_back_safely(tmp_path, renter, monkeypatch):
    cassette = tmp_path / "short.json"
    cassette.write_text(json.dumps({"kind": "agent_cassette", "version": 1, "entries": [
        {"kind": "model", "request": {}, "response": {
            "content": "Câu trả lời từ cassette.",
            "tool_calls": [],
            "usage": {"total_tokens": 5, "prompt_tokens": 3, "completion_tokens": 2, "cost": None}}},
    ]}), encoding="utf-8")
    monkeypatch.setenv("HOMEMATCH_AGENT_RECORD", "")
    monkeypatch.setenv("HOMEMATCH_AGENT_REPLAY", str(cassette))
    service = HomeMatchService(tmp_path / "short.sqlite", interpreter=OpenAIInterpreter(
        client=ExplodingClient(), model="fixture-model"))
    try:
        sid = service.create_session(renter)["session_id"]
        reply = service.message(sid, renter, SENTENCE)
        assert reply["message"] == "Câu trả lời từ cassette."
        # Lượt kế tiếp hết cassette → đường lui an toàn, không chết giữa chừng.
        reply2 = service.message(sid, renter, "câu tiếp theo", turn_id="second")
        assert reply2["agent_mode"] == "graph_fallback"
        assert reply2["questions"]
    finally:
        service.close()


def test_jev_record_and_replay_without_network(tmp_path, monkeypatch):
    cassette = tmp_path / "jev.json"
    # Ghi: Jev qua httpx giả (offline) trong chế độ record.
    monkeypatch.setenv("HOMEMATCH_AGENT_RECORD", str(cassette))
    monkeypatch.setenv("HOMEMATCH_DECISION_MODE", "jev")
    import httpx
    recorded = {}

    def fake_post(self, url, headers=None, json=None):
        recorded["payload"] = json
        return SimpleNamespace(status_code=200, json=lambda: {"answers": {"clarify": {
            "choice": "opt-0", "probabilities": {"opt-0": 0.9, "opt-1": 0.1}}}})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    clarification = {"field": "budget_scope", "options": [
        {"id": "opt-0", "label": "Tổng", "probability": 0.5, "interpretation": {
            "field": "budget_scope", "kind": "total_cap", "scope": "total"}},
        {"id": "opt-1", "label": "Thuê", "probability": 0.5, "interpretation": {
            "field": "budget_scope", "kind": "rent_cap", "scope": "rent"}}]}
    decision, best, decided_by, _ = decisions.decide(clarification, {}, mode="jev")
    assert (decision, decided_by) == ("accept", "jev")
    assert json.loads(cassette.read_text(encoding="utf-8"))["entries"][0]["kind"] == "jev"
    assert "monthly_income_vnd" not in json.dumps(recorded["payload"], ensure_ascii=False)

    # Phát lại: KHÔNG có httpx giả (post thật sẽ nổ mạng/失败) — vẫn cùng kết quả.
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kwargs:
                        (_ for _ in ()).throw(AssertionError("replay phải dùng cassette")))
    monkeypatch.setenv("HOMEMATCH_AGENT_RECORD", "")
    monkeypatch.setenv("HOMEMATCH_AGENT_REPLAY", str(cassette))
    decision2, best2, decided_by2, _ = decisions.decide(clarification, {}, mode="jev")
    assert (decision2, decided_by2) == ("accept", "jev")
    assert best2["probability"] == best["probability"] == 0.9
