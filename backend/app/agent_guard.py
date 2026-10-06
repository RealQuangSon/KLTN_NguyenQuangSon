"""Deterministic guardrails for the agent chat path: prompt-injection screening,
PII hygiene and the provider error taxonomy.

Everything here is best-effort, offline and deterministic. A flagged message is
quarantined (the assistant path is skipped and the draft is left untouched); the
patterns are never treated as instructions the agent obeys. `redact_tree` is the
single boundary for anything written to traces, diagnostics, grounding payloads
or checkpoints that is not the raw session draft.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .interpreter import folded, redact
from .models import DomainError

# Patterns run on folded (diacritic-stripped) text. Tuned to avoid the ordinary
# interview vocabulary; bare money/contact mentions are PII, not injection.
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("ignore_instructions", re.compile(
        r"bo qua (?:tat ca |cac )?(?:huong dan|chi dan|lenh|kiem duyet|quy trinh)"
        r"|ignore (?:all |any )?(?:previous|prior|above|earlier) ?instructions"
        r"|disregard (?:all |any )?(?:previous |prior |above )?.{0,24}instructions"
        r"|quen (?:het )?huong dan", re.I)),
    ("role_override", re.compile(
        r"tu nay ban la|ban la (?:mot )?(?:quan ly|admin|quan tri|he thong|system)"
        r"|dong vai (?:thanh )?(?:quan ly|admin|he thong)"
        r"|act as(?: an| a)? (?:admin|manager|system)|pretend to be(?: a| an)? (?:admin|manager|system)"
        r"|you are now(?: a| an)? (?:admin|manager|system)", re.I)),
    ("prompt_probe", re.compile(
        r"system prompt|huong dan he thong|prompt (?:cua )?(?:ban|he thong|noi bo)"
        r"|reveal (?:your )?prompt|leak (?:the )?prompt", re.I)),
    ("privilege_escalation", re.compile(
        r"\bcap (?:quyen|vai tro|admin|quan ly)"
        r"|\btu (?:duyet|cap quyen|ky duyet)|\bduyet (?:tat ca|toan bo|ho|giup)(?:\s|$)"
        r"|approve (?:all|everything)(?:\s|$)|grant (?:me )?(?:admin|manager|role)"
        r"|bypass (?:all )?(?:checks?|permissions?|approval)", re.I)),
    ("tool_invocation", re.compile(
        r"(?:chay|goi|thuc thi) (?:lenh|tool|cong cu|sql|cau truy van)"
        r"|run (?:the )?(?:command|tool|sql)|execute (?:sql|command)"
        r"|drop table|delete from|union select", re.I)),
    ("secret_probe", re.compile(
        r"api[_ ]?keys?|mat khau|password|passphrase|secret(?: key)?"
        r"|token (?:truy cap|cua)|(?:access )?credentials?", re.I)),
)


@dataclass
class InjectionScan:
    flagged: bool
    patterns: list[str] = field(default_factory=list)


def screen_injection(text: str) -> InjectionScan:
    """Flag instruction-injection signatures in user text. Output names only —
    the raw text is never copied into the scan result."""
    value = folded(text)
    hits = [name for name, pattern in INJECTION_PATTERNS if pattern.search(value)]
    return InjectionScan(flagged=bool(hits), patterns=hits)


def redact_tree(value: Any) -> Any:
    """Deep-redact money/phone/email in nested payloads (dict/list/str) before
    they reach traces, diagnostics, grounding payloads or checkpoints."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_tree(item) for item in value]
    return value


# Chat-triggered viewing preparation: deterministic phrase + room reference.
VIEWING_TRIGGER = re.compile(r"dat lich|hen xem")
ROOM_REFERENCE = re.compile(r"\bdemo[- ]?(\d{1,3})\b")


def viewing_intent(text: str) -> bool:
    return bool(VIEWING_TRIGGER.search(folded(text)))


def room_reference(text: str) -> str | None:
    match = ROOM_REFERENCE.search(folded(text))
    return f"demo-{int(match.group(1)):02d}" if match else None


# Provider failures keep their taxonomy codes. At the chat boundary they turn
# into this deterministic guided-form fallback; nothing is ever fabricated to
# replace the missing extraction. Budget exhaustion (budget_exceeded) is always
# raised as DomainError, never converted into a chat reply.
PROVIDER_FALLBACK_CODES = frozenset({"ai_unavailable", "context_limit"})


def provider_fallback_reply(code: str) -> dict:
    """Guided-form fallback response. The taxonomy code stays visible in the
    questions so the failure is never masked as a successful turn."""
    return {"intent": "unknown", "status": "needs_clarification",
            "questions": [f"Trợ lý AI tạm chưa xử lý được tin nhắn này (mã: {code}). "
                          "Vui lòng nhập nhu cầu qua biểu mẫu hoặc thử lại sau."],
            "message": "Không có kết quả thay thế nào được tạo khi dịch vụ AI lỗi."}


def quarantine_reply(scan: InjectionScan) -> dict:
    """Quarantined turn: the assistant path is skipped, the draft is untouched."""
    return {"intent": "unknown", "status": "needs_clarification",
            "questions": ["Tin nhắn có dấu hiệu chứa chỉ đạo nhúng (prompt injection) "
                          "nên được cách ly khỏi trợ lý AI. Vui lòng nhập nhu cầu thật qua biểu mẫu."],
            "message": "Tin nhắn đã được cách ly; hồ sơ nháp không đổi."}


def viewing_prep_missing_room_reply() -> dict:
    return {"intent": "find_room", "status": "needs_clarification",
            "questions": ["Bạn muốn đặt lịch xem phòng nào? Cho biết mã phòng trong "
                          "bản gợi ý đã duyệt (ví dụ demo-01)."],
            "message": "Chưa chuẩn bị được yêu cầu lịch xem vì chưa có mã phòng."}
