"""FC-04: đo nhanh tải catalog với ~5.000 phòng so với cỡ hiện tại (~2.779).

Không tối ưu trong bước này: chỉ đo. Nạp snapshot nháp (phòng tổng hợp, gắn nhãn
`synthetic: true` — L13) vào SQLite tạm và đo p50/p95 của:

- `catalog.rooms()` lần đầu (lạnh) và lần trúng cache;
- một lượt xếp hạng B1;
- `GET /listings` trang 1 (TestClient trong tiến trình);
- danh sách phòng của chủ nhà (mỗi chủ nhà demo ~1/4 kho).

PostgreSQL local chỉ chạy khi đặt `HOMEMATCH_TEST_DATABASE_URL`; không dùng Neon
(G5/C3). Lệnh: `.venv/bin/python -m data.measure_catalog_load [--rooms 5000]`.
"""
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.catalog import StoredCatalog
from backend.app.main import create_app
from backend.app.models import Profile, Room, Scenario
from backend.app.service import HomeMatchService

TITLE_PARTS = ("Phòng trọ", "Studio", "Căn hộ mini", "Phòng có gác", "Phòng WC riêng")
AREAS = {"TP.HCM": ["Quận 1", "Quận 7", "Bình Thạnh", "Thủ Đức", "Gò Vấp"],
         "Hà Nội": ["Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Nam Từ Liêm", "Hà Đông"]}


def draft_room(index: int, total: int) -> Room:
    """Phòng tổng hợp nháp để đo tải; không phải dữ liệu Chợ Tốt."""
    city = "TP.HCM" if index % 2 == 0 else "Hà Nội"
    apartment = index % 4 == 3
    area = AREAS[city][index % 5]
    landlord = "owner1" if city == "Hà Nội" else "owner2"
    return Room.model_validate({
        "id": f"measure-{index:05d}", "revision": 1,
        "title": f"{TITLE_PARTS[index % 5]} {area} số {index}",
        "city": city, "area": area,
        "room_type": "apartment" if apartment else ("studio" if index % 7 == 0 else "room"),
        "bedrooms": 2 if apartment else None, "capacity": None,
        "area_m2": 15.0 + index % 25,
        "published": True, "available": True,
        "amenities": {key: None for key in (
            "air_conditioning", "private_bathroom", "window", "balcony", "parking", "quiet",
            "washing_machine", "furniture", "pets_allowed", "kitchen", "wifi", "elevator",
            "security_24h", "camera", "loft", "flexible_hours", "no_shared_landlord",
            "water_heater", "fridge")},
        "latitude": 10.75 + index % 50 / 1000, "longitude": 106.66 + index % 40 / 1000,
        "location_accuracy": "approximate", "uncertainty_m": 300.0,
        "quote": {"rent_vnd": 2_500_000 + (index % 40) * 100_000, "deposit_vnd": None,
                  "advance_months": None, "payment_cycle_months": None, "min_lease_months": None,
                  "fees": [], "one_time_vnd": None},
        "source": f"measure://{index}", "synthetic": True,
        "features_text": None, "landlord_id": landlord,
        "description": "Phòng tổng hợp để đo tải catalog (FC-04), không phải tin thật.",
        "posted_at": None, "poster_kind": None,
        "ward": None, "ward_2025": None, "street": None, "available_from": None,
    })


def percentile(samples: list[float], q: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def measure(total: int) -> dict:
    rooms = [draft_room(index, total) for index in range(total)]
    with tempfile.TemporaryDirectory() as directory:
        service = HomeMatchService(Path(directory) / "measure.sqlite")
        try:
            service.catalog.import_rooms(rooms)
            catalog = service.catalog
            assert isinstance(catalog, StoredCatalog)

            def cold_rooms() -> None:
                catalog._payloads = None  # noqa: SLF001 - đo đúng đường nạp lạnh
                catalog.rooms()

            cold_samples = [timed(cold_rooms) for _ in range(5)]
            warm_samples = [timed(catalog.rooms) for _ in range(30)]
            profile = Profile(city="TP.HCM", room_type="room", max_monthly_cost_vnd=50_000_000,
                              scenario=Scenario(people=1))
            rank_samples = [timed(lambda: catalog.rank(profile, method="B1")) for _ in range(30)]
            with TestClient(create_app(lambda: service)) as client:
                def get_listings():
                    response = client.get("/listings", params={"city": "TP.HCM"})
                    assert response.status_code == 200
                    return response

                def get_landlord_rooms():
                    response = client.get("/landlord/rooms",
                                          headers={"Authorization": "Bearer demo-owner2"})
                    assert response.status_code == 200
                    return response

                listing_samples = [timed(get_listings) for _ in range(30)]
                landlord_samples = [timed(get_landlord_rooms) for _ in range(30)]
            return {
                "rooms": total,
                "landlords": len({room.landlord for room in rooms}),
                "cold_rooms_s": summarize(cold_samples),
                "warm_rooms_s": summarize(warm_samples),
                "rank_b1_s": summarize(rank_samples),
                "get_listings_page1_s": summarize(listing_samples),
                "landlord_room_list_s": summarize(landlord_samples),
            }
        finally:
            service.close()


def timed(operation):
    start = time.perf_counter()
    result = operation()
    return (time.perf_counter() - start), result


def summarize(pairs) -> dict:
    samples = [duration for duration, _ in pairs]
    return {"p50": round(percentile(samples, 0.5) * 1000, 1),
            "p95": round(percentile(samples, 0.95) * 1000, 1),
            "median_ms": round(statistics.median(samples) * 1000, 1)}


def main() -> None:
    # Same offline posture as backend/tests/conftest.py: demo auth, no LLM, no jobs.
    import os
    for key, value in (("HOMEMATCH_AUTH_MODE", "demo"), ("HOMEMATCH_LLM_MODE", "demo"),
                       ("HOMEMATCH_MATCHING_METHOD", "B1"), ("HOMEMATCH_EMBEDDING_MODE", "disabled"),
                       ("HOMEMATCH_JOBS_INTERVAL_SECONDS", "0")):
        os.environ.setdefault(key, value)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rooms", type=int, default=5000)
    arguments = parser.parse_args()
    results = [measure(arguments.rooms), measure(2779)]
    print(json.dumps({"note": "phòng tổng hợp nháp, SQLite; PG local chỉ chạy khi có "
                              "HOMEMATCH_TEST_DATABASE_URL (không dùng Neon)",
                      "storage": "sqlite",
                      "postgres_measured": bool(__import__("os").getenv("HOMEMATCH_TEST_DATABASE_URL")),
                      "runs": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
