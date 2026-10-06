"""W-02 checks: the public projection is an allowlist and never exposes
drafts, unapproved listings or AI-pending recommendation items."""
import pytest

from backend.app.catalog import Catalog
from backend.app.models import CatalogStatus, DomainError
from backend.app.projection import (PUBLIC_ROOM_FIELDS, ensure_ai_results_public,
                                    is_publicly_visible, public_catalog_projection,
                                    public_room_projection)


def _demo_rooms():
    rooms = Catalog().rooms()
    assert rooms, "Offline demo catalog must load"
    return rooms


def test_public_projection_excludes_unpublished_rooms():
    rooms = _demo_rooms()
    published = [room for room in rooms if room.published]
    assert published, "Demo catalog fixture needs published rooms"
    # A draft copy under a distinct ID must never appear next to its source.
    draft = published[0].model_copy(update={"id": "draft-room-x", "published": False})
    public = public_catalog_projection(rooms + [draft])
    ids = {item["id"] for item in public["rooms"]}
    assert "draft-room-x" not in ids
    assert published[0].id in ids
    assert public["count"] == len(ids)


def test_public_room_projection_is_allowlist_and_drafts_404():
    room = next(room for room in _demo_rooms() if room.published)
    projection = public_room_projection(room)
    # Exactly the allowlisted fields: private or future fields cannot leak.
    assert set(projection) == set(PUBLIC_ROOM_FIELDS)
    assert "published" not in projection
    for field in ("title", "city", "quote", "synthetic", "available"):
        assert field in projection
    draft = room.model_copy(update={"published": False})
    with pytest.raises(DomainError) as error:
        public_room_projection(draft)
    assert error.value.http_status == 404 and error.value.code == "not_found"


def test_public_coordinates_stay_approximate():
    room = next(room for room in _demo_rooms() if room.published)
    exact = room.model_copy(update={"location_accuracy": "exact"})
    assert public_room_projection(exact)["location_accuracy"] == "approximate"
    assert is_publicly_visible(exact)


def test_ai_pending_items_never_enter_public_projection():
    for status in ("generating", "generation_failed", "pending_review", "reviewed",
                   "invalidated", "no_match", "needs_verification", "rejected", "needs_revision"):
        with pytest.raises(DomainError) as error:
            ensure_ai_results_public(status)
        assert error.value.code == "not_published"
    ensure_ai_results_public("published")  # the only public run status


def test_unknown_availability_stays_unknown_in_public_projection():
    room = next(room for room in _demo_rooms() if room.published)
    unknown = room.model_copy(update={"available": None})
    assert public_room_projection(unknown)["available"] is None


def test_stored_catalog_public_projection_follows_moderation(service):
    room = next(room for room in service.catalog.rooms() if room.published)
    public_before = public_catalog_projection(service.catalog.rooms(), service.catalog.version)
    assert room.id in {item["id"] for item in public_before["rooms"]}
    # Moderation (published=False) removes the room from the public projection.
    service.catalog.change_status(room.id, CatalogStatus(expected_revision=room.revision,
                                                         published=False))
    public_after = public_catalog_projection(service.catalog.rooms(), service.catalog.version)
    assert room.id not in {item["id"] for item in public_after["rooms"]}
    assert public_after["catalog_version"] == service.catalog.version
