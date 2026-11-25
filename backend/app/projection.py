"""Public vs private projections (W-02).

The public projection is an explicit allowlist: a field only appears in
public output when it is listed here. Drafts, unpublished listings and
AI recommendation items that have not completed landlord review can never
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
# LF-01: description is the PII-masked post body; posted_at/poster_kind and the
# address detail are listing facts, never ranking input (F2).
# CA-04: source_images (CDN Chợ Tốt URL), toilets và project_name là dữ liệu tin
# gốc để hiển thị; poster_name KHÔNG vào danh sách này — nó chỉ trả qua khối
# contact cho người đã đăng nhập (C1b).
# source_videos (Cloudflare Stream) và tầng/hướng/loại hình
# cũng chỉ để hiển thị, không vào ranking/LLM/embedding.
PUBLIC_ROOM_FIELDS = (
    "id", "revision", "title", "city", "area", "room_type", "bedrooms", "capacity", "area_m2",
    "available", "amenities", "latitude", "longitude", "location_accuracy",
    "uncertainty_m", "quote", "source", "synthetic", "features_text", "occupancy", "landlord_id",
    "description", "posted_at", "poster_kind", "ward", "ward_2025", "street", "available_from",
    "source_images", "source_videos", "toilets", "project_name",
    "floor", "direction", "balcony_direction", "property_subtype",
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
    # Che địa chỉ chi tiết ở LÚC TRẢ RESPONSE (snapshot bất biến,
    # không đổi dữ liệu đã lưu). Model dùng title trực tiếp ở agent_loop/advisor
    # cũng đi qua projection-ish paths; trust/E-06 đọc Room gốc nên không ảnh hưởng.
    from .listings import mask_address
    street = data.get("street")
    for field in ("description", "title", "street"):
        value = projection.get(field)
        if isinstance(value, str):
            projection[field] = mask_address(value, street)
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
                          "Kết quả AI chưa được công bố.", 403)
