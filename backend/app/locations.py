"""Canonical city/area names and the aliases renters actually type.

Areas use the district names renters and listings still use after the
01/07/2025 administrative merger; ward-level geography is not modelled here.
Matching runs on diacritic-free, casefolded text with word boundaries.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path


def fold(text: str) -> str:
    value = unicodedata.normalize("NFD", unicodedata.normalize("NFC", text).casefold()).replace("đ", "d")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.replace(".", " ").split())


CITY_ALIASES: dict[str, tuple[str, ...]] = {
    "TP.HCM": ("tp hcm", "tphcm", "hcm", "ho chi minh", "sai gon", "saigon", "sg"),
    "Hà Nội": ("ha noi", "hanoi", "hn"),
}

_HCM_NUMBERED = {f"Quận {n}": (f"quan {n}", f"q {n}", f"q{n}") for n in (1, 3, 4, 5, 6, 7, 8, 10, 11, 12)}
_HCM_NAMED = {
    "Quận Bình Thạnh": ("binh thanh",),
    "Quận Gò Vấp": ("go vap",),
    "Quận Phú Nhuận": ("phu nhuan",),
    "Quận Tân Bình": ("tan binh",),
    "Quận Tân Phú": ("tan phu",),
    "Quận Bình Tân": ("binh tan",),
    # Sau sáp nhập 01/07/2025, Quận 9 (cùng Quận 2) thuộc TP. Thủ Đức — khách vẫn
    # gõ tên quận cũ ("khu công nghệ cao Quận 9"); nhận dạng về tên khu mới.
    "TP. Thủ Đức": ("thu duc", "quan 9", "q9", "q 9"),
    "Huyện Bình Chánh": ("binh chanh",),
    "Huyện Nhà Bè": ("nha be",),
}
_HANOI_NAMED = {
    "Quận Ba Đình": ("ba dinh",),
    "Quận Hoàn Kiếm": ("hoan kiem",),
    "Quận Đống Đa": ("dong da",),
    "Quận Hai Bà Trưng": ("hai ba trung",),
    "Quận Cầu Giấy": ("cau giay",),
    "Quận Thanh Xuân": ("thanh xuan",),
    "Quận Hoàng Mai": ("hoang mai",),
    "Quận Long Biên": ("long bien",),
    "Quận Tây Hồ": ("tay ho",),
    "Quận Bắc Từ Liêm": ("bac tu liem",),
    "Quận Nam Từ Liêm": ("nam tu liem",),
    "Quận Hà Đông": ("ha dong",),
}
AREA_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "TP.HCM": {**_HCM_NUMBERED, **_HCM_NAMED},
    "Hà Nội": _HANOI_NAMED,
}


def _pattern(alias: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")


def _with_prefixes(canonical: str, aliases: tuple[str, ...]) -> tuple[str, ...]:
    # "Quận Bình Thạnh", "quan binh thanh" and "binh thanh" all name the same area.
    return tuple(dict.fromkeys((fold(canonical), *aliases, *(f"quan {alias}" for alias in aliases))))


_CITY_PATTERNS = [(city, _pattern(alias)) for city, aliases in CITY_ALIASES.items()
                  for alias in (fold(city), *aliases)]
_AREA_PATTERNS = sorted(
    ((city, area, alias, _pattern(alias)) for city, areas in AREA_ALIASES.items()
     for area, aliases in areas.items() for alias in _with_prefixes(area, aliases)),
    key=lambda item: -len(item[2]),  # longest alias first: "nam tu liem" before "tu liem"
)


def find_city(text: str) -> str | None:
    value = fold(text)
    found = {city for city, pattern in _CITY_PATTERNS if pattern.search(value)}
    return found.pop() if len(found) == 1 else None


def find_area(text: str, city: str | None = None) -> str | None:
    """First area named in the text, restricted to `city` when it is known."""
    value = fold(text)
    for area_city, area, _, pattern in _AREA_PATTERNS:
        if (city is None or area_city == city) and pattern.search(value):
            return area
    return None


def city_for_area(area: str | None) -> str | None:
    """The single city a known area belongs to ("Bình Thạnh"/"Quận Bình Thạnh" → TP.HCM).
    None for anything unrecognised, so the city is never guessed from vague text."""
    if area is None:
        return None
    value = fold(area)
    matches = {area_city for area_city, area_name, alias, _ in _AREA_PATTERNS
               if value == fold(area_name) or value == alias}
    return matches.pop() if len(matches) == 1 else None


def canonical_city(value: str | None) -> str | None:
    if value is None:
        return None
    return find_city(value) or " ".join(value.split())


def canonical_area(value: str | None, city: str | None = None) -> str | None:
    if value is None:
        return None
    return find_area(value, canonical_city(city)) or " ".join(value.split())



# --- AG-01: điểm mốc (điểm đến) từ danh mục tĩnh data/places.json ---

_PLACES_PATH = Path(os.getenv(
    "HOMEMATCH_PLACES_PATH",
    Path(__file__).resolve().parents[2] / "data" / "places.json"))


def _load_places() -> list[dict]:
    if not _PLACES_PATH.exists():
        return []
    return json.loads(_PLACES_PATH.read_text(encoding="utf-8")).get("places", [])


_PLACES: list[dict] = _load_places()
# Longest alias first so "bach khoa ha noi" wins over a bare "bk" inside the same text.
_PLACE_PATTERNS = sorted(
    ((place, alias, _pattern(fold(alias))) for place in _PLACES
     for alias in [*(place.get("names") or []), *(place.get("aliases") or [])]),
    key=lambda item: -len(fold(item[1])),
)


_PLACE_KINDS = (("school", ("dai hoc", "dh ", "hoc vien", "cao dang", "truong ")),
                ("hospital", ("benh vien",)),
                ("transit", ("ga ", "ben xe", "san bay")))


def place_kind(place: dict) -> str | None:
    """Loại điểm mốc: đọc trường `kind` của places.json trước (LOC-001); chỉ khi mục
    không có `kind` mới suy từ TÊN (dự phòng). Dùng để lọc nút "gần đâu?" theo
    đúng loại khách nhắc ("gần trường" → các trường)."""
    if place.get("kind"):
        return place["kind"]
    first = fold((place.get("names") or [""])[0]) + " "
    names = " ".join(fold(name) + " " for name in place.get("names") or [])
    # Tên bắt đầu bằng loại nào thì là loại đó ("Bệnh viện Đại học Y Dược" là bệnh viện).
    for kind, prefixes in _PLACE_KINDS:
        if any(first.startswith(prefix) for prefix in prefixes):
            return kind
    for kind, prefixes in _PLACE_KINDS:
        if any(names.startswith(prefix) or f" {prefix}" in names for prefix in prefixes):
            return kind
    return None


def _place_dto(place: dict) -> dict:
    return {"id": place["id"], "label": place["names"][0], "city": place["city"],
            "latitude": place["latitude"], "longitude": place["longitude"],
            "uncertainty_m": place.get("uncertainty_m", 500)}


def resolve_place_candidates(text: str, city: str | None = None) -> list[dict]:
    """Mọi điểm mốc khớp tốt nhất (alias dài nhất) trong câu — LOC-001.

    Một phần tử = khớp duy nhất; nhiều phần tử = mơ hồ (ví dụ "Bách Khoa" khi
    chưa biết thành phố khớp cả HUST lẫn HCMUT). `city` (khi đã biết) giới hạn
    kết quả. Danh sách rỗng khi không có điểm mốc nào."""
    if not _PLACE_PATTERNS:
        return []
    value = fold(text)
    matches: dict[str, dict] = {}
    best = -1
    for place, alias, pattern in _PLACE_PATTERNS:
        if city is not None and place["city"] != city:
            continue
        if pattern.search(value):
            length = len(fold(alias))
            if length > best:
                best, matches = length, {place["id"]: place}
            elif length == best:
                matches.setdefault(place["id"], place)
    return [_place_dto(place) for place in matches.values()]


def place_by_id(place_id: str) -> dict | None:
    place = next((item for item in _PLACES if item.get("id") == place_id), None)
    return _place_dto(place) if place else None


def resolve_place(text: str, city: str | None = None) -> dict | None:
    """Tên điểm mốc trong câu → điểm đến có tọa độ (AG-01).

    So khớp fold dấu theo ranh giới từ, ưu tiên alias dài nhất; `city` (khi đã
    biết) giới hạn kết quả. Hai điểm mốc khác thành phố khớp cùng độ dài alias
    mà chưa biết thành phố thì trả None (không đoán). Không có điểm mốc ngoài
    danh mục: trả None để luồng giữ nguyên hành vi cũ (hỏi/sắp theo khu vực)."""
    found = resolve_place_candidates(text, city)
    return found[0] if len(found) == 1 else None
