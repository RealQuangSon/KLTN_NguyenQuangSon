"""Public vs private projections (W-02).

The public projection is an explicit allowlist: a field only appears in
public output when it is listed here. Drafts, unpublished listings and
AI recommendation items that have not completed manager review can never
enter the public projection. Physical-room/listing separation arrives with
HM-02/W-04; until then the canonical room ID doubles as the listing ID and
this module is the single place that decides what the public sees.
"""
from __future__ import annotations

from .catalog import fingerprint
from .models import DomainError, Room

# Allowlist for the public room projection. `published` is a moderation flag
# and is deliberately excluded: visibility is proven by passing the filter,
# not echoed back. `synthetic` stays public for data honesty (NFR-08).
PUBLIC_ROOM_FIELDS = (
    "id", "revision", "title", "city", "area", "room_type", "bedrooms", "capacity", "area_m2",
    "available", "amenities", "latitude", "longitude", "location_accuracy",
    "uncertainty_m", "quote", "source", "synthetic", "features_text", "occupancy", "landlord_id",
)

# Run statuses from which AI recommendation items may be shown publicly.
# Anything pending/reviewed/stale/failed is invisible to public consumers.
AI_VISIBLE_RUN_STATUSES = frozenset({"published"})


def is_publicly_visible(room: Room) -> bool:
    return room.published is True


def public_room_projection(room: Room) -> dict:
    """Allowlist projection of one published room; 404 for anything else."""
    if not is_publicly_visible(room):
        raise DomainError("not_found", "Không tìm thấy phòng.", 404)
    data = room.model_dump(mode="json")
    projection = {field: data[field] for field in PUBLIC_ROOM_FIELDS}
    # Public coordinates must stay approximate even when the owner record is exact.
    if projection["location_accuracy"] == "exact":
        projection["location_accuracy"] = "approximate"
    return projection


def public_catalog_projection(rooms: list[Room], catalog_version: str | None = None) -> dict:
    """Public catalog: only published rooms, stable order, explicit version."""
    visible = sorted((room for room in rooms if is_publicly_visible(room)), key=lambda room: room.id)
    items = [public_room_projection(room) for room in visible]
    return {"rooms": items,
            "catalog_version": catalog_version or fingerprint(items),
            "count": len(items)}


def ensure_ai_results_public(run_status: str) -> None:
    """Guard for AI recommendation items: only published runs are public."""
    if run_status not in AI_VISIBLE_RUN_STATUSES:
        raise DomainError("not_published",
                          "Kết quả AI chưa được quản lý duyệt công bố.", 403)
