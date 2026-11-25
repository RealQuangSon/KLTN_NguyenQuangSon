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

# Ngưỡng hiệu chỉnh trên gold; chỉnh lại khi có nhãn người.
IMPACT_THRESHOLD = 0.2
CHIP_KEYS = ("id", "label", "detail", "probability", "patch", "count", "min_monthly_total_vnd",
             "decided_by", "action", "text", "kind")
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
# Lỗi 1/4 (15/11): budget_scope xếp SAU destination — trước đây nó đứng trước và
# (sau khi hai cách hiểu có số đếm trung thực) nhảy vào hỏi/tự chấp nhận trước
# câu hỏi điểm đến, làm mất chip "gần đâu?" của các câu "gần trường".
FIELD_PRIORITY = ("destination_radius", "destination", "budget_scope", "area",
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
    # 18/11: khách nêu LOẠI điểm đến ("gần trường") thì hỏi trường nào kể cả khi đã
    # có quận — chip là các trường có căn quanh đó; không nêu loại thì giữ luật cũ.
    # current/personal (chỗ của chính khách) chỉ hỏi điểm neo khi CHƯA có
    # khu vực nào — khách đã nêu quận thì tìm trong quận đó, câu hỏi điểm neo
    # không được chiếm lượt (đồng bộ blocking_destination).
    kind = draft.destination_kind
    kind_blocks = (not kind and not draft.area and not (confirmed and confirmed.area)) \
        or (kind in {"school", "hospital", "transit"}) \
        or (kind in {"current", "personal"} and not draft.area and not (confirmed and confirmed.area))
    if (wants("destination") and draft.needs_destination and not draft.destination
            and kind_blocks and service is not None):
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
    if wants("people") and draft.people is None and blocking_people(draft):
        # 18/11: khách đã nói ở chung → lựa chọn từ 2 người, khách phải tự chọn.
        out.extend({"field": "people", "kind": "people", "value": people, "label": f"Ở {people} người",
                    "ask_only": True}
                   for people in (2, 3, 4))
    elif wants("people") and draft.people is None and confirmed is None:
        out.extend({"field": "people", "kind": "people", "value": people, "label": f"Ở {people} người"}
                   for people in (1, 2, 3))
    return out


def blocking_people(draft: DraftProfile) -> bool:
    """Khách nói ở chung mà chưa nêu số người: chưa được tìm theo mặc định 1 người."""
    return bool(draft.needs_people and draft.people is None)


def blocking_destination(draft: DraftProfile, confirmed: Profile | None = None) -> bool:
    """Khách nói "gần trường/bệnh viện…" mà chưa nêu tên: hỏi nơi nào trước khi tìm.
    current/personal (chỗ của chính khách — "gần tôi", "công ty tôi") chỉ
    chặn khi chưa có cả điểm neo lẫn khu vực; khách đã nêu quận (trong nháp hoặc
    hồ sơ đã xác nhận `confirmed`) thì tìm trong quận đó, không chặn."""
    if not (draft.needs_destination and draft.destination_kind and not draft.destination):
        return False
    if draft.destination_kind in {"current", "personal"}:
        return not (draft.area or (confirmed and confirmed.area))
    return True


def blocking_field(service, session_id: str) -> str | None:
    """Trường khách đã nhắc nhưng chưa rõ và HỎI ĐƯỢC (kho dựng được nút): chưa tự
    tìm khi còn trường này. Không dựng được nút thì không chặn — tìm như cũ."""
    draft = service._draft(session_id)
    profile_json = service.repo.session(session_id)["profile_json"]
    confirmed = Profile.model_validate_json(profile_json) if profile_json else None
    for field, check in (("destination", lambda d: blocking_destination(d, confirmed)),
                         ("people", blocking_people)):
        if check(draft) and build_clarification(service, session_id, field=field) is not None:
            return field
    return None


def _budget_level_label(level: int) -> str:
    """Lỗi 3 (đo live 15/11 lần C): nhãn mức tiền kiểu Việt — dấu phẩy thập phân
    ("4,5 triệu" thay cho "4.5 triệu"). Chip là chip CHỮ: bấm là gửi câu `text`,
    tiền đọc tất định từ câu đó (budget_hint đọc được "4,5 triệu" = 4.500.000)."""
    if level % 1_000_000 == 0:
        return f"{level // 1_000_000:g} triệu"
    return f"{level / 1_000_000:g}".replace(".", ",") + " triệu"


def _budget_levels(pool: list[int]) -> list[int]:
    """Lỗi 3 (đo live 15/11 lần C): ba phân vị làm tròn XUỐNG 500 nghìn có thể ra
    cùng một mức (vague-no-city#2: hai chip "3 triệu" giống hệt) → bỏ mức trùng,
    giữ thứ tự tăng dần, mỗi mức một chip. Sau khi bỏ trùng còn < 2 mức thì bổ
    sung mức kế tiếp (+500 nghìn so với mức cao nhất, đếm lại số căn thật) tới
    tối đa 3 mức; mức bổ sung không tăng thêm căn so với mức trước thì bỏ qua."""
    levels: list[int] = []
    for share in (0.4, 0.7, 0.9):
        level = max(500_000, int(pool[min(len(pool) - 1, int(len(pool) * share))] // 500_000) * 500_000)
        if level not in levels:
            levels.append(level)
    if len(levels) >= 2 or sum(1 for value in pool if value <= levels[-1]) >= len(pool):
        return levels  # đủ 2 mức, hoặc mức cao nhất đã phủ hết pool → không còn căn mới
    cursor = levels[-1]
    while len(levels) < 3:
        cursor += 500_000
        if sum(1 for value in pool if value <= cursor) <= sum(1 for value in pool if value <= levels[-1]):
            continue
        levels.append(cursor)
        if sum(1 for value in pool if value <= cursor) >= len(pool):
            break  # mức vừa thêm đã phủ hết pool
    return levels


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
    # Việc nhỏ 15/11: nhãn phải khớp CƠ SỞ ĐẾM — tổng tháng biết chắc (tin ghi đủ
    # phí) ≥ 5 căn mới được gọi "Tổng tháng dưới X"; kho thiếu phí (tổng là ước
    # tính) phải dùng tiền thuê với nhãn "Tiền thuê dưới X" (quy ước: không bao
    # giờ gọi giá thuê là tổng chi phí). Trước đây nhánh "Tổng tháng" luôn thắng
    # vì tổng ước tính lấp đầy pool → chip "Tổng tháng dưới 3.5 triệu (332 căn)"
    # đếm theo tổng ước tính nhưng nghe như tổng chắc.
    exact_items = [item for item in items
                   if not any(str(code).startswith("fee_assumed")
                              for code in (item.verification or []))]
    monthly_known = sorted(item.cost.monthly_total_vnd for item in exact_items
                           if item.cost.monthly_total_vnd is not None)
    options: list[dict] = []
    if len(monthly_known) >= 5:
        options.extend({"field": "budget_cap", "kind": "budget_cap", "value": level,
                        "scope": "total",
                        "label": f"Tổng tháng dưới {_budget_level_label(level)}",
                        "action": "text", "text": f"Tổng tháng dưới {_budget_level_label(level)}",
                        "count": sum(1 for value in monthly_known if value <= level),
                        "held": held}
                       for level in _budget_levels(monthly_known))
    else:
        rooms_by_id = {room.id: room for room in service.catalog.rooms()}
        rents = sorted(rooms_by_id[item.room_id].quote.rent_vnd for item in items
                       if rooms_by_id.get(item.room_id) is not None
                       and rooms_by_id[item.room_id].quote.rent_vnd is not None)  # pool ước tính
        if len(rents) < 5:
            return []  # không đủ dữ liệu giá → không bịa mức tiền
        options.extend({"field": "budget_cap", "kind": "budget_cap", "value": level,
                        "scope": "rent",
                        "label": f"Tiền thuê dưới {_budget_level_label(level)}",
                        "action": "text", "text": f"Tiền thuê dưới {_budget_level_label(level)}",
                        "count": sum(1 for value in rents if value <= level),
                        "held": held}
                       for level in _budget_levels(rents))
    return options


def income_budget_options(service, session_id: str, levels: list[int]) -> list[dict]:
    """18/11: chip CHỮ "Tổng tháng dưới X" cho các mức tham khảo tính từ số tiền
    khách kiếm được (costs.income_housing_levels). Bấm là gửi câu đó — tiền đọc tất
    định như mọi chip budget_cap. Đã biết thành phố thì đếm căn có tổng tháng biết
    chắc ≤ X (cùng cơ sở đếm với _budget_cap_interpretations, bỏ mọi trần tiền cũ);
    chưa biết thì nhãn không kèm số căn — không đoán."""
    draft = service._draft(session_id)
    base_profile_json = service.repo.session(session_id)["profile_json"]
    confirmed = Profile.model_validate_json(base_profile_json) if base_profile_json else None
    monthly_known: list[int] | None = None
    if draft.city or (confirmed and confirmed.city):
        profile = _moneyless_profile(service, draft.model_copy(update={"budget_hint_vnd": None}),
                                     base_profile_json)
        if profile is not None:
            profile = profile.model_copy(update={
                "max_monthly_cost_vnd": NO_BUDGET_FILTER_VND, "max_rent_vnd": None, "min_rent_vnd": None,
                "max_initial_cash_vnd": None, "loan": None, "budget_approx": False,
                "prefer_cheapest": False})
            items, _ = service.catalog.rank(profile, service.matching_method)
            monthly_known = [item.cost.monthly_total_vnd for item in items
                             if item.cost.monthly_total_vnd is not None
                             and not any(str(code).startswith("fee_assumed")
                                         for code in (item.verification or []))]
    options = []
    for index, level in enumerate(dict.fromkeys(level for level in levels if level > 0)):
        text = f"Tổng tháng dưới {_budget_level_label(level)}"
        count = None if monthly_known is None else sum(1 for value in monthly_known if value <= level)
        options.append({"id": f"opt-{index}", "label": text if count is None else f"{text} ({count} căn)",
                        "detail": text, "probability": None, "count": count,
                        "min_monthly_total_vnd": None, "decided_by": "rules",
                        "action": "text", "text": text, "patch": {"set": {}}})
    return options


def _destination_interpretations(service, draft: DraftProfile,
                                 base_profile_json: str | None, confirmed: Profile | None) -> list[dict]:
    """Chip điểm mốc THẬT trong danh mục (places.json) theo thành phố nháp, chỉ
    lấy nơi có căn trong bán kính mặc định; một lần rank duy nhất, đếm khoảng
    cách thuần toán (không truy vấn thêm)."""
    from .catalog import distance_m as _distance_m
    from .locations import _PLACES, place_kind
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
        if draft.destination_kind and draft.destination_kind not in {"current", "personal"} \
                and place_kind(place) != draft.destination_kind:
            # 18/11: "gần trường" → chỉ các trường, không đưa trung tâm thương mại.
            # current/personal không lọc theo loại — lấy mọi địa danh trong
            # thành phố như khi không có loại (chỗ khách chưa nêu tên không biết loại).
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
        # Lỗi 1 (15/11): hai cách hiểu phải trung thực với cách đọc của chính nó —
        # "chỉ trần tiền thuê" KHÔNG thêm trần tổng (trước đây gán thêm max_monthly
        # = hint làm hai cách hiểu trùng số đếm → nhóm bị coi là ít ảnh hưởng →
        # confirm chạy với trần CHỈ-thuê và công bố căn vượt tổng tháng khách nêu);
        # "trần tổng tháng" bỏ trần thuê (một mức tiền chỉ thuộc một phạm vi —
        # cùng ngữ nghĩa với _profile_from_draft đã xác nhận).
        if interpretation["scope"] == "rent":
            updates["max_rent_vnd"] = hint
            updates["max_monthly_cost_vnd"] = None
            updates["min_rent_vnd"] = draft.budget_min_vnd
        else:
            updates["max_monthly_cost_vnd"] = hint
            updates["max_rent_vnd"] = None
            updates["min_rent_vnd"] = None
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
    confirmed_profile = Profile.model_validate_json(base_profile_json) if base_profile_json else None
    requested = canonical_field(field) if field else None
    priority = FIELD_PRIORITY
    if blocking_people(draft):
        # 18/11: khách nói ở chung mà chưa rõ số người → hỏi ngay sau điểm đến,
        # trước cách hiểu mức tiền (số người đổi cả sức chứa lẫn phí theo đầu người).
        head = ("destination_radius", "destination", "people")
        priority = head + tuple(name for name in FIELD_PRIORITY if name not in head)
    for group_field in priority:
        if requested is not None and requested != group_field:
            continue
        interpretations = _interpretations(draft, service, base_profile_json, field=group_field)
        ask_only = any(interpretation.get("ask_only") for interpretation in interpretations)
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
        # "gần tôi" — chip "Dùng vị trí hiện tại" đứng ĐẦU danh sách câu
        # hỏi destination; không có count, không bị lọc vì 0 căn, không bao giờ tự
        # chọn thay khách (decisions.decide bỏ riêng), đi qua to_dto nguyên vẹn.
        # Kind personal ("gần công ty tôi") KHÔNG có chip — vị trí của máy không
        # phải chỗ công ty; hành vi cũ giữ nguyên.
        device_option = ({"id": "opt-device", "field": "destination", "kind": "device_location",
                          "label": "Dùng vị trí hiện tại",
                          "interpretation": {"field": "destination", "kind": "device_location"},
                          "top": [], "count": None, "min_monthly_total_vnd": None,
                          "probability": None, "action": "geolocate", "text": None, "held": 0}
                         if (group_field == "destination" and draft.destination_kind == "current"
                             and not draft.destination) else None)
        candidates = ([device_option] if device_option else []) + kept
        impact = _impact(kept)
        # HN-13.2: field ASK_ONLY (city/budget_cap/destination) là LỰA CHỌN rời
        # rạc khách phải tự chọn (chọn gì thì kết quả khác hẳn), không phải cách
        # hiểu của một câu khách đã nói — không dùng ngưỡng impact chặn.
        # 18/11: "gần trường" mà quanh đó chỉ có MỘT trường có căn vẫn hỏi (một nút +
        # khách gõ tên khác) — không lặng lẽ tìm theo quận bỏ mất ý "gần trường".
        # chip thiết bị luôn dựng được nên câu "gần tôi" luôn hỏi lại điểm
        # neo, kể cả khi danh sách địa danh rỗng (candidates đã gồm chip thiết bị).
        enough = len(candidates) >= 2 or (len(candidates) == 1 and group_field == "destination"
                                          and blocking_destination(draft, confirmed_profile))
        if not enough or (group_field not in ASK_ONLY_FIELDS and not ask_only
                          and impact < IMPACT_THRESHOLD):
            continue
        total = sum(option["count"] for option in kept) or 1
        for option in kept:
            option["probability"] = round(option["count"] / total, 4)
        if group_field == "destination_radius":
            # "Gần" mặc định là gần nhất: chip bán kính xếp gần-trước (HN-08 gold
            # preferred=radius_2000); xác suất vẫn hiển thị trên từng chip.
            kept = sorted(kept, key=lambda option: option["interpretation"]["radius_m"])
        built = {"field": group_field, "impact": round(impact, 4), "options": candidates}
        if group_field == "destination" and draft.destination_kind:
            built["question"] = KIND_QUESTIONS[draft.destination_kind]
        elif group_field == "people" and ask_only:
            built["question"] = "Bạn ở chung tổng cộng mấy người?"
        return built
    return None


KIND_QUESTIONS = {"school": "Bạn muốn ở gần trường nào?",
                  "hospital": "Bạn muốn ở gần bệnh viện nào?",
                  "transit": "Bạn muốn ở gần ga, bến xe hay sân bay nào?",
                  # chỗ của chính khách — hỏi điểm neo, không coi "tôi" là địa danh.
                  "current": "Bạn muốn ở gần chỗ nào? Gõ tên trường, công ty, địa chỉ hoặc chọn một địa điểm bên dưới.",
                  "personal": "Chỗ đó tên gì hoặc ở đường nào? Gõ tên để mình tìm quanh đó."}


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
    thấy 0 căn) — đếm từ pool ước tính nên N là số căn khách sẽ thấy.
    chip "Dùng vị trí hiện tại" không có số căn — giữ nguyên nhãn."""
    if option.get("kind") == "device_location":
        return option["label"]
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
            "question": question or clarification.get("question") or question_for(clarification["field"]),
            "reason": reason,
            "question_source": question_source or "catalog",
            "options": [{"id": option["id"], "label": option_label(option),
                         "detail": option["label"], "probability": option["probability"],
                         "count": option["count"], "min_monthly_total_vnd": option.get("min_monthly_total_vnd"),
                         "decided_by": decided_by,
                         # kind đi nguyên vẹn ra DTO — FE nhận biết chip
                         # "device_location" (action="geolocate") để lấy vị trí thiết bị.
                         "kind": option.get("kind"),
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
