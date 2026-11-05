"""WS-02: stream NDJSON các bước xử lý — thứ tự sự kiện, nội dung bước sạch PII."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.interpreter import OpenAIInterpreter
from backend.app.main import create_app
from backend.app.service import HomeMatchService


def call(id_, name, **arguments):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name,
                                                            arguments=json.dumps(arguments, ensure_ascii=False)))


def message(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))], usage=SimpleNamespace(total_tokens=7))


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        return self.turns.pop(0)


def stream_app(tmp_path, turns):
    service = HomeMatchService(tmp_path / "stream.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient(turns), model="fixture-model"))
    return service, create_app(lambda: service)


def test_stream_emits_steps_then_done(tmp_path):
    service, app = stream_app(tmp_path, [
        message(tool_calls=[call("c1", "find_place", query="HUST", city_hint="Hà Nội")]),
        message(content="Mình hiểu HUST là Đại học Bách Khoa Hà Nội."),
    ])
    renter_headers = {"Authorization": "Bearer demo-renter-a"}
    with TestClient(app) as client:
        sid = client.post("/sessions", headers=renter_headers).json()["session_id"]
        with client.stream("POST", f"/sessions/{sid}/messages/stream", headers=renter_headers,
                           json={"text": "gần HUST"}) as response:
            assert response.headers["content-type"].startswith("application/x-ndjson")
            lines = [json.loads(line) for line in response.iter_lines() if line.strip()]
    assert [line["type"] for line in lines] == ["step", "step", "done"]
    assert lines[0]["step"] == {"name": "route", "kind": "router", "detail": "AI phân tích nhu cầu"}
    assert lines[1]["step"]["name"] == "find_place" and lines[1]["step"]["kind"] == "tool"
    done = lines[-1]["data"]
    assert done["agent_mode"] == "loop" and done["steps"] and len(done["steps"]) == 1
    assert done["status"] == "needs_clarification"


def test_stream_step_lines_never_carry_pii_or_money_or_income(tmp_path):
    service, app = stream_app(tmp_path, [
        message(tool_calls=[call("c1", "find_place", query="HUST")]),
        message(content="Đã ghi nhận nhu cầu."),
    ])
    renter_headers = {"Authorization": "Bearer demo-renter-a"}
    with TestClient(create_app(lambda: service)) as client:
        sid = client.post("/sessions", headers=renter_headers).json()["session_id"]
        with client.stream("POST", f"/sessions/{sid}/messages/stream", headers=renter_headers,
                           json={"text": "gọi tôi 0901234567, thu nhập 20 triệu, gần HUST"}) as response:
            blob = "\n".join(response.iter_lines())
    assert "0901234567" not in blob
    assert "monthly_income_vnd" not in blob
    assert "20 triệu" not in blob
    assert "find_place" in blob  # bước tool vẫn hiện


def test_stream_error_line_on_domain_error(tmp_path):
    service = HomeMatchService(tmp_path / "e.sqlite")
    renter_headers = {"Authorization": "Bearer demo-renter-a"}
    with TestClient(create_app(lambda: service)) as client:
        with client.stream("POST", "/sessions/sid-không-tồn-tại/messages/stream",
                           headers=renter_headers, json={"text": "xin chào"}) as response:
            lines = [json.loads(line) for line in response.iter_lines() if line.strip()]
    assert lines[-1]["type"] == "error"
    assert lines[-1]["error"]["code"] in {"forbidden", "not_found"}
