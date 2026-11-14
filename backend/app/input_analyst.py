"""Phân tích đầu vào bằng Jev trước khi định tuyến sang agent chuyên trách.

Một request Decisions API với hai câu choice: `route` (needs | finance |
ranking | other) và `clarity` (clear = luật lọc trực tiếp được | reason = mơ
hồ, nhu cầu ngầm, địa danh, cần suy luận). Jev chỉ trả đáp án có kiểu kèm xác
suất, không viết câu chữ.

State gửi đi chỉ gồm tin nhắn và nháp đã qua `decision_context`/`_decision_text`
kèm pha phiên và việc đã có kết quả hay chưa — tuyệt đối không tiền, thu nhập,
khoản vay. Jev lỗi/timeout/breaker mở/xác suất dưới ngưỡng → luật dự phòng,
không chặn lượt (`decided_by="fallback"`). Chạy duy nhất trong nhánh
OpenAIInterpreter; demo mode không gọi Jev.

Cấu hình: `HOMEMATCH_INPUT_ANALYST=jev|rules|off`. `off` giữ nguyên hành vi một
vòng lặp (không gọi Jev, không bàn giao xếp hạng); mặc định khi không đặt là
`rules`.
"""
from __future__ import annotations

import math
import os
import re

from .decisions import DECISION_MODEL, decision_context, jev_post
from .interpreter import fixed_intent, folded

ANALYST_TIMEOUT_S = 3.0  # chip làm rõ giữ 2 s (decisions.py); một lần đo Jev 1,31 s
CONFIDENCE = 0.6
ROUTES = ("needs", "finance", "ranking", "other")
CLARITY_STATES = ("clear", "reason")

# Luật dự phòng cho route: câu hỏi so sánh/xếp hạng các căn đã gợi ý (đối chiếu
# trên văn bản bỏ dấu); chỉ áp khi phiên đã có kết quả để xếp hạng.
RANKING_HINT = re.compile(
    r"can nao|phong nao|nha nao|dang tien|so sanh|so sao|xep hang|hang dau|thu tu"
    r"|vi sao|tai sao|dung tren|dung dau|tot hon|re hon|cao hon|thap hon|chenh"
    r"|re nhat|dat nhat|tot nhat|nen chon|chon nao|danh gia|uom? diem", re.I)

# Chi tiết emit cho giao diện: không văn bản thô, không tiền, chỉ nhãn route.
_ROUTE_DETAIL = {
    "needs": "Phân tích tin nhắn: chuyển sang agent nhu cầu",
    "finance": "Phân tích tin nhắn: chuyển sang agent tài chính",
    "ranking": "Phân tích tin nhắn: chuyển sang agent xếp hạng",
    "other": "Phân tích tin nhắn: agent nhu cầu đảm nhận",
}


def analyst_mode() -> str:
    """`HOMEMATCH_INPUT_ANALYST` (jev|rules|off); mặc định rules; giá trị lạ → rules."""
    value = (os.getenv("HOMEMATCH_INPUT_ANALYST", "rules") or "rules").strip().lower()
    return value if value in {"jev", "rules", "off"} else "rules"


def enabled() -> bool:
    """False khi `off`: giữ nguyên hành vi một vòng lặp (test cũ, cassette không đổi)."""
    return analyst_mode() != "off"


def rules_route(text: str, has_results: bool) -> str:
    """Luật dự phòng: fixed_intent + mẫu nhận diện câu hỏi về các căn đã gợi ý."""
    if fixed_intent(text) in {"simulate_finance", "calculate_cost"}:
        return "finance"
    if has_results and RANKING_HINT.search(folded(text)):
        return "ranking"
    return "needs"


def _state(service, session: dict, text: str, *, has_results: bool, phase: str) -> dict:
    """State gửi Jev: tin nhắn + nháp qua decision_context (bỏ *_vnd/income/loan,
    che tiền trong chuỗi), kèm pha, cờ đã có kết quả và CÂU HỎI ĐANG CHỜ (HN-13.2)
    — khách đang trả lời câu hỏi nhu cầu thì route phải là needs. Không trường
    tiền nào; mất pending sau restart chỉ là thiếu ngữ cảnh, không lỗi."""
    draft = service._draft(session["id"]).model_dump(mode="json")
    pending = (getattr(service, "_pending_clarification", {}) or {}).get(session["id"]) or {}
    return decision_context({"message": text, "draft": draft,
                             "phase": phase, "has_results": has_results,
                             "pending_question": pending.get("question"),
                             "pending_field": pending.get("field")})


def _payload(state: dict) -> dict:
    return {"model": DECISION_MODEL, "state": state, "questions": {
        "route": {"type": "choice",
                  "instructions": "Tin nhắn khách cần agent chuyên trách nào xử lý? "
                                  "Nếu khách đang trả lời câu hỏi đang chờ (pending_question "
                                  "trong state) thì đó là needs.",
                  "criteria": {
                      "needs": "Tìm phòng, chốt/làm rõ nhu cầu, trả lời câu hỏi đang chờ, "
                               "hỏi tiện ích, mở hội thoại chủ nhà",
                      "finance": "Chi phí, khả năng chi trả, vay/trả góp cho các căn đang có",
                      "ranking": "So sánh, giải thích thứ hạng, vì sao căn đứng trên trong kết quả đã có",
                      "other": "Cẩm nang, hỗ trợ người thật hoặc chuyện khác ngoài ba việc trên"}},
        "clarity": {"type": "choice",
                    "instructions": "Tin nhắn đã đủ rõ để luật lọc trực tiếp chưa?",
                    "criteria": {
                        "clear": "Rõ thành phố/khu, mức tiền, loại phòng — luật lọc trực tiếp được",
                        "reason": "Mơ hồ, nhu cầu ngầm, nhắc địa danh (gần trường), cần suy luận"}}}}


