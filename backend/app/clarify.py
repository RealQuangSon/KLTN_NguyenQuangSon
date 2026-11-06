"""AG-11 lớp 2 — dựng lựa chọn làm rõ từ kho thật (code tất định).

Mỗi cách hiểu được áp lên hồ sơ tạm và chạy `catalog.match` (không ghi gì) để
gắn số căn/giá thật; loại cách hiểu ra 0 căn (trừ khi tất cả đều 0). Mức ảnh
hưởng = 1 − Jaccard(top 5 giữa các cách hiểu); < 0,2 thì không hỏi. Không số
nào ngoài kết quả tool; không tự nới điều kiện cứng — chip chỉ là lựa chọn.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations

from .models import DraftProfile, Profile

# Ngưỡng hiệu chỉnh theo PLAN.md AG-11 (chỉnh lại trên gold khi có nhãn người).
IMPACT_THRESHOLD = 0.2
CHIP_KEYS = ("id", "label", "detail", "probability", "patch", "count", "min_monthly_total_vnd", "decided_by")
FIELD_ALIASES = {"destination": "destination_radius", "budget": "budget_scope"}
FIELD_PRIORITY = ("destination_radius", "budget_scope", "area", "room_type", "people")


def canonical_field(field: str) -> str:
    return FIELD_ALIASES.get(field, field)


class _DraftSession(dict):
    """Session-like tối giản cho service._profile_from_draft (chỉ đọc nháp/hồ sơ)."""

    def __init__(self, draft: DraftProfile, profile_json: str | None):
        super().__init__(draft_json=draft.model_dump_json(), profile_json=profile_json)


def _match_top(service, profile: Profile) -> tuple[list[str], int, int | None]:
    # rank trả toàn tập đủ điều kiện; match chỉ trả top 5 nên không dùng để đếm.
    items, _ = service.catalog.rank(profile, service.matching_method)
    monthly = [item.cost.monthly_total_vnd for item in items if item.cost.monthly_total_vnd is not None]
    return ([item.room_id for item in items[:5]], len(items), min(monthly) if monthly else None)


def _resolved(draft: DraftProfile, field: str) -> bool:
    tracked = "destination" if field == "destination_radius" else field
    return (draft.field_status.get(tracked) == "confirmed"
            or draft.evidence_ref.get(tracked, "").startswith("clarify:"))


def _interpretations(draft: DraftProfile, service=None,
                     base_profile_json: str | None = None, *, profile: Profile | None = None,
                     field: str | None = None) -> list[dict]:
    """Các điểm mơ hồ khả dĩ của nháp hiện tại (không bịa giá trị ngoài dữ liệu)."""
    out: list[dict] = []
    requested = canonical_field(field) if field else None

    def wants(name: str) -> bool:
        return (requested is None or requested == name) and not _resolved(draft, name)

    if wants("destination_radius") and draft.destination:
        out.append({"field": "destination_radius", "kind": "radius", "radius_m": 2000,
                    "label": "Gần điểm đến · bán kính 2 km"})
        out.append({"field": "destination_radius", "kind": "radius", "radius_m": 5000,
                    "label": "Gần điểm đến · bán kính 5 km"})
    if wants("budget_scope") and draft.budget_hint_vnd and draft.budget_scope is None:
        out.append({"field": "budget_scope", "kind": "total_cap",
                    "label": "Trần TỔNG THÁNG (gồm phí)", "scope": "total"})
        out.append({"field": "budget_scope", "kind": "rent_cap",
                    "label": "Chỉ trần tiền THUÊ", "scope": "rent"})
    confirmed = Profile.model_validate_json(base_profile_json) if base_profile_json else None
    if wants("area") and not draft.area and not (confirmed and confirmed.area) and service is not None:
        if profile is None:
            profile = service._profile_from_draft("__clarify__", session_row=_DraftSession(draft, base_profile_json))
        if profile is not None:
            # Giữ trần tiền, điểm đến và mọi điều kiện khác; chỉ đếm khu vực có
            # ứng viên thật, không lấy các quận đông tin nhưng không đủ điều kiện.
            items, _ = service.catalog.rank(profile, service.matching_method)
            counts = Counter(item.area for item in items if item.area)
            areas = sorted(counts, key=lambda area: (-counts[area], area))[:3]
            out.extend({"field": "area", "kind": "area", "value": area, "label": area} for area in areas)
    if wants("room_type") and not draft.room_type and confirmed is None:
        labels = {"room": "Phòng trọ", "studio": "Studio", "apartment": "Căn hộ"}
        out.extend({"field": "room_type", "kind": "room_type", "value": value, "label": label}
                   for value, label in labels.items())
    if wants("people") and draft.people is None and confirmed is None:
        out.extend({"field": "people", "kind": "people", "value": people, "label": f"Ở {people} người"}
                   for people in (1, 2, 3))
    return out


def _temp_profile(service, draft: DraftProfile, interpretation: dict,
                  base_profile_json: str | None, *, profile: Profile | None = None) -> Profile | None:
    if profile is None:
        profile = service._profile_from_draft("__clarify__", session_row=_DraftSession(draft, base_profile_json))
    if profile is None:
        return None
    updates: dict = {}
    hint = draft.budget_hint_vnd
    field = canonical_field(interpretation["field"])
    if field == "budget_scope" and hint:
        if interpretation["scope"] == "rent":
            updates["max_rent_vnd"] = hint
            if base_profile_json is None:
                # Chưa có hồ sơ xác nhận: trần tổng giữ mức hint (thận trọng, không bịa hệ số).
                updates["max_monthly_cost_vnd"] = hint
        else:
            updates["max_monthly_cost_vnd"] = hint
            # Đổi cách hiểu không tự xóa trần thuê đã xác nhận trên hồ sơ gốc.
    if field == "destination_radius" and profile.destination:
        updates["destination"] = profile.destination.model_copy(
            update={"max_distance_m": interpretation["radius_m"]})
    if field == "area":
        updates["area"] = interpretation["value"]
    if field == "room_type":
        updates["room_type"] = interpretation["value"]
    if field == "people":
        updates["scenario"] = profile.scenario.model_copy(update={"people": interpretation["value"]})
    return profile.model_copy(update=updates) if updates else profile


def _impact(options: list[dict]) -> float:
    """So các cặp trong cùng trường; hai tập rỗng không tạo khác biệt giả."""
    impacts = []
    for first, second in combinations(options, 2):
        left, right = set(first["top"]), set(second["top"])
        union = left | right
        impacts.append(1 - len(left & right) / len(union) if union else 0.0)
    return max(impacts, default=0.0)


def build_clarification(service, session_id: str, field: str | None = None) -> dict | None:
    """Mỗi lần chỉ hỏi một trường; ưu tiên bán kính rồi cách hiểu trần tiền."""
    draft = service._draft(session_id)
    session = service.repo.session(session_id)
    base_profile_json = session["profile_json"]
    profile = service._profile_from_draft("__clarify__", session_row=_DraftSession(draft, base_profile_json))
    if profile is None:
        return None
    requested = canonical_field(field) if field else None
    for group_field in FIELD_PRIORITY:
        if requested is not None and requested != group_field:
            continue
        interpretations = _interpretations(draft, service, base_profile_json, profile=profile, field=group_field)
        options = []
        for index, interpretation in enumerate(interpretations):
            temporary = _temp_profile(service, draft, interpretation, base_profile_json, profile=profile)
            if temporary is None:
                continue
            top, count, min_monthly = _match_top(service, temporary)
            options.append({"id": f"opt-{index}", "field": group_field,
                            "kind": interpretation["kind"], "label": interpretation["label"],
                            "interpretation": interpretation, "top": top, "count": count,
                            "min_monthly_total_vnd": min_monthly})
        kept = [option for option in options if option["count"] > 0] or options
        impact = _impact(kept)
        if len(kept) < 2 or impact < IMPACT_THRESHOLD:
            continue
        total = sum(option["count"] for option in kept) or 1
        for option in kept:
            option["probability"] = round(option["count"] / total, 4)
        return {"field": group_field, "impact": round(impact, 4), "options": kept}
    return None


QUESTION_TEMPLATES = {
    "budget_scope": "Mức tiền bạn nêu hiểu thế nào cho đúng?",
    "destination_radius": "Bạn muốn ở gần điểm đến trong bán kính nào?",
    "area": "Bạn muốn ưu tiên khu vực nào trong các khu đang có căn khớp?",
    "room_type": "Bạn muốn tìm loại chỗ ở nào?",
    "people": "Bạn dự định ở mấy người?",
}


def question_for(field: str) -> str:
    return QUESTION_TEMPLATES.get(canonical_field(field), "Bạn muốn hiểu theo cách nào?")


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
    field = canonical_field(interpretation["field"])
    if field == "budget_scope":
        return {"set": {"budget_scope": interpretation["scope"]}}
    if field == "destination_radius":
        return {"set": {"destination_radius_m": interpretation["radius_m"]}}
    if field in {"area", "room_type", "people"}:
        return {"set": {field: interpretation["value"]}}
    return {"set": {}}


def to_dto(clarification: dict, decided_by: str) -> dict:
    field = canonical_field(clarification["field"])
    return {"id": f"clarify-{field}",
            "field": field,
            "question": question_for(clarification["field"]),
            "options": [{"id": option["id"], "label": option_label(option),
                         "detail": option["label"], "probability": option["probability"],
                         "count": option["count"], "min_monthly_total_vnd": option.get("min_monthly_total_vnd"),
                         "decided_by": decided_by,
                         "patch": option_patch(option)}
                        for option in clarification["options"]],
            "decided_by": decided_by}


def best_option(clarification: dict) -> dict:
    return max(clarification["options"], key=lambda option: option["count"])
