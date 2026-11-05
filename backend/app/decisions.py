"""AG-11 lớp 3 — Jev quyết định khi nào hỏi (OpenRouter Decisions API) + đường lui.

`HOMEMATCH_DECISION_MODE=jev` → gọi `typesafe/jev-1.14` (một endpoint alpha,
một nhà cung cấp → bắt buộc có đường lui). Jev lỗi/timeout/HTTP ≠ 200 → luật
trên xác suất `count` của lớp 2, ghi `decided_by="fallback"`, không chặn lượt.
"""
from __future__ import annotations

import json
import os

AUTO_THRESHOLD = 0.80
ASK_THRESHOLD = 0.40
DECISION_MODEL = os.getenv("HOMEMATCH_DECISION_MODEL", "typesafe/jev-1.14")
DECISION_TIMEOUT_S = 2.0


def _jev_payload(clarification: dict, context: dict) -> dict:
    """Request Jev: state đã qua redact (không tiền tuyệt đối, SĐT, email,
    thu nhập — caller chịu trách nhiệm, ở đây chỉ kiểm lại miền giá trị)."""
    state = json.dumps(context, ensure_ascii=False)
    for banned in ("monthly_income_vnd", "@", "090", "091", "092", "093",
                   "032", "035", "038", "039", "070", "083", "zalo.me"):
        if banned in state:
            raise ValueError(f"context carries banned token: {banned}")
    return {"model": DECISION_MODEL,
            "state": state,
            "questions": [{"id": "clarify", "type": "choice",
                           "criteria": [{"id": option["id"], "label": option["label"]}
                                        for option in clarification["options"]]}]}


def _rules(clarification: dict) -> tuple[str, dict | None]:
    """Luật không Jev: xác suất từ tỷ lệ số căn (lớp 2)."""
    options = clarification["options"]
    best = max(options, key=lambda option: option["probability"])
    if best["probability"] >= AUTO_THRESHOLD:
        return "accept", best
    if best["probability"] >= ASK_THRESHOLD:
        return "ask", best
    return "ask", best  # dưới ngưỡng: hỏi câu mở kèm 2 chip phổ biến nhất


def decide(clarification: dict, context: dict, *, client=None,
           mode: str | None = None) -> tuple[str, dict | None, str, str | None]:
    """Trả (quyết định, phương án, decided_by, mã lỗi nếu có).

    Quyết định: "accept" (áp phương án tốt nhất, nói rõ giả định),
    "ask" (hỏi lại kèm chip), "open" (hỏi câu mở kèm 2 chip).
    """
    mode = mode or os.getenv("HOMEMATCH_DECISION_MODE", "rules")
    if mode != "jev":
        decision, best = _rules(clarification)
        return decision, best, "rules", None
    try:
        if client is None:
            import httpx
            api_key = os.getenv("OPENAI_API_KEY", "")
            client = httpx.Client(timeout=DECISION_TIMEOUT_S)
            response = client.post(
                "https://openrouter.ai/api/alpha/decisions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=_jev_payload(clarification, context))
        else:
            response = client.post(
                "https://openrouter.ai/api/alpha/decisions",
                json=_jev_payload(clarification, context))
        if response.status_code != 200:
            raise RuntimeError(f"jev_http_{response.status_code}")
        data = response.json()
        answer = (data.get("answers") or [{}])[0]
        chosen = answer.get("choice_id")
        probability = float(answer.get("probability") or 0.0)
        options = {option["id"]: option for option in clarification["options"]}
        best = options.get(chosen)
        if best is None:
            raise RuntimeError("jev_unknown_choice")
        if probability >= AUTO_THRESHOLD:
            return "accept", best, "jev", None
        return "ask", best, "jev", None
    except Exception as error:  # mọi lỗi → luật dự phòng, không chặn lượt chat
        decision, best = _rules(clarification)
        return decision, best, "fallback", type(error).__name__
