"""HN-04: ngữ cảnh hội thoại — workspace, tóm tắt 4 lượt, bộ nhớ, cắt theo cap.

Model là client giả kịch bản; không gọi mạng. Ngữ cảnh gửi model không bao giờ
chứa thu nhập, SĐT, email; tiền trong lượt cũ ở dạng placeholder."""
import json
from types import SimpleNamespace

import pytest

from backend.app.agent_loop import AGENT_SYSTEM_PROMPT, _estimate_tokens, build_context
from backend.app.interpreter import OpenAIInterpreter
from backend.app.models import Actor, Profile, Scenario
from backend.app.service import HomeMatchService


def message(content="ok", tokens=7):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=None))], usage=SimpleNamespace(total_tokens=tokens))


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
    service = HomeMatchService(tmp_path / "ctx.sqlite", interpreter=OpenAIInterpreter(
        client=FakeClient([]), model="fixture"))
    yield service
    service.close()


def confirmed(agent, sid, renter):
    agent.confirm(sid, renter, Profile(city="TP.HCM", area="Quận 7",
        max_monthly_cost_vnd=6_000_000, max_initial_cash_vnd=8_000_000,
        monthly_income_vnd=20_000_000, scenario=Scenario(people=2)), 0)
    return agent.results(sid, renter)["results"]


