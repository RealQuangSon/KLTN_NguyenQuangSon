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
    # HN-10: sau các bước tool, câu trả lời stream delta rồi done.
    assert lines[-1]["type"] == "done"
    assert [line["type"] for line in lines[:2]] == ["step", "step"]
    deltas = [line for line in lines if line["type"] == "delta"]
    assert deltas and all(set(item) == {"type", "text"} for item in deltas)
    assert "".join(item["text"] for item in deltas) == "Mình hiểu HUST là Đại học Bách Khoa Hà Nội."
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

def test_stream_replaces_answer_when_post_check_fails(tmp_path):
    # HN-10: số bịa trong câu trả lời → delta đã phát, nhưng replace + done
    # phải mang câu template an toàn.
    service, app = stream_app(tmp_path, [
        message(content="Có đúng 99 căn giá 1 triệu gần đây."),
    ])
    renter_headers = {"Authorization": "Bearer demo-renter-a"}
    with TestClient(app) as client:
        sid = client.post("/sessions", headers=renter_headers).json()["session_id"]
        with client.stream("POST", f"/sessions/{sid}/messages/stream", headers=renter_headers,
                           json={"text": "gần HUST"}) as response:
            lines = [json.loads(line) for line in response.iter_lines() if line.strip()]
    deltas = "".join(item["text"] for item in lines if item["type"] == "delta")
    assert "99" in deltas  # delta đã phát raw trước hậu kiểm
    replace = [item for item in lines if item["type"] == "replace"]
    assert replace and "99" not in replace[-1]["text"]
    done = lines[-1]
    assert done["type"] == "done" and "99" not in done["data"]["message"]
    assert done["data"]["message"] == replace[-1]["text"]



def test_stream_error_line_on_domain_error(tmp_path):
    service = HomeMatchService(tmp_path / "e.sqlite")
    renter_headers = {"Authorization": "Bearer demo-renter-a"}
    with TestClient(create_app(lambda: service)) as client:
        with client.stream("POST", "/sessions/sid-không-tồn-tại/messages/stream",
                           headers=renter_headers, json={"text": "xin chào"}) as response:
            lines = [json.loads(line) for line in response.iter_lines() if line.strip()]
    assert lines[-1]["type"] == "error"
    assert lines[-1]["error"]["code"] in {"forbidden", "not_found"}
