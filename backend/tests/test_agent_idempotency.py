"""HN-03: retry sau đứt stream/khởi động lại và transaction tool ghi, offline."""
import json
from types import SimpleNamespace

import pytest

from backend.app.agent_executor import execute_tool
from backend.app.agents import ToolBox
from backend.app.models import Actor, DomainError, DraftPatch
from backend.app.service import HomeMatchService
from backend.app.agent_tools import TOOL_REGISTRY
from backend.app.agent_loop import build_tools
from backend.app.interpreter import OpenAIInterpreter


def test_uuid_key_with_digit_suffix_is_valid_but_phone_is_not(service, renter):
    sid = service.create_session(renter)["session_id"]
    key = "260bd4f0-0a96-408e-89c6-06146646154c"
    assert service.message(sid, renter, "Xin chào", turn_id=key)["turn_id"] == key
    with pytest.raises(DomainError) as error:
        service.message(sid, renter, "Xin chào", turn_id="0901234567")
    assert error.value.code == "invalid_turn_id"


def test_retry_cache_obeys_chat_retention(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Xin chào", turn_id="expires")
    service.repo.db.execute("UPDATE hm_agent_requests SET created_at=?", ("2000-01-01T00:00:00+00:00",))
    service.purge_transcripts()
    assert service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_agent_requests").fetchone()["c"] == 0


@pytest.mark.parametrize("name", [name for name, tool in TOOL_REGISTRY.items() if tool.exposed])
def test_real_exposed_handlers_obey_envelope_contract(service, renter, name):
    sid = service.create_session(renter)["session_id"]
    box = ToolBox()
    handlers = build_tools(service, service.repo.session(sid), renter, "", box)
    result = execute_tool(service, box, sid, "contract", name, handlers[name]["fn"],
                          TOOL_REGISTRY[name].sample_args, actor=renter)
    assert isinstance(result["ok"], bool)
    assert ("data" in result) if result["ok"] else all(key in result for key in ("error", "message", "hint"))


def test_turn_retry_survives_restart_without_duplicate_budget_or_transcript(storage, renter):
    service = HomeMatchService(storage)
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng Quận 7 dưới 4 triệu", turn_id="first")
    first = service.message(sid, renter, "nới thêm 1 triệu", turn_id="relative")
    count = service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_chat_transcripts").fetchone()["c"]
    service.close()
    service = HomeMatchService(storage)
    try:
        repeated = service.message(sid, renter, "nới thêm 1 triệu", turn_id="relative")
        assert repeated["draft_revision"] == first["draft_revision"]
        assert repeated["draft"]["budget_hint_vnd"] == 5_000_000
        assert service.budget.used(sid) == 0
        assert service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_chat_transcripts").fetchone()["c"] == count
        with pytest.raises(DomainError, match="nội dung khác") as conflict:
            service.message(sid, renter, "nới thêm 2 triệu", turn_id="relative")
        assert conflict.value.code == "idempotency_conflict"
        with pytest.raises(DomainError) as forbidden:
            service.message(sid, Actor(id="renter-b", role="renter"), "nới thêm 1 triệu", turn_id="relative")
        assert forbidden.value.code == "forbidden"
        service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=first["draft_revision"], set={"people": 2}))
        with pytest.raises(DomainError) as stale:
            service.message(sid, renter, "nới thêm 1 triệu", turn_id="relative")
        assert stale.value.code == "stale_turn"
    finally:
        service.close()


def test_write_tool_cache_and_error_rollback(service, renter):
    sid = service.create_session(renter)["session_id"]
    def write(patch):
        service.repo.db.execute("UPDATE hm_sessions SET draft_revision=draft_revision+1 WHERE id=?", (sid,))
        return {"saved": True}
    first = execute_tool(service, ToolBox(), sid, "turn", "update_needs", write, {"patch": {"people": 2}}, actor=renter)
    second = execute_tool(service, ToolBox(), sid, "turn", "update_needs", write, {"patch": {"people": 2}}, actor=renter)
    assert first == second and first["ok"]
    assert service.repo.session(sid)["draft_revision"] == 1
    def broken(patch):
        write(patch)
        raise DomainError("failed_write", "Không lưu được.", 409)
    failed = execute_tool(service, ToolBox(), sid, "bad", "update_needs", broken, {"patch": {}}, actor=renter)
    assert not failed["ok"] and failed["error"] == "failed_write"
    assert service.repo.session(sid)["draft_revision"] == 1
    assert service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_agent_tool_calls").fetchone()["c"] == 1
    with pytest.raises(DomainError) as forbidden:
        execute_tool(service, ToolBox(), sid, "turn", "update_needs", write,
                     {"patch": {"people": 2}}, actor=Actor(id="renter-b", role="renter"))
    assert forbidden.value.code == "forbidden"


def test_cache_excludes_profile_income_and_is_scoped_to_session(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile.model_copy(update={"monthly_income_vnd": 20_000_000}), 0)
    service.message(sid, renter, "Xin chào", turn_id="shared")
    blob = service.repo.db.execute("SELECT response_json FROM hm_agent_requests WHERE session_id=?", (sid,)).fetchone()["response_json"]
    assert "monthly_income_vnd" not in blob and "20000000" not in blob
    other = service.create_session(renter)["session_id"]
    reply = service.message(other, renter, "Xin chào", turn_id="shared")
    assert reply["session_id"] == other


def test_retry_after_confirm_keeps_one_run_and_identical_response(storage, renter):
    responses = [
        SimpleNamespace(content=None, tool_calls=[SimpleNamespace(id="c1", function=SimpleNamespace(
            name="update_needs", arguments=json.dumps({"patch": {"city": "TP.HCM"}})))]),
        SimpleNamespace(content=None, tool_calls=[SimpleNamespace(id="c2", function=SimpleNamespace(
            name="confirm_and_search", arguments="{}"))]),
        SimpleNamespace(content="Mình đã tìm phòng dưới 4 triệu.", tool_calls=None),
    ]
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=responses.pop(0))],
                               usage=SimpleNamespace(total_tokens=7))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    service = HomeMatchService(storage, interpreter=OpenAIInterpreter(client=client, model="fixture"))
    try:
        sid = service.create_session(renter)["session_id"]
        first = service.message(sid, renter, "phòng dưới 4 triệu", turn_id="confirm-retry")
        second = service.message(sid, renter, "phòng dưới 4 triệu", turn_id="confirm-retry")
        assert first == second
        assert service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_runs WHERE session_id=?", (sid,)).fetchone()["c"] == 1
        assert service.repo.session(sid)["profile_version"] == 1
    finally:
        service.close()
