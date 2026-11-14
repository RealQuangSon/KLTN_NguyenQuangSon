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
CHIP_KEYS = ("id", "label", "detail", "probability", "patch", "count", "min_monthly_total_vnd",
             "decided_by", "action", "text")
# HN-13.2: city (thiếu thành phố) và budget_cap (chưa có mức tiền) đứng trước —
# dựng được KHÔNG cần hồ sơ có trần; destination là điểm mốc thật thay quận.
# HN-13.2: alias "budget" giữ nguyên nghĩa budget_scope (cách hiểu mức tiền ĐÃ
# có — test cũ phụ thuộc); bỏ alias "destination"→destination_radius vì nó va
# chạm field mới "destination" (chip điểm mốc thật).
# HN-13.2: thứ tự TỰ HỎI giữ nguyên nhóm cũ (hiệu chỉnh gold HN-08 không bị phá);
# "destination" tự hỏi chỉ khi khách nói "gần" mà không nêu tên (needs_destination);
# "city"/"budget_cap" là phương án CUỐI khi thiếu thành phố/mức tiền (dựng được
# không cần trần). ask_user(field=...) vẫn tới được mọi nhóm trực tiếp.
FIELD_ALIASES = {"budget": "budget_scope"}
FIELD_PRIORITY = ("destination_radius", "budget_scope", "destination", "area",
                  "room_type", "people", "city", "budget_cap")
# Các field chỉ khách được chọn (không tự chấp nhận hộ khách — khách chưa nói gì).
ASK_ONLY_FIELDS = frozenset({"city", "budget_cap", "destination"})
# Bán kính mặc định cho "gần điểm mốc" (đúng mặc định destination của update_needs).
DESTINATION_RADIUS_M = 3000


def canonical_field(field: str) -> str:
    return FIELD_ALIASES.get(field, field)


class _DraftSession(dict):
    """Session-like tối giản cho service._profile_from_draft (chỉ đọc nháp/hồ sơ)."""

    def __init__(self, draft: DraftProfile, profile_json: str | None):
        super().__init__(draft_json=draft.model_dump_json(), profile_json=profile_json)


def _match_top(service, profile: Profile) -> tuple[list[str], int, int | None, int]:
    # rank trả toàn tập đủ điều kiện; match chỉ trả top 5 nên không dùng để đếm.
    items, diagnostics = service.catalog.rank(profile, service.matching_method)
    monthly = [item.cost.monthly_total_vnd for item in items if item.cost.monthly_total_vnd is not None]
    # HN-13.2: căn bị GIỮ chờ xác minh (thiếu phí/sức chứa) không nằm trong items —
    # nhãn chip phải nói thật để khách không bấm vào rồi thấy 0 căn.
    held = sum(diagnostics.get("verification", {}).values())
    return ([item.room_id for item in items[:5]], len(items),
            min(monthly) if monthly else None, held)


# Profile bắt buộc trần tiền >0; khi đếm chip TRƯỚC khi có mức tiền, giá trị
# này chỉ có nghĩa "KHÔNG lọc theo tiền" (không loại căn nào) — không bao giờ
# được ghi vào nháp, hiển thị hay hiểu là một mức tiền thật.
NO_BUDGET_FILTER_VND = 10 ** 12


