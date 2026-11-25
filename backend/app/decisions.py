"""AG-11 lớp 3 — Jev quyết định khi nào hỏi (OpenRouter Decisions API) + đường lui.

`HOMEMATCH_DECISION_MODE=jev` → gọi `typesafe/jev-1.14` (một endpoint alpha,
một nhà cung cấp → bắt buộc có đường lui). Jev lỗi/timeout/HTTP ≠ 200 → luật
trên xác suất `count` của lớp 2, ghi `decided_by="fallback"`, không chặn lượt.
"""
from __future__ import annotations

import math
import os
import re

from .agent_guard import redact
from .models import redact_destination

# HN-08 hiệu chỉnh theo gold clarify_cases: 0,80 làm CL01 (4 vs 17 căn,
# p=0,81) tự áp 5 km thay vì hỏi — gold mong hỏi; hạ còn 0,85.
AUTO_THRESHOLD = 0.85
ASK_THRESHOLD = 0.40
DECISION_MODEL = os.getenv("HOMEMATCH_DECISION_MODEL", "typesafe/jev-1.14")
DECISION_TIMEOUT_S = 2.0
_INCOME_TEXT = re.compile(r"(?:thu\s*nhập|thu\s*nhap|\bincome\b)\s*[:=]?[^\n;!?]*", re.I)
_SYMBOL_MONEY = re.compile(r"\b\d[\d.,]*(?:\s*\d{3})*\s*(?:₫|đ\b|usd\b)|\$\s*\d[\d.,]*", re.I)


def _decision_text(text: str) -> str:
    value = redact(text)
    value = _INCOME_TEXT.sub("[THONG_TIN_RIENG_DA_TACH]", value)
    value = re.sub(r"monthly_income_vnd|housing_ratio", "[THONG_TIN_RIENG_DA_TACH]", value, flags=re.I)
    return _SYMBOL_MONEY.sub("[TIEN_DA_TACH]", value)


def decision_context(value):
    """Ranh giới Jev độc lập caller: không giữ tiền, khoản vay hay thu nhập;
    tọa độ điểm neo từ thiết bị của khách cũng bỏ ngay tại đây (state
    gửi Jev gồm input analyst và chip, đều đi qua hàm này), chỉ còn nhãn/nguồn/
    bán kính."""
    return _context_tree(redact_destination(value))


def _context_tree(value):
    if isinstance(value, dict):
        return {_decision_text(str(key)): _context_tree(item) for key, item in value.items()
                if not (str(key).lower().endswith("_vnd") or "income" in str(key).lower()
                        or "loan" in str(key).lower() or str(key).lower() == "housing_ratio")}
    if isinstance(value, (list, tuple)):
        return [_context_tree(item) for item in value]
    if isinstance(value, str):
        return _decision_text(value)
    return value


def jev_post(payload: dict, timeout_s: float = DECISION_TIMEOUT_S) -> dict:
    """POST Decisions API tách riêng để dùng chung (input analyst có timeout riêng).

    Caller tự bọc cassette/breaker; lỗi HTTP ≠ 200 ném RuntimeError với mã
    jev_http_<status> để đường lui đọc được."""
    import httpx
    api_key = os.getenv("OPENAI_API_KEY", "")
    owned = httpx.Client(timeout=timeout_s)
    try:
        response = owned.post(
            "https://openrouter.ai/api/alpha/decisions",
            headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"jev_http_{response.status_code}")
        return response.json()
    finally:
        try:
            owned.close()
        except Exception:
            pass  # lỗi đóng kết nối không được che mất kết quả


def _jev_payload(clarification: dict, context: dict) -> dict:
    """Request Jev theo Decisions API: `state` là object, `questions` khóa theo
    tên, câu `choice` có `criteria` = {id phương án: mô tả}. Mọi văn bản đi
    qua redact; tiền, khoản vay và thu nhập bị bỏ đệ quy ngay tại ranh giới."""
    from .clarify import question_for
    options = clarification["options"]
    if not options:
        raise ValueError("jev_no_options")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", str(option["id"]))
           or redact(str(option["id"])) != str(option["id"]) for option in options):
        raise ValueError("jev_invalid_option_id")
    return {"model": DECISION_MODEL,
            "state": decision_context(context),
            "questions": {"clarify": {
                "type": "choice",
                "instructions": "Dựa trên hội thoại và nhu cầu nháp trong state, khách nhiều khả năng "
                                f"chọn phương án nào cho câu hỏi: {question_for(clarification.get('field', ''))}",
                "criteria": {option["id"]: _decision_text(option["label"]) for option in options}}}}


