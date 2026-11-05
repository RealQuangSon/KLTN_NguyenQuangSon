"""AG-13 — vòng lặp agent: LLM tự suy luận và tự gọi tool.

Phân vai giữ bất biến luận văn: LLM **quyết định và diễn giải**; tool **tính và
kiểm**. Tiền, lọc cứng, xếp hạng, quyền và công bố là code tất định bên trong
tool (qua `ToolBox.call`, giới hạn `MAX_AGENT_STEPS` bước/lượt). Mọi thứ LLM
đề xuất (địa điểm, quận) được tool kiểm chứng rồi mới ghi, và ghi ở trạng thái
`inferred` kèm câu nói lại cho khách. Model lỗi/hết ngân sách phiên → caller
(`service._chat_turn`) rơi về graph cũ `route → interview`
(`agent_mode="graph_fallback"`), không bao giờ ném 500 cho khách.
"""
from __future__ import annotations

import json
import re
import time

from pydantic import ValidationError

from .agent_provenance import stamp
from .agents import ToolBox
from .locations import resolve_place
from .models import Destination, DomainError

MAX_AGENT_STEPS = 6
SAFE_REPLY = ("Mình xử lý chưa trọn vẹn yêu cầu này trong số bước cho phép. "
              "Bạn nói rõ hơn nhu cầu (khu vực, mức tiền, loại phòng) hoặc dùng “Nhu cầu của tôi” nhé.")
# Số trong câu trả lời phải xuất hiện trong câu của khách hoặc trong kết quả tool.
_NUMBER = re.compile(r"\d[\d.,]*")

AGENT_SYSTEM_PROMPT = """Bạn là trợ lý tìm phòng trọ HomeMatch cho khách tại TP.HCM và Hà Nội.
Dùng hiểu biết chung để hiểu địa danh, khu vực và nhu cầu ngầm ("gần HUST", "phòng 2 người", "nới thêm tiền").
Khi suy ra điều khách chưa nói rõ, gọi tool để kiểm chứng rồi nói lại giả định cho khách sửa ("Mình hiểu HUST ở Đại Cồ Việt, Hai Bà Trưng — sai thì bấm sửa").
Không tự bịa số tiền hay số liệu: mọi con số trong câu trả lời phải lấy từ kết quả tool hoặc từ câu của khách.
Không tự nới điều kiện cứng (khu vực, trần tiền, tiện ích bắt buộc): chỉ đề nghị như một lựa chọn, khách xác nhận mới áp.
Thu nhập của khách không có trong ngữ cảnh, không được hỏi hay suy đoán.
Tiền trong tin nhắn đã được tách bằng placeholder; mức tiền khách nêu nằm ở ngữ cảnh dưới dạng trần gợi ý.
Trả lời bằng tiếng Việt, ngắn gọn, nói rõ các bước đã làm."""


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": required, "additionalProperties": False}}}


