"""Filter-based search over published listings (tenant portal, no AI and no login).

A published listing has already been approved by its landlord, so it is shown
directly; the AI shortlist keeps its own per-landlord review. Unknown values
never satisfy a filter: an amenity must be explicitly present, and a missing
monthly total is listed as unknown instead of being treated as cheap.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from .catalog import normalize
from .costs import calculate_cost
from .locations import canonical_area, canonical_city
from .models import Model, RoomType, Scenario
from .projection import public_room_projection

# Rooms imported from a crawl (data/crawl_chotot.py): the poster is not a platform account.
CRAWLED_SOURCE_PREFIXES = ("chotot://", "https://www.chotot.com/")
SORTS = ("monthly_asc", "monthly_desc", "rent_asc", "area_desc", "posted_desc")


def crawled_source_url(source: str | None) -> str | None:
    """URL tin gốc chỉ khi `source` thuộc CRAWLED_SOURCE_PREFIXES và là http(s).

    Scheme nội bộ "chotot://" là tin cào nhưng không mở được trên web → None.
    """
    if not source or not source.startswith(CRAWLED_SOURCE_PREFIXES):
        return None
    if not source.lower().startswith(("http://", "https://")):
        return None
    return source


class ListingQuery(Model):
    city: str | None = Field(default=None, max_length=64)
    area: str | None = Field(default=None, max_length=64)
    room_type: RoomType | None = None
    min_rent: int | None = Field(default=None, ge=0)
    max_rent: int | None = Field(default=None, ge=0)
    max_monthly: int | None = Field(default=None, ge=0)
    min_area_m2: float | None = Field(default=None, ge=0)
    min_bedrooms: int | None = Field(default=None, ge=1, le=5)
    people: int = Field(default=1, ge=1, le=20)
    amenities: list[str] = Field(default_factory=list, max_length=9)
    sort: Literal["monthly_asc", "monthly_desc", "rent_asc", "area_desc", "posted_desc"] = "monthly_asc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# --- E-03: che địa chỉ chi tiết ở lớp hiển thị ---------------------------------
# Chỉ che khi có NGỮ CẢNH địa chỉ; không đụng 24/7, ngày 12/11, tiền 3tr5,
# 200k/phòng, "số 2 người", "5 triệu". Snapshot bất biến: che lúc trả response.
MASK = "[Địa chỉ đã che]"
STREET_NUMBER_BEFORE = re.compile(
    r"(\d{1,4}(?:/\d{1,4}){0,3})(\s+(?:[ttnn][ưú]?\s+)?"
    r"(?:đường|Đường|phố|Phole|Phố)?\s*[A-Za-zÀ-ỹ])")
WITH_CONTEXT_FRACTION = re.compile(
    r"((?:\b[sS][oôốO]\s*|\b[nN]h[aàáA]\s*|\b[pP]h[oòôO][nñ]g\s*)"
    r"(?:\d{1,4}/\d{1,4}(?:/\d{1,4}){0,2})(?![\d/]))")
# Ngoại lệ đã biết KHÔNG phải địa chỉ: "24/7" (mở cửa), ngày tháng D/M.
NON_ADDRESS_FRACTION = re.compile(r"(?:^|[^\d/])(24/7)(?![\d/])")
NOT_ADDRESS_BEFORE = re.compile(r"c[aá]ch\s+[^,.]{0,20}$")


def mask_address(text: str | None, street: str | None = None) -> str | None:
    """Best-effort che số nhà trong văn bản hiển thị. Chỉ nhắm số đứng trước
    tên đường (khi biết `street`) và dạng 12/34A có ngữ cảnh "số"/"nhà"; không
    đụng 24/7, ngày D/M, tiền. Không bảo đảm che hết — UI phải nói rõ."""
    if not text:
        return text
    result = text
    if street:
        street_fold = " ".join(street.split())
        for word in {street_fold, re.sub(r"^(?:Đường|đường|Quận|quận)\s+", "", street_fold)}:
            if not word or len(word) < 4:
                continue
            escaped = re.escape(word)
            # Số đứng NGAY TRƯỚC tên đường: "25/12 đường Bà Cut", "25 Đường Bà Cut".
            # Lookbehind (?<![\w/]): số phải KHÔNG đứng liền sau chữ cái/chữ số
            # (\w tính cả chữ có dấu tiếng Việt) hoặc "/" — không thì sẽ bắt nhầm
            # "2" trong "40m2 Trần Xuân Soạn" hay "7" trong "Q7 Bà Cut".
            pattern = re.compile(
                rf"(?<![\w/])(\d{{1,4}}(?:/\d{{1,4}}){{0,3}})"
                rf"(\s+(?:[đd][uu][oờ]ng\s+)?{escaped})", re.IGNORECASE)
            result = pattern.sub(lambda match: f"{MASK}{match.group(2)}", result)
    # Dạng phân số 12/34A chỉ che khi có "số"/"nhà" ngay trước (ngữ cảnh địa chỉ):
    # "số 25/3A" → che; "24/7", "ngày 12/11" → không có ngữ cảnh → giữ nguyên.
    def _mask_fraction(match):
        fraction = match.group(1)
        if fraction and NON_ADDRESS_FRACTION.search(fraction):
            return match.group(0)
        return match.group(0).replace(fraction, MASK) if fraction else match.group(0)

    result = WITH_CONTEXT_FRACTION.sub(_mask_fraction, result)
    return result


def listing_card(room, people: int = 1) -> dict:
    """Public projection plus the cost estimate for a default scenario."""
    cost = calculate_cost(room.quote, Scenario(people=people, vehicles=1))
    return {**public_room_projection(room), "cost": cost.model_dump(mode="json")}


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _posted_moment(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def search(rooms, query: ListingQuery) -> dict:
    city = normalize(canonical_city(query.city)) if query.city else None
    area = normalize(canonical_area(query.area, query.city)) if query.area else None
    matches = []
    for room in rooms:
        if not room.published or room.available is False:
            continue
        if city and normalize(canonical_city(room.city)) != city:
            continue
        if area and normalize(canonical_area(room.area, room.city)) != area:
            continue
        if query.room_type and room.room_type != query.room_type:
            continue
        if query.min_bedrooms and (room.bedrooms or 0) < query.min_bedrooms:
            continue
        if query.min_area_m2 is not None and (room.area_m2 is None
                                              or room.area_m2 < query.min_area_m2):
            # Tin không rõ diện tích không thỏa bộ lọc tối thiểu (không TypeError).
            continue
        if room.capacity is not None and room.capacity < query.people:
            continue
        if query.min_rent is not None and room.quote.rent_vnd < query.min_rent:
            continue
        if query.max_rent is not None and room.quote.rent_vnd > query.max_rent:
            continue
        if any(room.amenities.get(name) is not True for name in query.amenities):
            continue
        card = listing_card(room, query.people)
        monthly = card["cost"]["monthly_total_vnd"]
        if query.max_monthly is not None and (monthly is None or monthly > query.max_monthly):
            continue
        matches.append(card)
    big = float("inf")
    # "Mới đăng" là lựa chọn của người dùng ở tìm theo bộ lọc (F2): never used
    # by the AI ranking. Unknown posting times sort last, never first.
    posted = {card["id"]: _posted_moment(card.get("posted_at")) for card in matches}
    keys = {
        "monthly_asc": lambda c: (c["cost"]["monthly_total_vnd"] is None, c["cost"]["monthly_total_vnd"] or 0, c["id"]),
        "monthly_desc": lambda c: (c["cost"]["monthly_total_vnd"] is None, -(c["cost"]["monthly_total_vnd"] or 0), c["id"]),
        "rent_asc": lambda c: (c["quote"]["rent_vnd"], c["id"]),
        "area_desc": lambda c: (-c["area_m2"] if c["area_m2"] else big, c["id"]),
        "posted_desc": lambda c: (posted[c["id"]] is None, -(posted[c["id"]] or EPOCH).timestamp(), c["id"]),
    }
    matches.sort(key=keys[query.sort])
    start = (query.page - 1) * query.page_size
    return {"total": len(matches), "page": query.page, "page_size": query.page_size,
            "items": matches[start:start + query.page_size],
            "notice": "Tin đã được chủ nhà công khai; chi phí là ước tính theo kịch bản mặc định."}
