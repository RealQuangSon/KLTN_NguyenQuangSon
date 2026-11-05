"""AG-13: vòng lặp agent — LLM tự gọi tool qua model giả (offline, không mạng).

Kịch bản kiểm: chuỗi find_place → update_needs → confirm_and_search → câu trả
lời; tool cấm tiền; tool lạ bị chặn; vượt 6 bước → câu trả lời an toàn; số bịa
trong văn bản bị thay; provider lỗi → rơi về graph cũ (agent_mode).
"""
import json
from types import SimpleNamespace

import pytest

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
    """Scripted chat.completions: mỗi lượt gọi lấy một phản hồi từ hàng đợi."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        # fake OpenAI client: client.chat.completions.create
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
def service(tmp_path):
    agent = HomeMatchService(tmp_path / "loop.sqlite", interpreter=OpenAIInterpreter(
        client=SimpleNamespace(), model="fixture-model"))
    yield agent
    agent.close()


def test_loop_runs_tools_and_publishes_results_in_one_turn(service, renter):
    client = FakeClient([
        message(tool_calls=[call("c1", "find_place", query="HUST", city_hint="Hà Nội")]),
        message(tool_calls=[call("c2", "update_needs",
                                 patch={"city": "Hà Nội", "area": "Quận Hai Bà Trưng",
                                        "destination_text": "HUST"})]),
        message(tool_calls=[call("c3", "confirm_and_search")]),
        message(content="Mình hiểu HUST ở Đại Cồ Việt, Hai Bà Trưng; kết quả đã hiện ở khung bên phải."),
    ])
    service.interpreter.client = client
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng trọ dưới 4 triệu gần HUST cho 1 người")
    assert reply["agent_mode"] == "loop"
    assert reply["steps"] and len(reply["steps"]) == 3
    assert "find_place" in reply["steps"][0] and "confirm_and_search" in reply["steps"][2]
    draft = service.session(sid, renter)["draft"]
    assert draft["city"] == "Hà Nội" and draft["area"] == "Quận Hai Bà Trưng"
    assert draft["destination"]["label"] == "Đại học Bách Khoa Hà Nội"
    assert draft["field_status"]["city"] == "inferred"
    session = service.session(sid, renter)
    assert session["active_run_id"]
    run = service.repo.run(session["active_run_id"])
    # Trần tổng tháng 4 triệu đọc từ câu khách (tất định); có thể ra kết quả hoặc
    # no_match nếu kho không có căn — quyết định xếp hạng vẫn là code tất định.
    assert run["status"] in {"published", "no_match", "needs_verification"}
    if run["status"] == "published":
        assert run["items"]
        assert any(item["components"].get("location") is not None for item in run["items"])
    assert service.session(sid, renter)["draft"]["budget_hint_vnd"] == 4_000_000
    # Thu nhập không bao giờ xuất hiện trong ngữ cảnh gửi model.
    sent_context = client.requests[0]["messages"][1]["content"]
    assert "monthly_income_vnd" not in sent_context


def test_loop_rejects_money_and_privilege_in_patch(service, renter):
    client = FakeClient([
        message(tool_calls=[call("c1", "update_needs", patch={"rent_budget_hint_vnd": 4_000_000, "role": "admin"})]),
        message(content="Mình không thể tự ghi mức tiền hay quyền hạn; bạn nhập trong “Nhu cầu của tôi” nhé."),
    ])
    service.interpreter.client = client
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "phòng dưới 4 triệu")
    assert reply["agent_mode"] == "loop"
    # Bước tool báo lỗi có cấu trúc cho model, không 500, không ghi gì vào nháp.
    assert any("invalid_patch" in step for step in reply["steps"])
    draft = service.session(sid, renter)["draft"]
    assert draft["city"] is None and draft["field_status"].get("city") is None


def test_loop_blocks_tools_outside_the_allowlist(service, renter):
    client = FakeClient([
        message(tool_calls=[call("c1", "delete_all_rooms")]),
        message(content="Mình không có quyền đó."),
    ])
    service.interpreter.client = client
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "xoá hết phòng đi")
    assert reply["agent_mode"] == "loop"
    assert any("tool_unavailable" in step for step in reply["steps"])
    assert service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_runs").fetchone()["c"] == 0


def test_loop_answers_safely_after_step_limit(service, renter):
    from backend.app.agent_loop import SAFE_REPLY
    client = FakeClient([message(tool_calls=[call(f"c{i}", "search_rooms")]) for i in range(8)])
    service.interpreter.client = client
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "tìm phòng Quận 7")
    assert reply["agent_mode"] == "loop"
    assert reply["message"] == SAFE_REPLY
    assert len(reply["steps"]) == 6  # đúng MAX_AGENT_STEPS, không chạy dài hơn


def test_loop_replaces_fabricated_numbers(service, renter):
    from backend.app.agent_loop import check_numbers
    # Số có trong câu khách hoặc kết quả tool: giữ lại.
    assert check_numbers("rẻ nhất 3,5 triệu cho 2 người", "3,5 triệu cho 2 người",
                         ['{"count": 5, "min_monthly_total_vnd": 3500000}']) == \
        "rẻ nhất 3,5 triệu cho 2 người"
    # Số bịa: thay bằng câu template không số.
    fabricated = check_numbers("Có 99 căn, rẻ nhất 1 triệu.", "tìm phòng",
                               ['{"count": 5}'])
    assert "99" not in fabricated and "1 triệu" not in fabricated


def test_provider_error_falls_back_to_the_old_graph(service, renter):
    client = FakeClient([ConnectionError("gateway down")])
    service.interpreter.client = client
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng Quận 7")
    assert reply["agent_mode"] == "graph_fallback"
    # Graph cũ chạy tiếp bằng interpreter openai → lỗi provider → fallback biểu mẫu.
    assert reply["status"] == "needs_clarification" and reply["questions"]
    assert "ai_unavailable" in " ".join(reply["questions"]) or "ai_unavailable" in (reply.get("message") or "")


def test_demo_mode_never_enters_the_loop(storage, renter):
    agent = HomeMatchService(storage)  # demo interpreter mặc định
    try:
        sid = agent.create_session(renter)["session_id"]
        reply = agent.message(sid, renter, "Tìm phòng Quận 7")
        assert "agent_mode" not in reply or reply.get("agent_mode") != "loop"
        assert reply["intent"] == "find_room" and reply["questions"]
    finally:
        agent.close()
