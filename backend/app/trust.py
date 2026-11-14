"""E-04: kiểm chứng tin — code tất định, KHÔNG vào xếp hạng (R4).

Mỗi mục trả {key, status, detail} với đúng ba trạng thái ok/warn/unknown.
Thiếu dữ liệu là unknown, KHÔNG BAO GIỜ ok. Ngưỡng là hằng số đặt tên rõ;
ảnh chỉ so URL/tên file, không tải ảnh. Kết quả nhóm cache theo
catalog.version (một truy vấn nhóm, không truy vấn từng dòng — Neon chậm);
freshness tính theo thời điểm hiện tại nên KHÔNG cache mục đó.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

PRICE_PER_M2_LOW = 0.5      # warn khi giá/m² < 50% trung vị nhóm
PRICE_PER_M2_HIGH = 2.0     # warn khi giá/m² > 200% trung vị nhóm
PRICE_GROUP_MIN = 5         # nhóm dưới 5 tin → unknown
FRESH_DAYS_OK = 30          # đăng trong 30 ngày → ok, quá → warn
DUPLICATE_RATIO_WINDOW = 48  # trùng tiêu đề+giá+khu trong cùng cửa sổ quét

TRUST_NOTICE = "Kiểm chứng tính tự động, không phải chứng nhận."

TRUST_KEYS = ("completeness", "price_vs_area", "duplicate", "image_reuse",
              "prepay_request", "title_consistency", "freshness", "reports",
              "ownership")


def _entry(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def _fold(value: str) -> str:
    from .locations import fold
    return fold(value)


# Câu đòi cọc/trả tiền TRƯỚC khi xem — ngữ cảnh rõ, không bắt nhầm ngày/24/7.
PREPAY_PATTERNS = (
    "dat coc truoc", "coc truoc khi xem", "chuyen tien truoc", "ck truoc",
    "chuyen khoan truoc", "chuyen coc truoc", "coc giu cho truoc khi xem",
    "gui tien truoc khi xem",
)


def _group_key(room) -> tuple:
    return (room.city, room.area, room.room_type)


def _prices_per_m2(rooms: list) -> dict[tuple, list[float]]:
    groups: dict[tuple, list[float]] = {}
    for room in rooms:
        if room.area_m2 and room.quote.rent_vnd and room.published:
            groups.setdefault(_group_key(room), []).append(room.quote.rent_vnd / room.area_m2)
    return groups


def _completeness(room) -> dict:
    missing = []
    if not room.source_images:
        missing.append("ảnh")
    if not room.quote.rent_vnd:
        missing.append("giá")
    if room.area_m2 is None:
        missing.append("diện tích")
    if room.quote.deposit_vnd is None:
        missing.append("tiền cọc")
    fee_names = {fee.name for fee in room.quote.fees}
    main = {"electricity", "water"} - fee_names
    missing.extend(sorted(main))
    if not missing:
        return _entry("ok", "Tin có đủ ảnh, giá, diện tích, cọc và phí điện nước.")
    return _entry("warn", "Tin còn thiếu: " + ", ".join(missing) + ".")


def _price_vs_area(room, groups: dict[tuple, list[float]]) -> dict:
    if not room.area_m2 or not room.quote.rent_vnd:
        return _entry("unknown", "Tin chưa ghi giá hoặc diện tích nên chưa so được giá mỗi m².")
    peers = groups.get(_group_key(room)) or []
    if len(peers) < PRICE_GROUP_MIN:
        return _entry("unknown", f"Nhóm khu vực chỉ có {len(peers)} tin so sánh — chưa đủ mặt bằng.")
    value = room.quote.rent_vnd / room.area_m2
    middle = median(peers)
    if middle <= 0:
        return _entry("unknown", "Mặt bằng nhóm chưa tính được.")
    ratio = value / middle
    if PRICE_PER_M2_LOW <= ratio <= PRICE_PER_M2_HIGH:
        return _entry("ok", f"Giá mỗi m² gần mặt bằng nhóm ({ratio:.0%} của trung vị).")
    side = "cao hơn" if ratio > 1 else "thấp hơn"
    return _entry("warn", f"Giá mỗi m² {side} trung vị nhóm {abs(ratio - 1):.0%}.")


def _duplicate(room, rooms: list) -> dict:
    title = " ".join(_fold(room.title).split())
    same = [other for other in rooms
            if other.id != room.id and other.published
            and " ".join(_fold(other.title).split()) == title
            and other.quote.rent_vnd == room.quote.rent_vnd
            and other.area == room.area]
    if same:
        return _entry("warn", f"Có {len(same)} tin khác cùng tiêu đề, giá và khu vực.")
    return _entry("ok", "Không thấy tin trùng tiêu đề, giá và khu vực.")


def _image_reuse(room, rooms: list) -> dict:
    if not room.source_images:
        return _entry("unknown", "Tin chưa có ảnh để đối chiếu.")
    mine = {url.rsplit("/", 1)[-1] for url in room.source_images}
    others = set()
    for other in rooms:
        if other.id == room.id or not other.published:
            continue
        others |= {url.rsplit("/", 1)[-1] for url in other.source_images}
    shared = mine & others
    if shared:
        return _entry("warn", "Mã file ảnh trùng với tin khác — có thể là ảnh đăng lại.")
    return _entry("ok", "Ảnh không trùng với tin khác trong kho.")


def _prepay_request(room) -> dict:
    haystack = _fold(f"{room.title} {room.description or ''}")
    hits = [pattern for pattern in PREPAY_PATTERNS if pattern in haystack]
    if hits:
        # Không trích số điện thoại: chỉ nêu phát hiện, không trích nguyên câu.
        return _entry("warn", "Mô tả có dấu hiệu đòi cọc/chuyển tiền trước khi xem.")
    return _entry("ok", "Không thấy yêu cầu chuyển tiền trước khi xem.")


def _title_consistency(room) -> dict:
    import re
    title = _fold(room.title)
    prices = [int(value) for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:tr|trieu)", title)]
    price_known = room.quote.rent_vnd
    area_matches = re.findall(r"(\d{2,3})\s*m2\b", title)
    checks = []
    if prices and price_known:
        stated = prices[0].replace(",", ".") if isinstance(prices[0], str) else prices[0]
        stated = float(str(stated).replace(",", "."))
        if abs(stated * 1_000_000 - price_known) > 500_000:
            checks.append("giá trong tiêu đề lệch với tin")
    if area_matches and room.area_m2:
        if abs(float(area_matches[0]) - room.area_m2) > 3:
            checks.append("diện tích trong tiêu đề lệch với tin")
    if checks:
        return _entry("warn", "; ".join(checks) + ".")
    if prices or area_matches:
        return _entry("ok", "Số trong tiêu đề khớp với tin.")
    return _entry("unknown", "Tiêu đề không ghi giá hoặc diện tích để đối chiếu.")


def _freshness(room, now: datetime) -> dict:
    if not room.posted_at:
        return _entry("unknown", "Tin không ghi ngày đăng.")
    posted = room.posted_at if room.posted_at.tzinfo else room.posted_at.replace(tzinfo=timezone.utc)
    days = (now - posted).days
    if days <= FRESH_DAYS_OK:
        return _entry("ok", f"Tin đăng {days} ngày trước.")
    return _entry("warn", f"Tin đăng {days} ngày trước, đã cũ.")


def _reports(room, confirmed_room_ids: set[str]) -> dict:
    if room.id in confirmed_room_ids:
        return _entry("warn", "Tin có báo cáo đã được xác nhận từ người dùng.")
    return _entry("ok", "Không có báo cáo đã xác nhận.")


def _ownership(room) -> dict:
    # Luôn unknown với tin cào: chưa đối chiếu giấy tờ (R4, E-04 bảng).
    if room.synthetic:
        return _entry("unknown", "Tin giả lập — không áp dụng kiểm chứng quyền sở hữu.")
    return _entry("unknown", "Chưa đối chiếu giấy tờ ownership.")


class TrustChecker:
    """Cache nhóm theo catalog.version; freshness tính live, không cache."""

    def __init__(self):
        self._version: str | None = None
        self._groups: dict[tuple, list[float]] | None = None
        self._rooms: list = []
        self._confirmed: set[str] = set()
        self._per_room: dict[str, dict[str, dict]] = {}

    @property
    def groups(self) -> dict[tuple, list[float]]:
        return self._groups or {}

    def refresh(self, rooms: list, catalog_version: str,
                confirmed_room_ids: set[str]) -> None:
        if catalog_version == self._version and confirmed_room_ids == self._confirmed:
            return
        self._version = catalog_version
        self._rooms = list(rooms)
        self._groups = _prices_per_m2(rooms)
        self._confirmed = set(confirmed_room_ids)
        self._per_room = {}

    def for_room(self, room) -> dict:
        if room.id in self._per_room:
            cached = self._per_room[room.id]
            # freshness luôn tính live theo thời điểm hiện tại.
            cached["freshness"] = _freshness(room, datetime.now(timezone.utc))
            return cached
        result = {
            "completeness": _completeness(room),
            "price_vs_area": _price_vs_area(room, self._groups or {}),
            "duplicate": _duplicate(room, self._rooms),
            "image_reuse": _image_reuse(room, self._rooms),
            "prepay_request": _prepay_request(room),
            "title_consistency": _title_consistency(room),
            "freshness": _freshness(room, datetime.now(timezone.utc)),
            "reports": _reports(room, self._confirmed),
            "ownership": _ownership(room),
        }
        self._per_room[room.id] = result
        return result


def listing_checks(room, groups: dict[tuple, list[float]]) -> dict:
    """Giá mỗi m² và vị trí so với trung vị khu — dùng chung số với price_vs_area (E-06.3)."""
    peers = groups.get(_group_key(room)) or []
    if not room.area_m2 or not room.quote.rent_vnd or len(peers) < PRICE_GROUP_MIN:
        return {"price_per_m2": None, "group_median_per_m2": None, "position": None}
    value = room.quote.rent_vnd / room.area_m2
    middle = median(peers)
    ratio = value / middle if middle else None
    position = None
    if ratio is not None:
        position = "ok" if PRICE_PER_M2_LOW <= ratio <= PRICE_PER_M2_HIGH \
            else ("high" if ratio > 1 else "low")
    return {"price_per_m2": round(value), "group_median_per_m2": round(middle),
            "position": position}


def similar_rooms(room, rooms: list, limit: int = 3) -> list:
    """E-06.4: chỗ ở tương tự — cùng thành phố, loại, mức giá gần; KHÔNG dùng
    posted_at, không đi qua LLM, không gồm monthly ước tính (so rent_vnd thô)."""
    if not room.quote.rent_vnd:
        return []
    candidates = []
    for other in rooms:
        if other.id == room.id or not other.published or other.available is False:
            continue
        if other.city != room.city or other.room_type != room.room_type:
            continue
        if not other.quote.rent_vnd:
            continue
        gap = abs(other.quote.rent_vnd - room.quote.rent_vnd) / max(room.quote.rent_vnd, 1)
        candidates.append((gap, other.id, other))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in candidates[:limit]]
