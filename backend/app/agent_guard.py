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
# 18/11 (đo live held-out K, 3/3 lần): "cho mình đi xem căn đầu tiên" không có
# "đặt lịch/hẹn xem" nên rơi vào vòng LLM. Động từ đi tới xem ("đi/qua/tới/ghé xem",
# "xem trực tiếp", "hẹn lịch/giờ") chỉ tính là đặt lịch xem khi câu nhắc MỘT CĂN
# cụ thể — "tìm phòng cuối tuần đi xem" chưa có căn nào thì vẫn là câu tìm phòng.
VIEWING_GO = re.compile(r"\b(?:di|qua|toi|den|ghe|sang)\s+(?:coi|xem)\b|\bxem truc tiep\b"
                        r"|\bhen (?:lich|gio|ngay)\b")
ROOM_DEICTIC = re.compile(r"căn\s*(?:này|đó|kia|ấy|nay\b|do\b)", re.I)


def mentions_specific_room(text: str) -> bool:
    return bool(ROOM_ORDINAL_NUMBER.search(text) or ROOM_ORDINAL_WORD.search(text)
                or ROOM_FIRST.search(text) or ROOM_LAST.search(text)
                or ROOM_DEICTIC.search(text) or mention_room_id(text))


def viewing_intent(text: str) -> bool:
    value = folded(text)
    if VIEWING_TRIGGER.search(value):
        return True
    return bool(VIEWING_GO.search(value)) and mentions_specific_room(text)


def room_reference(text: str) -> str | None:
    match = ROOM_REFERENCE.search(folded(text))
    return f"demo-{int(match.group(1)):02d}" if match else None


# Finance chat (AG-02): room ids a renter may name inside a simulate_finance
# utterance. Only ids in the currently approved shortlist are ever simulated.
FINANCE_ROOM_REFERENCE = re.compile(r"\b(?:synthetic-room-\d{3}|room-[0-9a-f]{10}|demo-\d{2})\b")


def finance_room_reference(text: str) -> str | None:
    match = FINANCE_ROOM_REFERENCE.search(folded(text))
    return match.group(0) if match else None


# AG-05: resolver tham chiếu căn — id đầy đủ (mọi nguồn: Chợ Tốt, synthetic,
# room-hash, demo), thứ tự trong danh sách ("căn số 2", "căn thứ hai", "căn
# đầu/cuối") hoặc tiêu đề rút gọn duy nhất. CHỈ trả id nằm trong visible_items
# của run hiện tại; câu không nhắc căn → None, không đoán.
ROOM_ID_PATTERNS = (re.compile(r"\b(chotot-\d+)\b", re.I),
                    re.compile(r"\b(synthetic-room-\d{1,3})\b", re.I),
                    re.compile(r"\b(room-[0-9a-f]{10})\b", re.I),
                    re.compile(r"\b(demo-\d{1,3})\b", re.I))
# 18/11 (probe live): câu trả lời gọi các căn là "Căn 1/2/3" nên khách nói lại đúng
# như vậy ("đặt lịch xem căn 1") — "số/thứ" là tuỳ chọn. Số theo sau là đơn vị
# ("căn 2 phòng ngủ", "căn 1 người", "căn 30m2", "căn 3 triệu") thì KHÔNG phải số
# thứ tự trong danh sách.
ROOM_ORDINAL_NUMBER = re.compile(
    r"căn\s*(?:số|thứ)?\s*(\d{1,2})(?!\d|[.,]\d|\s*(?:phòng|phong|pn\b|ngủ|người|nguoi|vợ|đứa"
    r"|m\b|m2|m²|mét|met\b|triệu|trieu|tr\b|củ|cu\b|k\b|nghìn|km\b|tầng|tang\b|xe\b|wc\b|toilet))", re.I)
