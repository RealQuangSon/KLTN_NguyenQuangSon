"""AG-11 lớp 2 — dựng lựa chọn làm rõ từ kho thật (code tất định).

Mỗi cách hiểu được áp lên hồ sơ tạm và chạy `catalog.match` (không ghi gì) để
gắn số căn/giá thật; loại cách hiểu ra 0 căn (trừ khi tất cả đều 0). Mức ảnh
hưởng = 1 − Jaccard(top 5 giữa các cách hiểu); < 0,2 thì không hỏi. Không số
nào ngoài kết quả tool; không tự nới điều kiện cứng — chip chỉ là lựa chọn.
"""
from __future__ import annotations

from .models import DraftProfile, Profile

# Ngưỡng hiệu chỉnh theo PLAN.md AG-11 (chỉnh lại trên gold khi có nhãn người).
IMPACT_THRESHOLD = 0.2
CHIP_KEYS = ("id", "label", "detail", "probability", "patch")


class _DraftSession(dict):
    """Session-like tối giản cho service._profile_from_draft (chỉ đọc nháp/hồ sơ)."""

    def __init__(self, draft: DraftProfile, profile_json: str | None):
        super().__init__(draft_json=draft.model_dump_json(), profile_json=profile_json)


def _match_top(service, profile: Profile) -> tuple[list[str], int, int | None]:
    items, _ = service.catalog.match(profile, service.matching_method)
    monthly = [item.cost.monthly_total_vnd for item in items if item.cost.monthly_total_vnd is not None]
    return ([item.room_id for item in items[:5]], len(items), min(monthly) if monthly else None)


def _interpretations(draft: DraftProfile) -> list[dict]:
    """Các điểm mơ hồ khả dĩ của nháp hiện tại (không bịa giá trị ngoài dữ liệu)."""
    out: list[dict] = []
    if draft.budget_hint_vnd:
        out.append({"field": "budget", "kind": "total_cap",
                    "label": "Trần TỔNG THÁNG (gồm phí)", "scope": "total"})
        out.append({"field": "budget", "kind": "rent_cap",
                    "label": "Chỉ trần tiền THUÊ", "scope": "rent"})
    if draft.destination:
        out.append({"field": "destination", "kind": "radius", "radius_m": 2000,
                    "label": "Gần điểm đến · bán kính 2 km", "scope": None})
        out.append({"field": "destination", "kind": "radius", "radius_m": 5000,
                    "label": "Gần điểm đến · bán kính 5 km", "scope": None})
    return out


def _temp_profile(service, draft: DraftProfile, interpretation: dict,
                  base_profile_json: str | None) -> Profile | None:
    profile = service._profile_from_draft("__clarify__", session_row=_DraftSession(draft, base_profile_json))
    if profile is None:
        return None
    updates: dict = {}
    hint = draft.budget_hint_vnd
    if interpretation["field"] == "budget" and hint:
        if interpretation["scope"] == "rent":
            updates["max_rent_vnd"] = hint
            if base_profile_json is None:
                # Chưa có hồ sơ xác nhận: trần tổng giữ mức hint (thận trọng, không bịa hệ số).
                updates["max_monthly_cost_vnd"] = hint
        else:
            updates["max_monthly_cost_vnd"] = hint
            updates.pop("max_rent_vnd", None)
    if interpretation["field"] == "destination" and profile.destination:
        updates["destination"] = profile.destination.model_copy(
            update={"max_distance_m": interpretation["radius_m"]})
    return profile.model_copy(update=updates) if updates else profile


def build_clarification(service, session_id: str) -> dict | None:
    """Trả cấu trúc lựa chọn làm rõ, hoặc None khi không đáng hỏi."""
    draft = service._draft(session_id)
    interpretations = _interpretations(draft)
    if not interpretations:
        return None
    session = service.repo.session(session_id)
    base_profile_json = session["profile_json"]
    options = []
    for index, interpretation in enumerate(interpretations):
        profile = _temp_profile(service, draft, interpretation, base_profile_json)
        if profile is None:
            continue
        top, count, min_monthly = _match_top(service, profile)
        options.append({"id": f"opt-{index}", "field": interpretation["field"],
                        "kind": interpretation["kind"], "label": interpretation["label"],
                        "interpretation": interpretation, "top": top, "count": count,
                        "min_monthly_total_vnd": min_monthly})
    kept = [option for option in options if option["count"] > 0] or options
    if len(kept) < 2:
        return None
    first, second = kept[0], kept[1]
    union = len(set(first["top"]) | set(second["top"])) or 1
    impact = 1 - len(set(first["top"]) & set(second["top"])) / union
    if impact < IMPACT_THRESHOLD:
        return None
    total = sum(option["count"] for option in kept) or 1
    for option in kept:
        option["probability"] = round(option["count"] / total, 4)
    return {"field": first["field"], "impact": round(impact, 4), "options": kept}


QUESTION_TEMPLATES = {
    "budget": "Mức tiền bạn nêu hiểu thế nào cho đúng?",
    "destination": "Bạn muốn ở gần điểm đến trong bán kính nào?",
}


def question_for(field: str) -> str:
    return QUESTION_TEMPLATES.get(field, "Bạn muốn hiểu theo cách nào?")


def option_label(option: dict) -> str:
    label = option["label"]
    if option.get("min_monthly_total_vnd") is not None:
        money = f"{option['min_monthly_total_vnd']:,}".replace(",", ".")
        label += f" · {option['count']} căn · từ {money} ₫"
    else:
        label += f" · {option['count']} căn"
    return label


def option_patch(option: dict) -> dict:
    """Patch có cấu trúc cho chip — mọi giá trị do code tính từ lựa chọn; khách
    bấm mới áp, server ghi `confirmed` với evidence `clarify:rN`."""
    interpretation = option["interpretation"]
    if interpretation["field"] == "budget":
        return {"set": {"budget_scope": interpretation["scope"]}}
    if interpretation["field"] == "destination":
        return {"set": {"destination_radius_m": interpretation["radius_m"]}}
    return {"set": {}}


def to_dto(clarification: dict, decided_by: str) -> dict:
    return {"id": f"clarify-{clarification['field']}",
            "field": clarification["field"],
            "question": question_for(clarification["field"]),
            "options": [{"id": option["id"], "label": option_label(option),
                         "detail": option["label"], "probability": option["probability"],
                         "patch": option_patch(option)}
                        for option in clarification["options"]],
            "decided_by": decided_by}


def best_option(clarification: dict) -> dict:
    return max(clarification["options"], key=lambda option: option["count"])