def test_context_carries_workspace_and_results_but_never_income(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    results = confirmed(agent, sid, renter)
    agent._workspace[sid] = {"view": "list", "selected_room_id": results[0]["room_id"],
                             "visible_room_ids": [item["room_id"] for item in results[:3]],
                             "focus_room_ids": []}
    context = json.loads(build_context(agent, agent.repo.session(sid), renter))
    assert [room["room_id"] for room in context["workspace"]["rooms"]] == \
        [item["room_id"] for item in results[:3]]
    assert context["workspace"]["selected_room_id"] == results[0]["room_id"]
    assert [item["room_id"] for item in context["current_results"]][:2] == \
        [item["room_id"] for item in results[:2]]
    assert "monthly_income_vnd" not in context
    assert "20000000" not in json.dumps(context)


def test_recent_turns_capped_at_six_and_redacted(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    for index in range(8):
        agent.interpreter.client = FakeClient([message("Đã ghi nhận nhu cầu.")])
        agent.message(sid, renter, f"câu hỏi {index}: gọi 0901234567 hoặc a@b.com, ngân sách 4 triệu")
    context = json.loads(build_context(agent, agent.repo.session(sid), renter))
    recent = context["recent_chat"]
    assert len(recent) == 6  # đúng 6 lượt gần nhất
    blob = json.dumps(context, ensure_ascii=False)
    assert "0901234567" not in blob and "a@b.com" not in blob
    assert "4 triệu" not in blob and "[TIEN_DA_TACH]" in blob


def test_cap_trims_summary_and_old_turns_before_workspace(agent, renter, monkeypatch):
    sid = agent.create_session(renter)["session_id"]
    results = confirmed(agent, sid, renter)
    agent._workspace[sid] = {"view": "map", "selected_room_id": None,
                             "visible_room_ids": [item["room_id"] for item in results],
                             "focus_room_ids": []}
    with agent.repo.db:
        agent.repo.db.execute("UPDATE hm_sessions SET summary_json=? WHERE id=?",
            (json.dumps({"text": "tóm tắt dài " * 80, "turns": 4}), sid))
    for index in range(6):
        agent.interpreter.client = FakeClient([message("ok")])
        agent.message(sid, renter, "lượt cũ rất dài " * 30)
    context = agent._turn_context(agent.repo.session(sid), renter)
    core_blob = json.dumps({key: context[key] for key in ("draft", "confirmed_profile", "notes")
                            if context.get(key) is not None}, ensure_ascii=False)
    workspace_blob = json.dumps({"workspace": context["workspace"]}, ensure_ascii=False)
    # Cap chỉ đủ cho nháp + một nửa workspace → tóm tắt phải bị bỏ, lượt cũ cắt gọn.
    cap = _estimate_tokens(AGENT_SYSTEM_PROMPT) + _estimate_tokens(core_blob) \
        + _estimate_tokens(workspace_blob) // 2
    monkeypatch.setenv("HOMEMATCH_CONTEXT_TOKEN_CAP", str(cap))
    trimmed = json.loads(build_context(agent, agent.repo.session(sid), renter))
    assert "draft" in trimmed and "workspace" in trimmed  # nháp không bao giờ bị cắt
    assert len(trimmed["workspace"]["rooms"]) < len(context["workspace"]["rooms"])
    assert "summary" not in trimmed  # tóm tắt bị bỏ trước khi workspace bị cắt quá nửa
    assert len(trimmed.get("recent_chat") or []) < 6  # lượt cũ cắt từ cũ nhất


def test_summary_preferred_over_old_turns_when_slack_is_small(agent, renter, monkeypatch):
    sid = agent.create_session(renter)["session_id"]
    results = confirmed(agent, sid, renter)
    agent._workspace[sid] = {"view": "list", "selected_room_id": None,
                             "visible_room_ids": [item["room_id"] for item in results],
                             "focus_room_ids": []}
    summary_text = "Khách tìm Quận 7, 2 người."
    with agent.repo.db:
        agent.repo.db.execute("UPDATE hm_sessions SET summary_json=? WHERE id=?",
            (json.dumps({"text": summary_text, "turns": 4}), sid))
    for index in range(6):
        agent.interpreter.client = FakeClient([message("ok")])
        agent.message(sid, renter, "lượt cũ rất dài " * 30)
    context = agent._turn_context(agent.repo.session(sid), renter)
    core_blob = json.dumps({key: context[key] for key in ("draft", "confirmed_profile", "notes")
                            if context.get(key) is not None}, ensure_ascii=False)
    # Cap đủ cho nháp + workspace đủ + tóm tắt ngắn, không đủ cho 6 lượt cũ dài.
    cap = _estimate_tokens(AGENT_SYSTEM_PROMPT) + _estimate_tokens(core_blob) \
        + _estimate_tokens(json.dumps({"workspace": context["workspace"]}, ensure_ascii=False)) \
        + _estimate_tokens(json.dumps({"summary": summary_text}, ensure_ascii=False)) + 10
    monkeypatch.setenv("HOMEMATCH_CONTEXT_TOKEN_CAP", str(cap))
    trimmed = json.loads(build_context(agent, agent.repo.session(sid), renter))
    assert trimmed.get("summary") == summary_text  # tóm tắt thắng lượt cũ khi chật chỗ
    assert len(trimmed.get("recent_chat") or []) < 6


def test_summary_updates_every_four_turns_without_tools_call(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    for index in range(3):
        agent.interpreter.client = FakeClient([message("Đã hiểu nhu cầu của bạn.")])
        agent.message(sid, renter, f"tìm phòng Quận 7 lần {index}")
    # Lượt thứ 4: một kịch bản cho lượt, một cho lần gọi tóm tắt (không kèm tools).
    turn4 = FakeClient([message("Đã hiểu nhu cầu của bạn."),
                        message("Khách muốn phòng Quận 7 TP.HCM cho 2 người; chưa rõ trần tiền.")])
    agent.interpreter.client = turn4
    agent.message(sid, renter, "tìm phòng Quận 7 lần 3")
    assert len(turn4.requests) == 2
    assert "tools" in turn4.requests[0] and "tools" not in turn4.requests[1]
    row = agent.repo.db.execute("SELECT summary_json FROM hm_sessions WHERE id=?", (sid,)).fetchone()
    summary = json.loads(row["summary_json"])
    assert summary["turns"] == 4 and summary["text"]
    agent.interpreter.client = FakeClient([message("ok")])
    agent.message(sid, renter, "câu khác")  # lượt 5 không cập nhật tóm tắt
    row = agent.repo.db.execute("SELECT summary_json FROM hm_sessions WHERE id=?", (sid,)).fetchone()
    assert json.loads(row["summary_json"])["turns"] == 4


def test_summary_enters_context_and_survives_restart(renter, tmp_path):
    path = tmp_path / "restart.sqlite"
    service = HomeMatchService(path, interpreter=OpenAIInterpreter(client=FakeClient([]), model="fixture"))
    try:
        sid = service.create_session(renter)["session_id"]
        for index in range(3):
            service.interpreter.client = FakeClient([message("ok")])
            service.message(sid, renter, f"lượt {index}")
        service.interpreter.client = FakeClient([message("ok"), message("Khách tìm phòng Quận 7.")])
        service.message(sid, renter, "lượt 3")
    finally:
        service.close()
    restarted = HomeMatchService(path, interpreter=OpenAIInterpreter(client=FakeClient([]), model="fixture"))
    try:
        context = json.loads(build_context(restarted, restarted.repo.session(sid), renter))
        assert context["summary"]
        assert "monthly_income_vnd" not in context
    finally:
        restarted.close()


def test_summarizer_failure_never_breaks_the_turn(agent, renter):
    sid = agent.create_session(renter)["session_id"]
    for index in range(3):
        agent.interpreter.client = FakeClient([message("ok")])
        agent.message(sid, renter, f"lượt {index}")
    # Lượt 4: lượt chạy ok nhưng lần gọi tóm tắt lỗi provider → bỏ qua, lượt vẫn xong.
    agent.interpreter.client = FakeClient([message("ok"), ConnectionError("summarizer down")])
    reply = agent.message(sid, renter, "lượt 3")
    assert reply["message"]
    row = agent.repo.db.execute("SELECT summary_json FROM hm_sessions WHERE id=?", (sid,)).fetchone()
    assert row["summary_json"] is None