def _answer(response: dict, question: str, options: tuple[str, ...]) -> dict:
    """Kiểm một đáp án choice như decide(): choice hợp lệ, xác suất hữu hạn trong
    [0,1] đủ mọi phương án, tổng xấp xỉ 1. Sai định dạng → ném, caller đi luật."""
    answer = ((response.get("answers") or {}).get(question) or {})
    probabilities = answer.get("probabilities") or {}
    choice = answer.get("choice")
    if choice not in options or not isinstance(probabilities, dict) \
            or set(probabilities) != set(options):
        raise ValueError(f"jev_invalid_{question}")
    if any(isinstance(value, bool) for value in probabilities.values()):
        raise ValueError(f"jev_invalid_{question}")
    parsed = {key: float(probabilities[key]) for key in options}
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in parsed.values()):
        raise ValueError(f"jev_invalid_{question}")
    if not math.isclose(sum(parsed.values()), 1.0, abs_tol=0.02):
        raise ValueError(f"jev_invalid_{question}_total")
    return {"choice": str(choice), "probabilities": parsed}


def _budget_exhausted(service, session_id: str) -> bool:
    """Phiên hết lượt hoặc vượt trần chi phí thì không đốt thêm tiền cho Jev."""
    budget = service.budget
    return budget.used(session_id) >= budget.turn_limit \
        or budget.spent_usd(session_id) > budget.cost_cap_usd


def analyze(service, session: dict, text: str, *, has_results: bool, phase: str,
            mode: str | None = None, client=None, emit=None) -> dict:
    """Trả {"route", "clarity", "decided_by"} — không văn bản thô, không tiền.

    - mode `rules`: luật ngay, `decided_by="rules"`, clarity luôn "clear"
      (không phát sinh lượt gọi LLM khi không phân tích được).
    - mode `jev`: Jev trả lời được → xác suất quyết định; route dưới 0,6 → luật;
      p(clear) dưới 0,6 → "reason". Jev lỗi/breaker mở/hết ngân sách phiên → luật,
      `decided_by="fallback"`, clarity "clear".
    Chi phí `usage.cost` của Jev được cộng vào trần chi phí phiên."""
    session_id = session["id"]
    mode = mode or analyst_mode()
    if mode == "off":
        mode = "rules"
    decided_by = "rules"
    error_name: str | None = None
    route = rules_route(text, has_results)
    clarity = "clear"
    if mode == "jev" and not _budget_exhausted(service, session_id):
        state = _state(service, session, text, has_results=has_results, phase=phase)
        try:
            from .agent_cassette import jev_call
            from . import provider_breaker
            if client is None:
                # HN-07: breaker chung với chip làm rõ — 5 lỗi liên tiếp → luật.
                if provider_breaker.open_("jev"):
                    raise RuntimeError("jev_circuit_open")
                try:
                    response = jev_call(_payload(state),
                                        lambda payload: jev_post(payload, ANALYST_TIMEOUT_S))
                    provider_breaker.record("jev", True)
                except Exception:
                    provider_breaker.record("jev", False)
                    raise
            else:
                response = client.post("https://openrouter.ai/api/alpha/decisions",
                                       json=_payload(state))
                if response.status_code != 200:
                    raise RuntimeError(f"jev_http_{response.status_code}")
                response = response.json()
            # Chi phí provider báo (OpenRouter usage.cost) cộng vào trần phiên.
            service.budget.record_cost(session_id, (response.get("usage") or {}).get("cost"))
            route_answer = _answer(response, "route", ROUTES)
            clarity_answer = _answer(response, "clarity", CLARITY_STATES)
            decided_by = "jev"
            route = route_answer["choice"]
            if route_answer["probabilities"][route] < CONFIDENCE:
                route = rules_route(text, has_results)
                decided_by = "fallback"
            clarity = "clear" if clarity_answer["probabilities"]["clear"] >= CONFIDENCE else "reason"
        except Exception as error:  # mọi lỗi → luật dự phòng, không chặn lượt chat
            route = rules_route(text, has_results)
            clarity = "clear"
            decided_by = "fallback"
            error_name = type(error).__name__
    analysis = {"route": route, "clarity": clarity, "decided_by": decided_by}
    summary = (f"route={route}; clarity={clarity}; decided_by={decided_by}"
               + (f"; lỗi provider={error_name}" if error_name else ""))
    service._record_step("decision", "input_analyst", True, summary)
    if emit is not None:
        detail = _ROUTE_DETAIL[route]
        if decided_by == "fallback":
            detail += " (Jev không dùng được — dùng luật)"
        elif decided_by == "rules" and mode == "rules":
            detail += " (luật)"
        emit({"name": "route", "kind": "router", "detail": detail})
    return analysis
