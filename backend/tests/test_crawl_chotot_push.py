"""CA-03: push_snapshot stores every raw ad in chotot_raw_ads (batched) and
leaves chotot_listings.raw NULL for new snapshots; the raw size cap stops the
push before any write; pull_snapshot keeps working for legacy snapshots.

PostgreSQL only, via the local test DSN (HOMEMATCH_TEST_DATABASE_URL); the
tests skip when it is unset. Never Neon, never the crawl database, no network.
"""
import hashlib
import json

import psycopg
import pytest

from data.crawl_chotot import pull_snapshot, push_snapshot

SNAPSHOT_ID = "chotot-test-2.4"


def base_ad(ad_id, **overrides):
    ad = {"ad_id": ad_id, "list_id": 87761600 + ad_id, "subject": f"Phòng trọ số {ad_id}",
          "body": "Phòng mới.", "price": 3_000_000, "size": 20,
          "region_name": "TP Hồ Chí Minh", "area_name": "Quận 7"}
    ad.update(overrides)
    return ad


@pytest.fixture
def snapshot_dir(tmp_path):
    """A tiny snapshot: 3 raw ads, one rejected by to_room (price=99) so the raw
    table must hold more ads than the catalog."""
    directory = tmp_path / SNAPSHOT_ID
    (directory / "raw").mkdir(parents=True)
    ads = [base_ad(1), base_ad(2), base_ad(3, price=99)]
    (directory / "raw" / "page-000.json").write_text(
        json.dumps(ads, ensure_ascii=False, indent=1), encoding="utf-8")
    room = {"id": "chotot-1", "revision": 1, "title": "Phòng trọ số 1", "city": "TP.HCM",
            "area": "Quận 7", "room_type": "room", "bedrooms": None, "capacity": None,
            "area_m2": 20.0, "published": True, "available": True, "amenities": {},
            "latitude": None, "longitude": None, "location_accuracy": "area_only",
            "uncertainty_m": None, "quote": {"rent_vnd": 3000000, "deposit_vnd": None,
                                             "advance_months": None, "payment_cycle_months": None,
                                             "min_lease_months": None, "fees": [], "one_time_vnd": None},
            "source": "https://www.chotot.com/87761601.htm", "synthetic": False,
            "features_text": None, "landlord_id": "owner2", "description": "Phòng mới.",
            "posted_at": "2026-10-30T04:00:00+00:00", "poster_kind": "individual",
            "ward": None, "ward_2025": None, "street": None, "available_from": None}
    catalog = {"notice": "test fixture", "snapshot_id": SNAPSHOT_ID, "rooms": [room]}
    catalog_path = directory / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    manifest = {"snapshot_id": SNAPSHOT_ID, "captured_at": "2026-11-07T08:00:00+07:00",
                "crawler_version": "2.4", "rooms": 1, "raw_ads": 3,
                "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest()}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    return directory


def test_push_stores_every_raw_ad_and_keeps_listings_raw_null(snapshot_dir, postgres_storage):
    result = push_snapshot(snapshot_dir, postgres_storage, log=lambda *_: None)
    assert result == {"snapshot_id": SNAPSHOT_ID, "rooms_on_db": 1, "raw_on_db": 3}
    with psycopg.connect(postgres_storage) as connection:
        rows = connection.execute(
            "SELECT ad_id, list_id, raw->>'subject' FROM chotot_raw_ads WHERE snapshot_id=%s "
            "ORDER BY ad_id", (SNAPSHOT_ID,)).fetchall()
        assert [row[0] for row in rows] == [1, 2, 3]
        assert rows[2][2] == "Phòng trọ số 3"  # the catalog-rejected ad is still in raw
        assert connection.execute(
            "SELECT raw FROM chotot_listings WHERE snapshot_id=%s", (SNAPSHOT_ID,)).fetchall() == [(None,)]
        listing = connection.execute(
            "SELECT room->>'id' FROM chotot_listings WHERE snapshot_id=%s", (SNAPSHOT_ID,)).fetchone()
        assert listing == ("chotot-1",)


def test_republish_same_hash_is_a_noop(snapshot_dir, postgres_storage):
    push_snapshot(snapshot_dir, postgres_storage, log=lambda *_: None)
    logs: list[str] = []
    push_snapshot(snapshot_dir, postgres_storage, log=logs.append)
    assert any("bỏ qua" in line for line in logs)
    with psycopg.connect(postgres_storage) as connection:
        assert connection.execute("SELECT count(*) FROM chotot_raw_ads WHERE snapshot_id=%s",
                                  (SNAPSHOT_ID,)).fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM chotot_listings WHERE snapshot_id=%s",
                                  (SNAPSHOT_ID,)).fetchone()[0] == 1


def test_raw_size_cap_stops_before_any_write(snapshot_dir, postgres_storage):
    with pytest.raises(SystemExit, match="max-raw-mb"):
        push_snapshot(snapshot_dir, postgres_storage, log=lambda *_: None, max_raw_mb=0.000001)
    with psycopg.connect(postgres_storage) as connection:
        assert connection.execute("SELECT to_regclass('chotot_snapshots')").fetchone()[0] is None or \
            connection.execute("SELECT count(*) FROM chotot_snapshots WHERE snapshot_id=%s",
                               (SNAPSHOT_ID,)).fetchone()[0] == 0


def test_pull_snapshot_restores_legacy_snapshot(tmp_path, postgres_storage):
    # A legacy (2.3-style) row: catalog/manifest texts only, no raw ads table rows.
    catalog_text = json.dumps({"snapshot_id": "chotot-legacy", "rooms": []}, ensure_ascii=False)
    manifest_text = json.dumps({"snapshot_id": "chotot-legacy", "crawler_version": "2.3",
                                "rooms": 0}, ensure_ascii=False)
    with psycopg.connect(postgres_storage) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS chotot_snapshots (
                snapshot_id text PRIMARY KEY,
                captured_at timestamptz NOT NULL,
                catalog_sha256 text NOT NULL,
                rooms integer NOT NULL,
                manifest jsonb NOT NULL,
                uploaded_at timestamptz NOT NULL DEFAULT now()
            );
            ALTER TABLE chotot_snapshots ADD COLUMN IF NOT EXISTS catalog_json text;
            ALTER TABLE chotot_snapshots ADD COLUMN IF NOT EXISTS manifest_json text;
        """)
        connection.execute(
            "INSERT INTO chotot_snapshots(snapshot_id, captured_at, catalog_sha256, rooms, manifest, "
            "catalog_json, manifest_json) VALUES (%s, now(), %s, 0, '{}'::jsonb, %s, %s) "
            "ON CONFLICT (snapshot_id) DO NOTHING",
            ("chotot-legacy", hashlib.sha256(catalog_text.encode("utf-8")).hexdigest(),
             catalog_text, manifest_text))
    result = pull_snapshot("chotot-legacy", tmp_path, postgres_storage, force=True)
    assert result["status"] == "restored"
    assert (tmp_path / "chotot-legacy" / "catalog.json").read_text(encoding="utf-8") == catalog_text
    assert (tmp_path / "chotot-legacy" / "manifest.json").read_text(encoding="utf-8") == manifest_text