ROOM_ORDINAL_WORDS = {"hai": 2, "ba": 3, "bốn": 4, "bon": 4, "năm": 5, "nam": 5, "một": 1, "mot": 1}
ROOM_ORDINAL_WORD = re.compile(r"căn\s*(?:thứ|thu|số)?\s*(hai|ba|bốn|bon|năm|nam|một|mot)\b", re.I)
ROOM_FIRST = re.compile(r"căn\s*(?:đầu|dầu|đầu tiên|first)", re.I)
ROOM_LAST = re.compile(r"căn\s*(?:cuối|cuối cùng|last)", re.I)


def mention_room_id(text: str) -> str | None:
    """Token dạng mã phòng trong câu (bất kể có trong danh sách hay không) —
    dùng để phân biệt 'không nhắc căn' với 'nhắc căn ngoài kết quả hiện tại'."""
    for pattern in ROOM_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def resolve_room_reference(text: str, visible_items: list) -> str | None:
    """Câu nói → room_id trong danh sách đang hiển thị, hoặc None."""
    ids = [item.get("room_id") for item in visible_items if item.get("room_id")]
    if not ids:
        return None
    value = folded(text)
    for pattern in ROOM_ID_PATTERNS:
        match = pattern.search(text)
        if match and match.group(1) in ids:
            return match.group(1)
    ordinal = ROOM_ORDINAL_NUMBER.search(text)
    if ordinal:
        index = int(ordinal.group(1)) - 1
        return ids[index] if 0 <= index < len(ids) else None
    word = ROOM_ORDINAL_WORD.search(text)
    if word:
        position = ROOM_ORDINAL_WORDS[word.group(1).lower()]
        return ids[position - 1] if position <= len(ids) else None
    if ROOM_FIRST.search(text):
        return ids[0]
    if ROOM_LAST.search(text):
        return ids[-1]
    matches = []
    for room_id, item in zip(ids, visible_items):
        title = folded((item.get("title") or "").split(". ")[0])
        if len(title) >= 6 and title in value:
            matches.append(room_id)
    return matches[0] if len(matches) == 1 else None


# 18/11 (đo live held-out K): model gửi room_ref dạng trần ("3", "thứ ba", "đầu
# tiên", "phòng 2", "#1") nên resolver theo câu khách ("căn …") không nhận ra và
# model quay sang hỏi khách "mã căn". room_ref của model được chuẩn hóa về
# "căn <phần còn lại>" rồi resolve như câu khách — vẫn chỉ trả id trong danh sách.
_MODEL_REF_PREFIX = re.compile(r"^\s*(?:căn|can|phòng|phong|room|#)\s*", re.I)


def resolve_model_room_ref(ref: str, visible_items: list) -> str | None:
    found = resolve_room_reference(ref, visible_items)
    if found is not None:
        return found
    bare = _MODEL_REF_PREFIX.sub("", ref).strip().lstrip("#").strip()
    return resolve_room_reference(f"căn {bare}", visible_items) if bare else None


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


def viewing_prep_missing_room_reply(has_results: bool = True) -> dict:
    """18/11: mã phòng không còn hiện cho khách (Lỗi 2c 15/11) nên câu hỏi lại dùng
    số thứ tự trong danh sách gợi ý — đúng cách câu trả lời gọi các căn."""
    if not has_results:
        return {"intent": "find_room", "status": "needs_clarification",
                "questions": ["Bạn cho mình biết khu vực và mức tiền muốn tìm nhé?"],
                "message": "Bạn chưa có danh sách gợi ý nào nên mình chưa đặt lịch xem được. "
                           "Mình tìm phòng trước, rồi bạn chọn căn muốn xem trong danh sách."}
    return {"intent": "find_room", "status": "needs_clarification",
            "questions": ["Bạn muốn đặt lịch xem căn nào? Nói số thứ tự trong danh sách gợi ý, "
                          "ví dụ “xem căn 1”."],
            "message": "Mình chưa rõ bạn muốn xem căn nào trong danh sách gợi ý."}