def _moneyless_profile(service, draft: DraftProfile, base_profile_json: str | None) -> Profile | None:
    """Hồ sơ KHÔNG lọc tiền để đếm chip: thành phố là tối thiểu; dùng cùng bộ
    scenario mặc định với service._profile_from_draft. Trần tiền là sentinel
    không-lọc (xem NO_BUDGET_FILTER_VND) — không phải mức tiền giả đề xuất."""
    from .models import Scenario
    confirmed = Profile.model_validate_json(base_profile_json) if base_profile_json else None
    scenario = Scenario(people=draft.people or 1, vehicles=1, electricity_kwh="140",
                        water_m3="3", moving_vnd=300_000, setup_vnd=200_000)
    if confirmed:
        updates: dict = {}
        if draft.area and draft.evidence_ref.get("area"):
            updates["area"] = draft.area
        if draft.room_type and draft.evidence_ref.get("room_type"):
            updates["room_type"] = draft.room_type
        if draft.people and draft.evidence_ref.get("people"):
            updates["scenario"] = confirmed.scenario.model_copy(update={"people": draft.people})
        return confirmed.model_copy(update=updates) if updates else confirmed
    if not draft.city:
        return None
    return Profile(city=draft.city, area=draft.area or None, max_monthly_cost_vnd=NO_BUDGET_FILTER_VND,
                   room_type=draft.room_type or "room", scenario=scenario,
                   preferences=list(draft.preferences))


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
    confirmed = Profile.model_validate_json(base_profile_json) if base_profile_json else None

    def wants(name: str) -> bool:
        return (requested is None or requested == name) and not _resolved(draft, name)

    # HN-13.2 — city: thiếu thành phố thì hỏi trước, chip là thành phố đang có căn.
    if wants("city") and not draft.city and not (confirmed and confirmed.city) and service is not None:
        counts = Counter(room.city for room in service.catalog.rooms()
                         if room.published and room.city)
        for city, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append({"field": "city", "kind": "city", "value": city,
                        "label": f"Ở {city}", "count": count})
    # HN-13.2 — budget_cap: chưa có mức tiền; mức gợi ý lấy từ phân bố KHO THẬT,
    # không tạo trần giả. Đủ dữ liệu phí → tổng tháng; thiếu → giá thuê và ghi
    # rõ "Tiền thuê", không bao giờ gọi giá thuê là tổng chi phí.
    if (wants("budget_cap") and not draft.budget_hint_vnd
            and not (confirmed and confirmed.max_monthly_cost_vnd) and service is not None):
        out.extend(_budget_cap_interpretations(service, draft, base_profile_json, confirmed))
    if wants("destination_radius") and draft.destination:
        # Gồm cả mức đang TẠM dùng để khách giữ nguyên được (HN-13.2).
        current_radius = int(draft.destination.max_distance_m)
        for radius_m in sorted({2000, 5000, current_radius}):
            out.append({"field": "destination_radius", "kind": "radius", "radius_m": radius_m,
                        "label": f"Trong {radius_m / 1000:g} km"})
    if wants("budget_scope") and draft.budget_hint_vnd and draft.budget_scope is None:
        out.append({"field": "budget_scope", "kind": "total_cap",
                    "label": "Trần TỔNG THÁNG (gồm phí)", "scope": "total"})
        out.append({"field": "budget_scope", "kind": "rent_cap",
                    "label": "Chỉ trần tiền THUÊ", "scope": "rent"})
    # HN-13.2 — destination: chip là ĐIỂM MỐC THẬT trong danh mục theo thành phố
    # nháp, chỉ lấy nơi có căn; chip CHỮ gửi "gần <điểm mốc>" (find_place tra được).
    if (wants("destination") and draft.needs_destination and not draft.destination
            and not draft.area and not (confirmed and confirmed.area) and service is not None):
        out.extend(_destination_interpretations(service, draft, base_profile_json, confirmed))
    # Có điểm đến thì không hỏi khu vực: điểm đến đã là tín hiệu khu vực, hỏi
    # thêm quận là nhiễu (gold CL11/CL33 — HN-08).
    if (wants("area") and not draft.area and not (confirmed and confirmed.area)
            and not draft.destination and service is not None):
        if profile is None:
            # Đếm tác động giữ cách hiểu cũ (scope chưa nêu = trần tổng) để hiệu chỉnh
            # hỏi/không hỏi không đổi; hồ sơ thật dùng mặc định tiền thuê (UX-01).
            profile = service._profile_from_draft("__clarify__", session_row=_DraftSession(draft, base_profile_json),
                                                  legacy_caps=True)
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


