"""LF-01: new listing fields on Room/Quote, public projection, ranking invariants.

The frozen synthetic catalog keeps loading with every new field null; the
validators reject out-of-range terms; the public projection exposes the new
listing facts; the AI ranking reads none of them (F2), while new amenity keys
behave exactly like the old ones in hard filters and preference scoring.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.catalog import Catalog
from backend.app.main import create_app
from backend.app.models import AMENITY_KEYS, Profile, Quote, Room, Scenario
from backend.app.projection import PUBLIC_ROOM_FIELDS, public_room_projection

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OWNER_A = {"Authorization": "Bearer demo-owner-a"}
OWNER_B = {"Authorization": "Bearer demo-owner-b"}


def make_quote(**overrides):
    base = {"rent_vnd": 3_000_000, "fees": []}
    return Quote.model_validate({**base, **overrides})


def make_room(**overrides):
    base = {"id": "lf-room-1", "revision": 1, "title": "Phòng test trường mới", "city": "TP.HCM",
            "area": "Quận Phú Nhuận", "published": True, "available": True, "capacity": 2,
            "area_m2": 20.0, "amenities": {"kitchen": True}, "quote": make_quote(),
            "source": "https://www.chotot.com/123456.htm"}
    return Room.model_validate({**base, **overrides})


def test_frozen_catalog_loads_with_null_new_fields():
    payload = json.loads((DATA_DIR / "catalog/rooms.json").read_text(encoding="utf-8"))
    rooms = [Room.model_validate(item) for item in payload["rooms"]]
    assert rooms
    for room in rooms:
        assert room.description is None and room.posted_at is None and room.poster_kind is None
        assert room.ward is None and room.ward_2025 is None and room.street is None
        assert room.available_from is None
        assert room.quote.payment_cycle_months is None and room.quote.min_lease_months is None


def test_new_fields_round_trip_through_room_model():
    posted = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
    room = make_room(description="Phòng có bếp, WC riêng.", posted_at=posted, poster_kind="broker",
                     ward="Phường 9", ward_2025="Phường Đức Nhuận", street="Đường Hồ Văn Huê",
                     available_from=date(2026, 12, 1),
                     quote=make_quote(payment_cycle_months=3, min_lease_months=12))
    dumped = room.model_dump(mode="json")
    assert Room.model_validate(dumped) == room
    assert dumped["posted_at"] == "2026-10-30T03:00:00Z" and dumped["available_from"] == "2026-12-01"


def test_term_validators_block_out_of_range_values():
    for field, bad in (("payment_cycle_months", 0), ("payment_cycle_months", 13),
                       ("min_lease_months", 0), ("min_lease_months", 100)):
        with pytest.raises(ValidationError) as error:
            make_quote(**{field: bad})
        assert error.value.errors()[0]["type"] != "extra_forbidden", "field must exist, not be rejected as unknown"
    assert make_quote(payment_cycle_months=12).payment_cycle_months == 12
    assert make_quote(min_lease_months=60).min_lease_months == 60


def test_description_and_poster_kind_validators():
    with pytest.raises(ValidationError):
        make_room(description="x" * 4001)
    assert len(make_room(description="x" * 4000).description) == 4000
    with pytest.raises(ValidationError) as error:
        make_room(poster_kind="agency")
    assert error.value.errors()[0]["type"] == "literal_error"


def test_amenity_keys_constant_matches_the_frozen_list():
    assert set(AMENITY_KEYS) == {
        "air_conditioning", "washing_machine", "balcony", "parking", "window",
        "private_bathroom", "furniture", "pets_allowed", "quiet",
        "kitchen", "wifi", "elevator", "security_24h", "camera", "loft",
        "flexible_hours", "no_shared_landlord", "water_heater", "fridge"}
    assert len(AMENITY_KEYS) == len(set(AMENITY_KEYS))


def test_public_projection_exposes_new_listing_fields():
    room = make_room(description="Phòng có bếp.", posted_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
                     poster_kind="broker", ward="Phường 9", ward_2025="Phường Đức Nhuận",
                     street="Đường Hồ Văn Huê", available_from=date(2026, 12, 1))
    projection = public_room_projection(room)
    assert set(projection) == set(PUBLIC_ROOM_FIELDS)
    assert projection["description"] == "Phòng có bếp."
    assert projection["poster_kind"] == "broker"
    assert projection["ward_2025"] == "Phường Đức Nhuận" and projection["available_from"] == "2026-12-01"
    # Unknown stays null in the projection, never 0/false.
    empty = public_room_projection(make_room())
    assert empty["description"] is None and empty["posted_at"] is None and empty["poster_kind"] is None


def test_roominput_accepts_editable_fields_and_rejects_server_set_ones():
    from backend.app.models import RoomInput
    values = {"title": "Phòng có bếp quận Phú Nhuận", "city": "TP.HCM", "area": "Quận Phú Nhuận",
              "area_m2": 20.0, "available": True, "quote": make_quote().model_dump(),
              "description": "Phòng đầy đủ tiện nghi.", "ward": "Phường 9", "street": "Đường Hồ Văn Huê",
              "available_from": "2026-12-01"}
    room_input = RoomInput.model_validate(values)
    assert room_input.available_from == date(2026, 12, 1)
    for server_set in ({"posted_at": "2026-10-30T00:00:00Z"}, {"poster_kind": "broker"}):
        with pytest.raises(ValidationError) as error:
            RoomInput.model_validate({**values, **server_set})
        assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_ranking_ignores_posted_at_poster_kind_and_description():
    catalog = Catalog(DATA_DIR / "catalog/rooms.json")
    profile = Profile(city="TP.HCM", room_type="room", max_monthly_cost_vnd=8_000_000,
                      scenario=Scenario(people=1))
    base_ranked, _ = catalog.rank(profile, method="B1")
    assert base_ranked, "synthetic catalog must yield eligible rooms for the profile"
    # Distinct posting times per room: a ranking that reads them must move.
    stamped = [room.model_copy(update={
        "posted_at": datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        "poster_kind": "broker" if index % 2 else "individual",
        "description": f"Tin số {index}."})
        for index, room in enumerate(catalog.rooms())]
    assert any(room.posted_at for room in stamped)
    mutated_ranked, _ = _rank_rooms(stamped, profile)
    assert [(item.room_id, item.score, item.components) for item in mutated_ranked] == \
           [(item.room_id, item.score, item.components) for item in base_ranked]


def _rank_rooms(rooms, profile):
    import tempfile
    from backend.app.catalog import Catalog as CatalogClass
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "rooms.json"
        path.write_text(json.dumps({"rooms": [room.model_dump(mode="json") for room in rooms]},
                                   ensure_ascii=False), encoding="utf-8")
        reloaded = CatalogClass(path)
        assert [(room.posted_at, room.poster_kind, room.description, room.available_from)
                for room in reloaded.rooms()] == \
               [(room.posted_at, room.poster_kind, room.description, room.available_from)
                for room in rooms], "new fields must survive the catalog round trip"
        return reloaded.rank(profile, method="B1")


def test_new_amenity_keys_work_as_hard_filter_and_preference():
    catalog_room = next(room for room in Catalog(DATA_DIR / "catalog/rooms.json").rooms()
                        if room.published and room.available and room.capacity)
    with_kitchen = catalog_room.model_copy(update={"amenities": {**catalog_room.amenities, "kitchen": True}})
    unknown_kitchen = catalog_room.model_copy(update={"amenities": {**catalog_room.amenities, "kitchen": None}})
    base = dict(room_type=catalog_room.room_type, max_monthly_cost_vnd=50_000_000,
                scenario=Scenario(people=1))
    profile = Profile(city=catalog_room.city, area=catalog_room.area, must_amenities=["kitchen"], **base)
    eligible, diagnostics = _rank_rooms([with_kitchen], profile)
    assert [item.room_id for item in eligible] == [with_kitchen.id]
    blocked, _ = _rank_rooms([unknown_kitchen], profile)
    assert blocked == [] and diagnostics["rejected"].get("required_amenity") is None
    unknown_profile = Profile(city=catalog_room.city, area=catalog_room.area,
                              preferences=["kitchen"], **base)
    preferred, _ = _rank_rooms([with_kitchen], unknown_profile)
    assert preferred[0].components["preferences"] == 1.0


def test_landlord_sees_own_description_but_other_landlord_never_does(service):
    client = None
    with TestClient(create_app(lambda: service)) as test_client:
        client = test_client
        payload = {"title": "Phòng có bếp của owner-a", "city": "TP.HCM", "area": "Quận 1",
                   "area_m2": 18.0, "available": True,
                   "quote": {"rent_vnd": 3_000_000, "fees": []},
                   "description": "Liên hệ 0901234567.", "ward": "Phường Bến Nghé",
                   "available_from": "2026-12-01"}
        created = client.post("/landlord/rooms", headers=OWNER_A, json=payload)
        assert created.status_code == 201, created.text
        room_id = created.json()["room"]["id"]
        own = client.get(f"/landlord/rooms/{room_id}", headers=OWNER_A).json()["room"]
        # FC-01/F4: masking happens at write time, so the stored copy itself is masked.
        assert own["description"] == "Liên hệ [SĐT đã che]."
        assert own["ward"] == "Phường Bến Nghé"
        assert own["available_from"] == "2026-12-01"
        assert own["posted_at"] is None and own["poster_kind"] is None
        other_listing = client.get(f"/landlord/rooms/{room_id}", headers=OWNER_B)
        assert other_listing.status_code == 404
        other_rooms = client.get("/landlord/rooms", headers=OWNER_B).json()["rooms"]
        assert room_id not in {room["id"] for room in other_rooms}


def test_public_listing_never_shows_phone_digits_from_landlord_text(service):
    # FC-01/F4: the /tin/:id page serves GET /listings/{id} to anonymous visitors;
    # phones in landlord free text must be masked before the room is stored.
    with TestClient(create_app(lambda: service)) as client:
        payload = {"title": "Phòng có gác gần chợ", "city": "TP.HCM", "area": "Quận 1",
                   "area_m2": 18.0, "available": True, "published": True,
                   "quote": {"rent_vnd": 3_000_000, "fees": []},
                   "description": "Liên hệ 0901234567 hoặc zalo 0912 345 678",
                   "house_rules": "Gọi 0987 654 321 trước khi đến.",
                   "features_text": "Xem nhà gọi 0912345678."}
        created = client.post("/landlord/rooms", headers=OWNER_A, json=payload)
        assert created.status_code == 201, created.text
        room_id = created.json()["room"]["id"]
        anonymous = client.get(f"/listings/{room_id}")
        assert anonymous.status_code == 200, anonymous.text
        body = anonymous.text
        for phone in ("0901234567", "0912 345 678", "0987 654 321", "0912345678"):
            assert phone not in body
        assert "[SĐT đã che]" in body
        own = client.get(f"/landlord/rooms/{room_id}", headers=OWNER_A).json()["room"]
        assert own["description"] == "Liên hệ [SĐT đã che] hoặc zalo [SĐT đã che]"
        assert own["house_rules"] == "Gọi [SĐT đã che] trước khi đến."
        assert own["features_text"] == "Xem nhà gọi [SĐT đã che]."
        # PUT replaces the whole payload: an update re-masks the incoming text too.
        from backend.app.models import RoomInput
        editable = {key: own[key] for key in RoomInput.model_fields if key in own}
        edit = {**editable, "expected_revision": own["revision"],
                "description": "Số mới 0987654321", "house_rules": None, "features_text": None}
        updated = client.put(f"/landlord/rooms/{room_id}", headers=OWNER_A, json=edit)
        assert updated.status_code == 200, updated.text
        assert updated.json()["room"]["description"] == "Số mới [SĐT đã che]"
        refreshed = client.get(f"/listings/{room_id}").text
        assert "[SĐT đã che]" in refreshed and "0987654321" not in refreshed


def test_eval_invariants_include_listing_meta_counterfactual(tmp_path):
    from data.generate import generate
    from eval.suites import invariants_report
    dataset, runs = tmp_path / "data", tmp_path / "runs"
    generate(dataset)
    report = invariants_report(dataset, "dev", runs / "invariants.json")
    meta = report["counterfactual"]["listing_meta"]
    assert report["passed"] and report["violations"] == {}
    assert meta["invariant_holds"] and meta["profiles_compared"] == 15
    assert meta["posted_at_past_changed"] == 0 and meta["posted_at_future_changed"] == 0
    assert meta["poster_kind_changed"] == 0


def test_frontend_amenity_labels_match_backend_keys():
    # Same sync mechanism as locations.ts: the backend reads src/types.ts directly.
    import re
    source = (DATA_DIR.parent / "frontend/src/types.ts").read_text(encoding="utf-8")
    block = source.split("export const amenities", 1)[1].split("};", 1)[0]
    keys = set(re.findall(r"^\s*([a-z_0-9]+):", block, re.M))
    assert keys == set(AMENITY_KEYS)


def test_listing_search_supports_posted_desc_sort():
    from datetime import datetime, timedelta, timezone as tz

    from backend.app.listings import ListingQuery, search
    now = datetime.now(tz.utc)
    rooms = []
    for index, days in enumerate((30, 1, None)):
        base = make_room(id=f"lf-sort-{index}", revision=1)
        base = base.model_copy(update={
            "posted_at": None if days is None else now - timedelta(days=days)})
        rooms.append(base)
    result = search(rooms, ListingQuery(city="TP.HCM", sort="posted_desc"))
    order = [item["id"] for item in result["items"]]
    assert order == ["lf-sort-1", "lf-sort-0", "lf-sort-2"]  # newest first, unknown last
