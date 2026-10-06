"""Canonical city/area names and the aliases renters actually type.

Areas use the district names renters and listings still use after the
01/07/2025 administrative merger; ward-level geography is not modelled here.
Matching runs on diacritic-free, casefolded text with word boundaries.
"""
from __future__ import annotations

import re
import unicodedata


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
    "TP. Thủ Đức": ("thu duc",),
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


def canonical_city(value: str | None) -> str | None:
    if value is None:
        return None
    return find_city(value) or " ".join(value.split())


def canonical_area(value: str | None, city: str | None = None) -> str | None:
    if value is None:
        return None
    return find_area(value, canonical_city(city)) or " ".join(value.split())

