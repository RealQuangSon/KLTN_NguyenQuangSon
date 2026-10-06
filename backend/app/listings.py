"""Filter-based search over published listings (tenant portal, no AI and no login).

A published listing has already been approved by its landlord, so it is shown
directly; the AI shortlist keeps its own per-landlord review. Unknown values
never satisfy a filter: an amenity must be explicitly present, and a missing
monthly total is listed as unknown instead of being treated as cheap.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .catalog import normalize
from .costs import calculate_cost
from .locations import canonical_area, canonical_city
from .models import Model, RoomType, Scenario
from .projection import public_room_projection

SORTS = ("monthly_asc", "monthly_desc", "rent_asc", "area_desc")


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
    sort: Literal["monthly_asc", "monthly_desc", "rent_asc", "area_desc"] = "monthly_asc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


def listing_card(room, people: int = 1) -> dict:
    """Public projection plus the cost estimate for a default scenario."""
    cost = calculate_cost(room.quote, Scenario(people=people, vehicles=1))
    return {**public_room_projection(room), "cost": cost.model_dump(mode="json")}


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
        if query.min_area_m2 and room.area_m2 < query.min_area_m2:
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
    keys = {
        "monthly_asc": lambda c: (c["cost"]["monthly_total_vnd"] is None, c["cost"]["monthly_total_vnd"] or 0, c["id"]),
        "monthly_desc": lambda c: (c["cost"]["monthly_total_vnd"] is None, -(c["cost"]["monthly_total_vnd"] or 0), c["id"]),
        "rent_asc": lambda c: (c["quote"]["rent_vnd"], c["id"]),
        "area_desc": lambda c: (-c["area_m2"] if c["area_m2"] else big, c["id"]),
    }
    matches.sort(key=keys[query.sort])
    start = (query.page - 1) * query.page_size
    return {"total": len(matches), "page": query.page, "page_size": query.page_size,
            "items": matches[start:start + query.page_size],
            "notice": "Tin đã được chủ nhà công khai; chi phí là ước tính theo kịch bản mặc định."}
