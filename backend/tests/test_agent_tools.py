"""HN-03: hợp đồng registry, allowlist và biên tool; hoàn toàn offline."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial
import json

import pytest
from pydantic import ValidationError

from backend.app.agent_capability import CAPABILITIES, TOOL_CAPABILITIES
from backend.app.agent_tools import (AMENITY_LABELS, TOOL_REGISTRY, AskUserArgs, UpdateNeedsArgs,
                                     public_result, redact_result, tool_specs, tools_by_agent,
                                     workspace_view)
from backend.app.agents import AGENT_TOOLS, ToolBox
from backend.app.models import DomainError, DraftProfile


def test_renter_finance_ratio_stays_private_from_tools_and_model():
    from backend.app.agent_tools import public_result, redact_result
    payload = {"cost": {"housing_ratio": 0.3, "monthly_income_vnd": 20_000_000}}
    assert public_result(payload, for_renter=True) == {"cost": {"housing_ratio": 0.3}}
    assert public_result(payload) == {"cost": {}}
    assert redact_result(payload) == {"cost": {}}


@pytest.mark.parametrize("definition", TOOL_REGISTRY.values(), ids=TOOL_REGISTRY)
def test_every_registry_tool_has_an_executable_contract(definition):
    parsed = definition.Args.model_validate(definition.sample_args)
    schema = definition.spec()["function"]["parameters"]
    assert schema == definition.Args.model_json_schema()
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert definition.timeout_s > 0 and isinstance(definition.writes, bool)
    assert definition.capability in CAPABILITIES
    with pytest.raises(ValidationError):
        definition.Args.model_validate({**definition.sample_args, "unregistered_field": True})

    seen = []

    def handler(**arguments):
        seen.append(arguments)
        return {"note": "gọi 0901234567 qua son@example.com, 20 triệu", "count": 2,
                "nested": {"monthly_income_vnd": 20_000_000, "housing_ratio": 0.3}}

    box = ToolBox()
    result = box.invoke(definition.name, handler, definition.sample_args)
    assert result["ok"] is True
    assert seen == [parsed.model_dump(mode="json", exclude_unset=True)]
    assert box.calls == [{"agent": definition.agent, "tool": definition.name}]
    blob = json.dumps(result, ensure_ascii=False)
    model_blob = json.dumps(definition.redact(result), ensure_ascii=False)
    summary = definition.summarize(result)
    for forbidden in ("0901234567", "son@example.com", "monthly_income_vnd", "housing_ratio"):
        assert forbidden not in blob and forbidden not in model_blob and forbidden not in summary
    assert "20 triệu" in blob
    assert "20 triệu" not in model_blob and "20 triệu" not in summary
    assert len(summary) <= 160


def test_registry_generates_allowlist_capability_and_only_exposed_specs():
    assert AGENT_TOOLS == tools_by_agent()
    assert set().union(*AGENT_TOOLS.values()) == set(TOOL_REGISTRY)
    assert TOOL_CAPABILITIES == {name: definition.capability for name, definition in TOOL_REGISTRY.items()}
    specs = tool_specs()
    assert {spec["function"]["name"] for spec in specs} == {
        name for name, definition in TOOL_REGISTRY.items() if definition.exposed}
    assert len(specs) == 12  # simulate_loan + compare_rooms (HN-13)
    assert "extract_needs" not in {spec["function"]["name"] for spec in specs}


@pytest.mark.parametrize("field", ["destination_radius", "budget_scope", "area", "room_type", "people"])
def test_ask_user_model_selects_field_without_inventing_options(field):
    assert AskUserArgs(field=field).field == field
    with pytest.raises(ValidationError):
        AskUserArgs(field=field, options=["Cho 999 căn", "Tự nới trần"])
    assert AskUserArgs(field="other", question="Bạn muốn hỏi gì?", options=["A", "B"]).options == ["A", "B"]
    with pytest.raises(ValidationError):
        AskUserArgs(field="other")
    with pytest.raises(ValidationError):
        AskUserArgs(field="other", question="Bạn chọn?", options=["A", "B", "C", "D", "E"])
    with pytest.raises(ValidationError):
        AskUserArgs(question="Câu hỏi thiếu field")


@pytest.mark.parametrize("name, arguments, code", [
    ("unregistered_tool", {}, "tool_unavailable"),
    ("find_place", {}, "invalid_arguments"),
    ("find_place", {"query": 123}, "invalid_arguments"),
    ("update_needs", {"patch": {"monthly_income_vnd": 20_000_000}}, "invalid_patch"),
    ("update_needs", {"patch": {"people": "2"}}, "invalid_patch"),
])
def test_invalid_calls_are_structured_and_never_run_handler(name, arguments, code):
    def forbidden(**kwargs):
        pytest.fail("Không được thực thi handler với tham số không hợp lệ")

    box = ToolBox()
    result = box.invoke(name, forbidden, arguments)
    assert result["ok"] is False and result["error"] == code and result["hint"]
    assert "monthly_income_vnd" not in json.dumps(result)
    assert box.calls == []


@pytest.mark.parametrize("error, code", [
    (DomainError("unknown_place", "Không tìm thấy điểm mốc; gọi 0901234567"), "unknown_place"),
    (TimeoutError("son@example.com"), "tool_failed"),
    (RuntimeError("bí mật provider"), "tool_failed"),
])
def test_handler_errors_have_safe_envelopes(error, code):
    def fail(**kwargs):
        raise error

    result = ToolBox().invoke("find_place", fail, {"query": "HUST"})
    assert result["ok"] is False and result["error"] == code and result["hint"]
    assert "0901234567" not in json.dumps(result)
    assert "son@example.com" not in json.dumps(result)
    assert "bí mật provider" not in json.dumps(result, ensure_ascii=False)


def test_workspace_view_comes_from_successful_registry_tools():
    assert workspace_view([], DraftProfile()) == ("keep", None)
    assert workspace_view(["confirm_and_search"], DraftProfile()) == ("list", {"sorted_by": "match"})
    assert workspace_view(["confirm_and_search"], {"destination": {"label": "HUST"}}) == (
        "map", {"sorted_by": "distance"})
    assert workspace_view(["confirm_and_search", "room_details"], DraftProfile()) == ("detail", None)
    assert workspace_view(["estimate_cost", "ask_user"], DraftProfile()) == ("cost", None)


def test_error_summary_includes_only_safe_code():
    definition = TOOL_REGISTRY["find_place"]
    assert "unknown_place" in definition.summarize({"ok": False, "error": "unknown_place"})
    malicious = {"ok": False, "error": "0901234567 son@example.com", "message": "20 triệu"}
    summary = definition.summarize(malicious)
    for forbidden in ("0901234567", "son@example.com", "20 triệu"):
        assert forbidden not in summary


def test_public_result_keeps_grounded_money_and_unknown_costs():
    raw = {"title": "Phòng từ 4 triệu", "rent_vnd": 4_000_000, "monthly_total_vnd": None,
           "nested": [{"monthly_income_vnd": 20_000_000, "housing_ratio": 0.2,
                       "note": "Liên hệ 0901234567 hoặc son@example.com"}]}
    result = public_result(raw)
    assert result["title"] == "Phòng từ 4 triệu"
    assert result["rent_vnd"] == 4_000_000 and result["monthly_total_vnd"] is None
    assert raw["nested"][0]["monthly_income_vnd"] == 20_000_000
    blob = json.dumps(result, ensure_ascii=False)
    for forbidden in ("monthly_income_vnd", "housing_ratio", "0901234567", "son@example.com"):
        assert forbidden not in blob


@pytest.mark.parametrize("project", [public_result, redact_result])
def test_projection_preserves_valid_identifiers_without_allowing_contact_fields(project):
    room_ids = ["chotot-123456789", "chotot-0901234567", "synthetic-room-123456789",
                "demo-0901234567", "room-0123456789"]
    uid = "260bd4f0-0a96-408e-89c6-06146646154c"
    for room_id in room_ids:
        assert project({"room_id": room_id, "id": room_id}) == {"room_id": room_id, "id": room_id}
    assert project({"visible_room_ids": room_ids, "room_ids": room_ids, "top_ids": room_ids}) == {
        "visible_room_ids": room_ids, "room_ids": room_ids, "top_ids": room_ids}
    for key in ("turn_id", "session_id", "run_id", "conversation_id", "id"):
        assert project({key: uid}) == {key: uid}
    assert project({"session_ids": [uid], "selected_room_id": room_ids[0]}) == {
        "session_ids": [uid], "selected_room_id": room_ids[0]}
    for key in ("room_id", "id", "turn_id", "visible_room_ids"):
        value = ["0901234567"] if key.endswith("_ids") else "0901234567"
        assert "0901234567" not in json.dumps(project({key: value}))
    for key in ("room_id", "id", "session_id"):
        assert "son@example.com" not in json.dumps(project({key: "son@example.com"}))
    # Câu tự do không được hưởng ngoại lệ giữ mã bản ghi.
    assert "0901234567" not in project({"note": "chotot-0901234567"})["note"]


def test_registry_can_bind_handler_with_trusted_turn_context(monkeypatch):
    service, actor, toolbox = object(), object(), ToolBox()
    session = {"id": "fixture-session"}

    def handler(service_arg, session_arg, actor_arg, toolbox_arg, query, city_hint=None):
        assert (service_arg, session_arg, actor_arg, toolbox_arg) == (service, session, actor, toolbox)
        return {"found": True, "query": query, "city": city_hint}

    definition = replace(TOOL_REGISTRY["find_place"], handler=handler)
    monkeypatch.setitem(TOOL_REGISTRY, "find_place", definition)
    bound = partial(definition.handler, service, session, actor, toolbox)
    result = toolbox.invoke("find_place", bound, definition.sample_args)
    assert result == {"ok": True, "data": {"found": True, "query": "HUST", "city": "Hà Nội"}}


def test_thread_safe_step_reservation_preserves_raw_graph_contract():
    box = ToolBox(max_steps=6)

    def attempt(index):
        try:
            return box.call("ranking", "match_catalog", lambda: index)
        except DomainError as error:
            assert error.code == "agent_step_limit"
            return None

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(20)))
    assert len([value for value in results if value is not None]) == 6
    assert len(box.calls) == 6 and box.summary("ranking")["steps"] == 6


def test_update_needs_schema_pins_amenity_enum_and_forbids_money_fields():
    """Sửa luồng UX (14/11): model gọi sai update_needs hai lần mỗi lượt (trường tiền
    bị cấm, tiện ích viết bằng lời) — schema gửi model phải chặn trước: enum tiện ích
    đúng bằng AMENITY_KEYS kèm nghĩa tiếng Việt, mô tả công cụ cấm trường tiền.
    Kiểm tra runtime giữ lax để hàng rào invalid_amenity trong agent_loop còn nguyên."""
    from backend.app.models import AMENITY_KEYS

    definition = TOOL_REGISTRY["update_needs"]
    parameters = definition.spec()["function"]["parameters"]
    preferences = parameters["$defs"]["NeedsPatch"]["properties"]["preferences"]
    assert preferences["items"]["enum"] == list(AMENITY_KEYS)
    # Nghĩa tiếng Việt cho từng khóa để model ánh xạ được ("máy lạnh" → air_conditioning).
    for key in AMENITY_KEYS:
        assert key in preferences["items"]["description"] and AMENITY_LABELS.get(key)
    assert "máy lạnh" in preferences["items"]["description"]
    # Mô tả công cụ cấm trường tiền; hệ thống tự đọc tiền từ câu khách.
    assert "KHÔNG gửi bất kỳ trường tiền nào" in definition.description
    assert "tự đọc tất định từ câu của khách" in definition.description
    # Runtime vẫn nhận chuỗi lạ (handler invalid_amenity từ chối, không pydantic chặn trước).
    assert UpdateNeedsArgs.model_validate({"patch": {"preferences": ["máy lạnh"]}}
                                          ).patch.preferences == ["máy lạnh"]
    assert UpdateNeedsArgs.model_validate({"patch": {"preferences": ["air_conditioning"]}}
                                          ).patch.preferences == ["air_conditioning"]