TOOL_SPECS = [
    _tool("find_place", "Tra điểm mốc (trường, bệnh viện, KCN, ga, bến xe, TTTM, khu đô thị) theo tên/không dấu.",
          {"query": {"type": "string"}, "city_hint": {"type": "string", "enum": ["TP.HCM", "Hà Nội"]}},
          ["query"]),
    _tool("update_needs", "Ghi nhu cầu đã kiểm chứng vào nháp. Chỉ các trường: city, area, people, room_type,"
          " bedrooms, preferences (danh sách tiện ích), needs_destination, accept_estimated_data,"
          " soft_description, destination_text (điểm mốc đã tra bằng find_place)."
          " Cấm mọi trường tiền/thu nhập; mức tiền khách nêu đã được ghi tự động.",
          {"patch": {"type": "object"}}, ["patch"]),
    _tool("search_rooms", "Xem trước số căn khớp nhu cầu nháp (không ghi gì): số căn, giá thấp nhất, lý do bị loại.",
          {}, []),
    _tool("confirm_and_search", "Xác nhận hồ sơ từ nháp và chạy vòng tìm; trả trạng thái, số căn và top căn.",
          {}, []),
    _tool("ask_user", "Kết thúc lượt bằng MỘT câu hỏi ngắn + các lựa chọn ngắn để khách bấm;"
          " lựa chọn phải đến từ kết quả find_place/search_rooms.",
          {"question": {"type": "string"},
           "options": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
          ["question"]),
    _tool("room_details", "Chi tiết một căn trong kết quả hiện tại theo mã phòng hoặc 'căn số N'.",
          {"room_ref": {"type": "string"}}, ["room_ref"]),
    _tool("estimate_cost", "Tính chi phí tháng/vào ở/khoản vay cho một căn trong kết quả hiện tại (tool tất định).",
          {"room_id": {"type": "string"}}, ["room_id"]),
    _tool("search_handbook", "Tra cẩm nang quyền lợi người thuê (nội quy, cọc, tạm trú…).",
          {"question": {"type": "string"}}, ["question"]),
    _tool("open_landlord_chat", "Mở hội thoại với chủ nhà của một căn trong kết quả hiện tại.",
          {"room_ref": {"type": "string"}}, ["room_ref"]),
    _tool("prepare_viewing", "Kiểm tra căn trong kết quả hiện tại có đặt lịch được không (chưa tạo lịch;"
          " khách bấm xác nhận trên giao diện thì lịch mới được tạo).",
          {"room_ref": {"type": "string"}}, ["room_ref"]),
]
TOOL_NAMES = frozenset(spec["function"]["name"] for spec in TOOL_SPECS)


def _strip_income(payload):
    """Kết quả tool cho LLM không bao giờ mang thu nhập hay tỉ lệ lộ thu nhập."""
    if isinstance(payload, dict):
        return {key: _strip_income(value) for key, value in payload.items()
                if key not in {"monthly_income_vnd", "housing_ratio"}}
    if isinstance(payload, list):
        return [_strip_income(item) for item in payload]
    return payload


def _number_key(value: str) -> str:
    return re.sub(r"[.,]", "", value)


def check_numbers(answer: str, user_text: str, tool_payloads: list[str]) -> str:
    """Hậu kiểm: số trong câu trả lời phải khớp số từ câu khách hoặc kết quả tool.

    So ở dạng đã bỏ dấu ngăn cách ("4,5 triệu" → "45" nằm trong "4500000").
    Sai → thay toàn bộ câu bằng câu template không số; không bao giờ giữ số bịa."""
    allowed = _number_key(user_text) + "|" + "|".join(_number_key(part) for part in tool_payloads)
    for match in _NUMBER.finditer(answer):
        key = _number_key(match.group(0))
        if key and key not in allowed:
            return ("Mình vừa kiểm tra nhu cầu của bạn qua các bước bên dưới; số liệu chi tiết "
                    "xem trong khung kết quả hoặc hỏi mình thêm.")
    return answer


def build_tools(service, session: dict, actor, text: str, toolbox: ToolBox) -> dict:
    """Bộ tool của lượt: hàm tất định + agent cho phép, bó vào phiên hiện tại."""
    results_guard = service.results(session["id"], actor)
    visible = {item["room_id"]: item for item in results_guard["results"]}

    def find_place(query: str, city_hint: str | None = None):
        draft = service._draft(session["id"])
        place = resolve_place(str(query), city_hint or draft.city)
        if place is None:
            return {"found": False,
                    "note": "Không có trong danh mục điểm mốc; hỏi lại tên cụ thể hoặc dùng khu vực/quận."}
        return {"found": True, **place}

    def update_needs(patch: dict):
        forbidden = {"rent_budget_hint_vnd", "monthly_budget_vnd", "monthly_income_vnd", "budget_hint_vnd",
                     "max_monthly_cost_vnd", "budget_hint", "role", "approved", "destination"}
        if forbidden & set(patch):
            raise DomainError("invalid_patch",
                              f"Chỉ ghi nhu cầu qua các trường được cấp; trường tiền/quyền bị cấm: {sorted(forbidden & set(patch))}",
                              422)
        patch = dict(patch)
        destination_text = patch.pop("destination_text", None)
        if destination_text:
            place = resolve_place(str(destination_text), service._draft(session["id"]).city)
            if place is None:
                raise DomainError("unknown_place", "Điểm mốc không có trong danh mục; gọi find_place trước.", 422)
            patch["destination"] = Destination(
                label=place["label"], latitude=place["latitude"], longitude=place["longitude"],
                uncertainty_m=place["uncertainty_m"], max_distance_m=3000)
        updated = service._apply_agent_patch(session["id"], patch)
        return {"saved": True, "fields": sorted(updated), "note": "đã ghi ở trạng thái inferred; nhớ nói lại giả định cho khách"}

    def search_rooms():
        profile = service._profile_from_draft(session["id"])
        if profile is None:
            return {"count": 0, "note": "Chưa đủ dữ liệu tối thiểu (thành phố + mức tiền); hỏi khách bổ sung."}
        items, diagnostics = service.catalog.match(profile, service.matching_method)
        rejected = {key: value for key, value in (diagnostics.get("rejected") or {}).items() if value}
        monthly = [item.cost.monthly_total_vnd for item in items if item.cost.monthly_total_vnd is not None]
        return {"count": len(items),
                "min_monthly_total_vnd": min(monthly) if monthly else None,
                "rejected_top": dict(sorted(rejected.items(), key=lambda kv: -kv[1])[:3]),
                "sample": [{"room_id": item.room_id, "title": item.title.split(". ")[0],
                            "monthly_total_vnd": item.cost.monthly_total_vnd} for item in items[:3]]}

    def confirm_and_search():
        profile = service._profile_from_draft(session["id"])
        if profile is None:
            raise DomainError("needs_more_info", "Cần thành phố và mức tiền trước khi tìm.", 422)
        fresh = service.repo.session(session["id"])
        result = service.confirm(session["id"], actor, profile, fresh["draft_revision"])
        return {"status": result["status"], "count": len(result["results"]),
                "sorted_by": "khoảng cách tới điểm đến" if profile.destination else "điểm khớp nhu cầu",
                "top": [{"room_id": item["room_id"], "title": item["title"],
                         "monthly_total_vnd": item["cost"].get("monthly_total_vnd")}
                        for item in result["results"][:3]]}

    def ask_user(question: str, options: list[str] | None = None):
        return {"question": str(question), "options": [str(item) for item in (options or [])][:4]}

    def _visible_room(ref: str):
        room_id = service.room_reference_in(str(ref), visible)
        if room_id is None:
            raise DomainError("not_visible",
                              "Không tìm thấy căn trong kết quả hiện tại; dùng room_id hoặc 'căn số N'.", 403)
        return visible[room_id]

    def room_details(room_ref: str):
        item = _visible_room(room_ref)
        room = next(room for room in service.catalog.rooms() if room.id == item["room_id"])
        return {"room_id": room.id, "title": room.title.split(". ")[0], "rent_vnd": room.quote.rent_vnd,
                "deposit_vnd": room.quote.deposit_vnd, "area": room.area, "city": room.city,
                "capacity": room.capacity, "house_rules_head": (room.house_rules or "")[:200]}

    def estimate_cost(room_id: str):
        item = _visible_room(room_id)
        room = next(room for room in service.catalog.rooms() if room.id == item["room_id"])
        profile = service._confirmed_profile(session["id"])
        cost = service._simulate_item(room, profile, scenario=profile.scenario,
                                      cost_split=profile.cost_split, loan=profile.loan)
        return _strip_income(cost)

    def search_handbook(question: str):
        from . import handbook
        return handbook.answer(str(question))

    def open_landlord_chat(room_ref: str):
        item = _visible_room(room_ref)
        conversation = service.start_conversation(actor, item["room_id"], session["id"])
        return {"conversation_id": conversation["conversation_id"],
                "note": "Đã mở hội thoại; ngữ cảnh chuyển kèm cho chủ nhà (chỉ băng tài chính, không thu nhập)."}

    def prepare_viewing(room_ref: str):
        item = _visible_room(room_ref)
        return {"prepared": True, "room_id": item["room_id"],
                "note": "Căn đủ điều kiện đặt lịch; khách chọn giờ và bấm 'Yêu cầu xem' thì lịch mới được tạo."}

    return {
        "find_place": {"agent": "needs", "fn": find_place},
        "update_needs": {"agent": "needs", "fn": update_needs},
        "search_rooms": {"agent": "needs", "fn": search_rooms},
        "confirm_and_search": {"agent": "needs", "fn": confirm_and_search},
        "ask_user": {"agent": "needs", "fn": ask_user},
        "room_details": {"agent": "needs", "fn": room_details},
        "estimate_cost": {"agent": "finance", "fn": estimate_cost},
        "search_handbook": {"agent": "handbook", "fn": search_handbook},
        "open_landlord_chat": {"agent": "support", "fn": open_landlord_chat},
        "prepare_viewing": {"agent": "needs", "fn": prepare_viewing},
    }


def run_turn(service, session: dict, actor, text: str,
             emit=None) -> tuple[dict, dict]:
    """Một lượt chat chạy bằng vòng lặp tool. Trả về (response, provenance).

    Chỉ gọi khi `HOMEMATCH_LLM_MODE=openai`; mọi lỗi provider/budget/step nổ ra
    cho caller rơi về graph cũ — vòng lặp không tự che lỗi mạng."""
    interpreter = service.interpreter
    # Mức tiền trong CÂU CỦA KHÁCH được đọc tất định (như graph cũ), không qua LLM:
    # model không được tự ghi trường tiền nào khác qua update_needs.
    from .interpreter import rent_budget_hint
    hint = rent_budget_hint(text)
    if hint:
        service._apply_chat_budget_hint(session["id"], hint, session["draft_revision"])
        session = service.repo.session(session["id"])
    toolbox = ToolBox(max_steps=MAX_AGENT_STEPS)
    tools = build_tools(service, session, actor, text, toolbox)
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(service._agent_context(session), ensure_ascii=False)},
        {"role": "user", "content": text},
    ]
    steps: list[dict] = []
    tool_payloads: list[str] = []
    usage_total = {"logical_calls": 0, "tokens": 0, "saw_none": False}
    response_dict: dict | None = None
    turn_started = time.monotonic()
    # WS-02: phát sự kiện bước ngay khi chạy; timeout lượt 60 s do endpoint giữ.
    if emit is not None:
        emit({"name": "route", "kind": "router", "detail": "AI phân tích nhu cầu"})

    def finalize(answer: str, questions: list[str] | None, mode_note: str | None = None):
        return {"intent": "find_room", "status": "needs_clarification", "message": answer,
                "questions": questions or None, "interpreter_mode": "openai", "agent_mode": "loop",
                "steps": [f"{entry['tool']}: {entry['detail']}" for entry in steps] or None}

    for _ in range(MAX_AGENT_STEPS):
        if time.monotonic() - turn_started > 55:
            response_dict = finalize(SAFE_REPLY, None)
            break
        service.budget.spend(session["id"])
        try:
            completion = interpreter.client.chat.completions.create(
                model=interpreter.model, messages=messages, tools=TOOL_SPECS, tool_choice="auto")
        except DomainError:
            raise
        except Exception:
            # Chi tiết SDK/network không bao giờ tới khách; caller rơi về graph cũ.
            raise DomainError("ai_unavailable", "Dịch vụ AI chưa sẵn sàng; vui lòng thử lại.", 503) from None
        usage = getattr(completion, "usage", None)
        usage_total["logical_calls"] += 1
        tokens = getattr(usage, "total_tokens", None)
        if tokens is None:
            usage_total["saw_none"] = True
        else:
            usage_total["tokens"] += int(tokens)
        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            messages.append({"role": "assistant", "content": message.content,
                             "tool_calls": [{"id": call.id, "type": "function",
                                             "function": {"name": call.function.name,
                                                          "arguments": call.function.arguments}}
                                            for call in tool_calls]})
            for call in tool_calls:
                name = call.function.name
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = None
                if not isinstance(arguments, dict) or name not in tools or name not in TOOL_NAMES:
                    result = {"error": "tool_unavailable",
                              "message": "Tool không có trong bộ được cấp hoặc tham số không phải JSON hợp lệ."}
                else:
                    try:
                        result = toolbox.call(tools[name]["agent"], name, tools[name]["fn"], **arguments)
                    except DomainError as error:
                        result = {"error": error.code, "message": str(error)}
                    except (TypeError, ValidationError) as error:
                        result = {"error": "invalid_arguments", "message": str(error)[:300]}
                payload = json.dumps(_strip_income(result), ensure_ascii=False, default=str)
                tool_payloads.append(payload)
                detail = (result.get("note") or result.get("message")
                          if isinstance(result, dict) and result.get("error") is None
                          else (f"lỗi {result.get('error')}" if isinstance(result, dict) and result.get("error")
                                else name))
                if isinstance(result, dict) and result.get("error"):
                    detail = f"lỗi {result['error']}: {result.get('message', '')}"[:160]
                elif isinstance(result, dict) and name == "find_place" and result.get("found"):
                    detail = f"điểm mốc {result.get('label')} ({result.get('city')})"
                elif isinstance(result, dict) and "count" in result:
                    detail = f"{result['count']} căn khớp"
                elif isinstance(result, dict) and result.get("saved"):
                    detail = "đã ghi nháp: " + ", ".join(result.get("fields") or [])
                steps.append({"tool": name, "detail": str(detail)[:160]})
                if emit is not None:
                    emit({"name": name, "kind": "tool", "detail": str(detail)[:160]})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})
                if name == "ask_user" and isinstance(result, dict) and result.get("error") is None:
                    question = result.get("question") or ""
                    questions = [question] + [f"Lựa chọn: {option}" for option in result.get("options", [])]
                    response_dict = finalize(question, questions)
            if response_dict is not None:
                break
            continue
        answer = (message.content or "").strip()
        if answer:
            response_dict = finalize(check_numbers(answer, text, tool_payloads), None)
            break
    if response_dict is None:
        response_dict = finalize(SAFE_REPLY, None)
    service.interpreter.last_usage = {"logical_calls": usage_total["logical_calls"],
                                      "tokens": None if usage_total["saw_none"] else usage_total["tokens"]}
    provenance = stamp("interpreter", "agent_loop", interpreter_mode="openai",
                       agent_mode="loop", **toolbox.summary("needs"))
    return response_dict, provenance