def _rules(clarification: dict) -> tuple[str, dict | None]:
    """Luật không Jev: xác suất từ tỷ lệ số căn (lớp 2). Bán kính điểm đến
    KHÔNG tự áp theo số căn (HN-08 gold CL01-10): 5 km thường nhiều căn hơn
    nhưng "gần" nghĩa là gần nhất — xác suất số căn đo mật độ kho, không phải
    ý định; chỉ Jev mới đủ cơ sở để tự áp bán kính."""
    options = clarification["options"]
    if not options:
        return "ask", None
    best = max(options, key=lambda option: option["probability"])
    if (best["probability"] >= AUTO_THRESHOLD
            and clarification.get("field") != "destination_radius"):
        return "accept", best
    if best["probability"] >= ASK_THRESHOLD:
        return "ask", best
    return "ask", best  # dưới ngưỡng: hỏi câu mở kèm 2 chip phổ biến nhất


def decide(clarification: dict, context: dict, *, client=None,
           mode: str | None = None) -> tuple[str, dict | None, str, str | None]:
    """Trả (quyết định, phương án, decided_by, mã lỗi nếu có).

    Quyết định: "accept" (áp phương án tốt nhất, nói rõ giả định),
    "ask" (hỏi lại kèm chip), "open" (hỏi câu mở kèm 2 chip).

    chip "Dùng vị trí hiện tại" (kind=device_location) không có count
    nên không tham gia quyết định — không đưa vào criteria của Jev, không vào
    luật xác suất, không bao giờ được tự chọn thay khách; sau quyết định chip
    vẫn đứng đầu danh sách của DTO."""
    mode = mode or os.getenv("HOMEMATCH_DECISION_MODE", "rules")
    device_options = [option for option in clarification["options"]
                      if option.get("kind") == "device_location"]
    clarification["options"] = [option for option in clarification["options"]
                                if option.get("kind") != "device_location"]
    try:
        if mode != "jev":
            decision, best = _rules(clarification)
            return decision, best, "rules", None
        try:
            from .agent_cassette import jev_call
            from . import provider_breaker
            # HN-09: cassette ghi/phát lại Jev; payload đã qua decision_context/redact.
            if client is None:
                # HN-07: breaker — 5 lỗi liên tiếp → bỏ qua provider Jev 120 s (dùng luật).
                # Chỉ đếm trên đường provider thật (client ngoài là test/đường nhánh riêng).
                if provider_breaker.open_("jev"):
                    raise RuntimeError("jev_circuit_open")
                try:
                    answer = (jev_call(_jev_payload(clarification, context),
                                       lambda payload: jev_post(payload, DECISION_TIMEOUT_S))
                              .get("answers") or {}).get("clarify") or {}
                    provider_breaker.record("jev", True)
                except Exception:
                    provider_breaker.record("jev", False)
                    raise
            else:
                response = client.post(
                    "https://openrouter.ai/alpha/decisions",
                    json=_jev_payload(clarification, context))
                if response.status_code != 200:
                    raise RuntimeError(f"jev_http_{response.status_code}")
                answer = (response.json().get("answers") or {}).get("clarify") or {}
            probabilities = answer.get("probabilities") or {}
            options = {option["id"]: option for option in clarification["options"]}
            best = options.get(answer.get("choice"))
            if best is None or not isinstance(probabilities, dict) or not probabilities:
                raise RuntimeError("jev_unknown_choice")
            # Kiểm toàn bộ trước khi ghi: response hỏng không được làm lệch luật dự phòng.
            if set(probabilities) != set(options):
                raise ValueError("jev_missing_probability")
            if any(isinstance(value, bool) for value in probabilities.values()):
                raise ValueError("jev_invalid_probability")
            parsed = {key: float(probabilities[key]) for key in options}
            if not all(math.isfinite(p) and 0 <= p <= 1 for p in parsed.values()):
                raise ValueError("jev_invalid_probability")
            if not math.isclose(sum(parsed.values()), 1.0, abs_tol=0.02):
                raise ValueError("jev_invalid_probability_total")
            # Chip xếp theo xác suất của Jev (cao nhất đứng đầu).
            for option in clarification["options"]:
                option["probability"] = round(parsed[option["id"]], 4)
            clarification["options"].sort(key=lambda option: -option["probability"])
            if best["probability"] >= AUTO_THRESHOLD:
                return "accept", best, "jev", None
            return "ask", best, "jev", None
        except Exception as error:  # mọi lỗi → luật dự phòng, không chặn lượt chat
            decision, best = _rules(clarification)
            return decision, best, "fallback", type(error).__name__
    finally:
        clarification["options"] = device_options + clarification["options"]