def _budget_cap_interpretations(service, draft: DraftProfile,
                                base_profile_json: str | None, confirmed: Profile | None) -> list[dict]:
    """Mức ngân sách gợi ý từ phân bố KHO THẬT (một lần rank, không rank lại từng
    mức): đủ ≥5 căn có tổng tháng → mức tổng tháng; không → giá thuê và nhãn nói
    rõ "Tiền thuê" (không bao giờ gọi giá thuê là tổng chi phí). Trả chip CHỮ —
    bấm là gửi câu đó, tiền được đọc tất định từ câu."""
    city = draft.city or (confirmed.city if confirmed else None)
    if not city:
        return []
    draft_no_money = draft.model_copy(update={"budget_hint_vnd": None})
    profile = _moneyless_profile(service, draft_no_money, base_profile_json)
    if profile is None:
        return []
    # HN-13.3: trên kho crawl phần lớn tin bị GIỮ vì thiếu phí/sức chứa — đếm từ
    # pool CHẤP NHẬN ước tính (đó là những tin khách sẽ thấy khi đồng ý) và nói
    # thật trên nhãn; không bao giờ hiển thị 0 căn khi vẫn còn tin khớp.
    # HN-13.3.1: cùng định nghĩa held với search_rooms/confirm — helper chung.
    held = 0  # D-12: không còn tin bị giữ; mọi tin khớp đều hiện kèm nhãn.
    items, _ = service.catalog.rank(profile, service.matching_method)
    monthly_known = sorted(item.cost.monthly_total_vnd for item in items
                           if item.cost.monthly_total_vnd is not None)
    options: list[dict] = []
    if len(monthly_known) >= 5:
        # Mức trần tại các phân vị, làm tròn XUỐNG 500 nghìn cho dễ đọc.
        for share in (0.4, 0.7, 0.9):
            level = max(500_000, int(monthly_known[min(len(monthly_known) - 1, int(len(monthly_known) * share))] // 500_000) * 500_000)
            count = sum(1 for value in monthly_known if value <= level)
            money = f"{level // 1_000_000:g} triệu" if level % 1_000_000 == 0 else f"{level / 1_000_000:g} triệu"
            options.append({"field": "budget_cap", "kind": "budget_cap", "value": level,
                            "scope": "total", "label": f"Tổng tháng dưới {money}",
                            "action": "text", "text": f"Tổng tháng dưới {money}",
                            "count": count, "held": held})
    else:
        rooms_by_id = {room.id: room for room in service.catalog.rooms()}
        rents = sorted(rooms_by_id[item.room_id].quote.rent_vnd for item in items
                       if rooms_by_id.get(item.room_id) is not None
                       and rooms_by_id[item.room_id].quote.rent_vnd is not None)  # pool ước tính
        if len(rents) < 5:
            return []  # không đủ dữ liệu giá → không bịa mức tiền
        for share in (0.4, 0.7, 0.9):
            level = max(500_000, int(rents[min(len(rents) - 1, int(len(rents) * share))] // 500_000) * 500_000)
            count = sum(1 for value in rents if value <= level)
            money = f"{level // 1_000_000:g} triệu" if level % 1_000_000 == 0 else f"{level / 1_000_000:g} triệu"
            options.append({"field": "budget_cap", "kind": "budget_cap", "value": level,
                            "scope": "rent", "label": f"Tiền thuê dưới {money}",
                            "action": "text", "text": f"Tiền thuê dưới {money}",
                            "count": count, "held": held})
    return options


def _destination_interpretations(service, draft: DraftProfile,
                                 base_profile_json: str | None, confirmed: Profile | None) -> list[dict]:
    """Chip điểm mốc THẬT trong danh mục (places.json) theo thành phố nháp, chỉ
    lấy nơi có căn trong bán kính mặc định; một lần rank duy nhất, đếm khoảng
    cách thuần toán (không truy vấn thêm)."""
    from .catalog import distance_m as _distance_m
    from .locations import _PLACES
    from .models import Destination
    city = draft.city or (confirmed.city if confirmed else None)
    if not city:
        return []
    draft_no_money = draft.model_copy(update={"budget_hint_vnd": None})
    profile = _moneyless_profile(service, draft_no_money, base_profile_json)
    if profile is None:
        return []
    # D-12: mọi tin khớp (kể cả thiếu phí/sức chứa) đều hiện kèm nhãn nên đếm thẳng từ rank.
    items, _ = service.catalog.rank(profile, service.matching_method)
    dest_held = 0
    rooms_by_id = {room.id: room for room in service.catalog.rooms()}
    counts: dict[str, int] = {}
    for place in _PLACES:
        if place.get("city") != city:
            continue
        anchor = Destination(label=place["names"][0], latitude=place["latitude"],
                             longitude=place["longitude"], uncertainty_m=place.get("uncertainty_m", 0),
                             max_distance_m=DESTINATION_RADIUS_M)
        count = sum(1 for item in items
                    if rooms_by_id.get(item.room_id) is not None
                    and _distance_m(rooms_by_id[item.room_id], anchor) is not None
                    and _distance_m(rooms_by_id[item.room_id], anchor) <= DESTINATION_RADIUS_M)
        if count:
            counts[place["names"][0]] = count
    return [{"field": "destination", "kind": "destination", "value": name,
             "label": f"Gần {name}", "action": "text", "text": f"gần {name}",
             "count": count, "held": dest_held}
            for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]]


def _temp_profile(service, draft: DraftProfile, interpretation: dict,
                  base_profile_json: str | None, *, profile: Profile | None = None) -> Profile | None:
    if profile is None:
        profile = service._profile_from_draft("__clarify__", session_row=_DraftSession(draft, base_profile_json),
                                              legacy_caps=True)
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
    if field == "city":
        updates["city"] = interpretation["value"]
    if field == "budget_cap":
        # Chip budget_cap là chip CHỮ (tiền đọc tất định từ câu gửi đi) — hồ sơ
        # tạm chỉ dùng khi cần đếm lại, đặt trần tạm theo mức của chip.
        if interpretation.get("scope") == "rent":
            updates["max_rent_vnd"] = interpretation["value"]
        else:
            updates["max_monthly_cost_vnd"] = interpretation["value"]
    if field == "room_type":
        updates["room_type"] = interpretation["value"]
    if field == "people":
        updates["scenario"] = profile.scenario.model_copy(update={"people": interpretation["value"]})
    return profile.model_copy(update=updates) if updates else profile


def _impact(options: list[dict]) -> float:
    """So các cặp trong cùng trường. Hai tín hiệu: (1) Jaccard top-5 — lựa chọn
    đổi kết quả thấy ngay; (2) chênh SỐ CĂN — "2 km có 3 căn, 5 km có 20 căn"
    vẫn đáng hỏi dù top-5 trùng. Hiệu chỉnh theo gold clarify_cases (HN-08):
    nhóm yes có chênh 6–21 căn, nhóm low_impact gần bằng nhau. Hai tập rỗng
    không tạo khác biệt giả."""
    impacts = []
    for first, second in combinations(options, 2):
        left, right = set(first["top"]), set(second["top"])
        union = left | right
        top_impact = 1 - len(left & right) / len(union) if union else 0.0
        counts = (first.get("count", 0), second.get("count", 0))
        if max(counts) > 0:
            count_impact = 1 - min(counts) / max(counts)
        else:
            count_impact = 0.0
        impacts.append(max(top_impact, count_impact))
    return max(impacts, default=0.0)


def build_clarification(service, session_id: str, field: str | None = None) -> dict | None:
    """Mỗi lần chỉ hỏi một trường theo FIELD_PRIORITY. Nhóm city/budget_cap/
    destination dựng được KHI CHƯA có mức tiền (không tạo trần giả, không ghi
    nháp); nhóm còn lại cần hồ sơ từ nháp như trước."""
    draft = service._draft(session_id)
    session = service.repo.session(session_id)
    base_profile_json = session["profile_json"]
    requested = canonical_field(field) if field else None
    for group_field in FIELD_PRIORITY:
        if requested is not None and requested != group_field:
            continue
        interpretations = _interpretations(draft, service, base_profile_json, field=group_field)
        options = []
        for index, interpretation in enumerate(interpretations):
            if "count" in interpretation:
                # Nhóm tự đếm lúc dựng (city/budget_cap/destination) — một lần
                # rank cho cả nhóm, không rank lại từng chip.
                options.append({"id": f"opt-{index}", "field": group_field,
                                "kind": interpretation["kind"], "label": interpretation["label"],
                                "interpretation": interpretation, "top": [],
                                "count": interpretation["count"],
                                "min_monthly_total_vnd": None,
                                "action": interpretation.get("action", "patch"),
                                "text": interpretation.get("text"),
                                "held": interpretation.get("held", 0)})
                continue
            temporary = _temp_profile(service, draft, interpretation, base_profile_json)
            if temporary is None:
                continue
            top, count, min_monthly, held = _match_top(service, temporary)
            options.append({"id": f"opt-{index}", "field": group_field,
                            "kind": interpretation["kind"], "label": interpretation["label"],
                            "interpretation": interpretation, "top": top, "count": count,
                            "min_monthly_total_vnd": min_monthly, "held": held})
        kept = [option for option in options if option["count"] > 0]
        if not kept:
            kept = options
        elif len(kept) < len(options):
            # Giữ cả lựa chọn 0 căn khi có lựa chọn dương: "2 km · 0 căn" vs
            # "5 km · 5 căn" là thông tin người dùng cần để chọn (HN-08 gold).
            kept = options
        impact = _impact(kept)
        # HN-13.2: field ASK_ONLY (city/budget_cap/destination) là LỰA CHỌN rời
        # rạc khách phải tự chọn (chọn gì thì kết quả khác hẳn), không phải cách
        # hiểu của một câu khách đã nói — không dùng ngưỡng impact chặn.
        if len(kept) < 2 or (group_field not in ASK_ONLY_FIELDS and impact < IMPACT_THRESHOLD):
            continue
        total = sum(option["count"] for option in kept) or 1
        for option in kept:
            option["probability"] = round(option["count"] / total, 4)
        if group_field == "destination_radius":
            # "Gần" mặc định là gần nhất: chip bán kính xếp gần-trước (HN-08 gold
            # preferred=radius_2000); xác suất vẫn hiển thị trên từng chip.
            kept = sorted(kept, key=lambda option: option["interpretation"]["radius_m"])
        return {"field": group_field, "impact": round(impact, 4), "options": kept}
    return None


QUESTION_TEMPLATES = {
    "budget_cap": "Bạn muốn chi bao nhiêu mỗi tháng?",
    "city": "Bạn muốn thuê tại thành phố nào?",
    "destination": "Bạn muốn ở gần đâu?",
    "budget_scope": "Mức tiền bạn nêu hiểu thế nào cho đúng?",
    "destination_radius": "Bạn muốn ở gần điểm đến trong bán kính nào?",
    "area": "Bạn muốn ưu tiên khu vực nào trong các khu đang có căn khớp?",
    "room_type": "Bạn muốn tìm loại chỗ ở nào?",
    "people": "Bạn dự định ở mấy người?",
}


def question_for(field: str) -> str:
    return QUESTION_TEMPLATES.get(canonical_field(field), "Bạn muốn hiểu theo cách nào?")


def option_label(option: dict) -> str:
    """Nhãn chip tự nhiên: "Trong 2 km (1 căn, từ 3.230.000 ₫)"; khi có căn bị
    giữ chờ xác minh thì nói thật "kèm nhãn ước tính" (không để khách bấm vào
    thấy 0 căn) — đếm từ pool ước tính nên N là số căn khách sẽ thấy."""
    label = option["label"]
    if option.get("min_monthly_total_vnd") is not None:
        money = f"{option['min_monthly_total_vnd']:,}".replace(",", ".")
        label += f" ({option['count']} căn, từ {money} ₫)"
    else:
        label += f" ({option['count']} căn)"
    return label


def option_patch(option: dict) -> dict:
    """Patch có cấu trúc cho chip — mọi giá trị do code tính từ lựa chọn; khách
    bấm mới áp, server ghi `confirmed` với evidence `clarify:rN`. Chip CHỮ
    (action="text") không có patch: bấm là GỬI CÂU đó (tiền đọc tất định)."""
    if option.get("action") == "text":
        return {"set": {}}
    interpretation = option["interpretation"]
    field = canonical_field(interpretation["field"])
    if field == "budget_scope":
        return {"set": {"budget_scope": interpretation["scope"]}}
    if field == "destination_radius":
        return {"set": {"destination_radius_m": interpretation["radius_m"]}}
    if field in {"area", "room_type", "people", "city"}:
        return {"set": {field: interpretation["value"]}}
    return {"set": {}}


def assumption_sentence(option: dict) -> str:
    """Giả định diễn đạt thành CÂU NGƯỜI ĐỌC (HN-13.2) — không phải nhãn chip
    có số căn/khoảng giá ("Phòng trọ · 14 căn · từ 2.525.000 ₫" là nhãn chip)."""
    interpretation = option.get("interpretation") or {}
    field = canonical_field(interpretation.get("field") or option.get("field") or "")
    if field == "destination_radius":
        return f"Tạm dùng bán kính {interpretation['radius_m'] / 1000:g} km quanh điểm đến"
    if field == "budget_scope":
        return ("Tạm hiểu mức tiền bạn nêu là trần TỔNG THÁNG" if interpretation.get("scope") == "total"
                else "Tạm hiểu mức tiền bạn nêu là trần tiền THUÊ")
    if field == "area":
        return f"Tạm tìm ở {interpretation['value']}"
    if field == "room_type":
        return {"room": "Tạm tìm phòng trọ", "studio": "Tạm tìm studio",
                "apartment": "Tạm tìm căn hộ"}.get(interpretation.get("value"), "Tạm tìm phòng trọ")
    if field == "people":
        return f"Tạm hiểu bạn ở {interpretation['value']} người"
    if field == "city":
        return f"Tạm tìm tại {interpretation['value']}"
    return ""


def to_dto(clarification: dict, decided_by: str, *,
           question: str | None = None, reason: str | None = None,
           question_source: str | None = None) -> dict:
    field = canonical_field(clarification["field"])
    return {"id": f"clarify-{field}",
            "field": field,
            "question": question or question_for(clarification["field"]),
            "reason": reason,
            "question_source": question_source or "catalog",
            "options": [{"id": option["id"], "label": option_label(option),
                         "detail": option["label"], "probability": option["probability"],
                         "count": option["count"], "min_monthly_total_vnd": option.get("min_monthly_total_vnd"),
                         "decided_by": decided_by,
                         "action": option.get("action") or "patch",
                         "text": option.get("text"),
                         "patch": option_patch(option)}
                        for option in clarification["options"]],
            "decided_by": decided_by}


def state_chips(service, session_id: str) -> list[str]:
    """Chip trạng thái khi CHƯA có câu hỏi đang chờ và chưa có kết quả (HN-13.2):
    điểm mốc thật trong danh mục + mức tiền từ phân bố kho — tối đa 4, đều là
    câu khách gửi được ngay (tiền được đọc tất định từ câu, không tự nới cứng).
    Không có dữ liệu giá → không đưa chip tiền thay vì bịa."""
    draft = service._draft(session_id)
    session = service.repo.session(session_id)
    base_profile_json = session["profile_json"]
    confirmed = Profile.model_validate_json(base_profile_json) if base_profile_json else None
    chips: list[str] = []
    if not draft.city and not (confirmed and confirmed.city):
        # Thiếu thành phố: hỏi thành phố trước, chip là thành phố đang có căn.
        from collections import Counter
        counts = Counter(room.city for room in service.catalog.rooms()
                         if room.published and room.city)
        chips.extend(f"Thuê ở {city}" for city, _ in sorted(counts.items(), key=lambda kv: -kv[1]))
        return chips[:4]
    for interpretation in _destination_interpretations(service, draft, base_profile_json, confirmed)[:2]:
        chips.append(interpretation["text"])
    for interpretation in _budget_cap_interpretations(service, draft, base_profile_json, confirmed)[:2]:
        chips.append(interpretation["text"])
    return chips[:4]


def best_option(clarification: dict) -> dict:
    return max(clarification["options"], key=lambda option: option["count"])
