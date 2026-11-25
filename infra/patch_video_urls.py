"""Công cụ vá một lần: sửa `source_videos` bị che nhầm trong snapshot
chotot-2026-11-07-5k-r2.

Nguyên nhân: `_clean_raw_string` cũ chỉ miễn che URL chotot.com nên dãy số
trong mã video videodelivery.net bị mask_pii coi là SĐT; `rebuild_catalog` đọc
raw đã che. Catalog `chotot-2026-11-07-5k` (cào trực tiếp) vẫn có URL đúng.

Mặc định CHỈ in số phòng sẽ đổi (dry-run). Cờ ghi rõ ràng:
- `--write`         : vá file catalog.json + manifest của r2 ở máy;
- `--apply-neon`    : vá Neon trong một transaction cho mỗi database
                      (chotot_listings + chotot_snapshots của r2 trên crawl DB,
                      hm_rooms trên app DB được chỉ định qua --app-database).

Không đụng chotot_raw_ads, không đổi revision, không đổi trường nào khác.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.crawl_chotot import is_stream_video_url  # noqa: E402

R2_SNAPSHOT = "chotot-2026-11-07-5k-r2"
SOURCE_SNAPSHOT = "chotot-2026-11-07-5k"


def valid_entry(entry: dict) -> bool:
    return (isinstance(entry, dict)
            and is_stream_video_url(entry.get("url"))
            and is_stream_video_url(entry.get("thumbnail"), thumbnail=True))


def malformed_rooms(catalog: dict) -> list[dict]:
    return [room for room in catalog["rooms"]
            if any(not valid_entry(entry) for entry in room.get("source_videos") or [])]


def build_patch(r2_path: Path, source_path: Path) -> tuple[dict[str, list[dict]], dict]:
    """Trả về ({room_id: source_videos mới}, thống kê). Phòng không tìm được ở
    catalog nguồn hoặc nguồn vẫn sai dạng → danh sách rỗng (B-1)."""
    r2_catalog = json.loads(r2_path.read_text(encoding="utf-8"))
    source = {room["id"]: room for room in
              json.loads(source_path.read_text(encoding="utf-8"))["rooms"]}
    patches: dict[str, list[dict]] = {}
    stats = {"restored_from_source": 0, "emptied": 0}
    for room in malformed_rooms(r2_catalog):
        donor = source.get(room["id"], {}).get("source_videos") or []
        if donor and all(valid_entry(entry) for entry in donor):
            patches[room["id"]] = donor
            stats["restored_from_source"] += 1
        else:
            patches[room["id"]] = []
            stats["emptied"] += 1
    return patches, stats


def _patch_catalog_file(r2_path: Path, patches: dict[str, list[dict]]) -> dict:
    """Đổi đúng `source_videos` của các phòng được chỉ định; trả manifest mới."""
    catalog_path = r2_path / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    changed = 0
    for room in catalog["rooms"]:
        if room["id"] in patches:
            room["source_videos"] = patches[room["id"]]
            changed += 1
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    manifest_path = r2_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["catalog_sha256"] = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    manifest["videos_restored_from"] = SOURCE_SNAPSHOT
    # Chạy lại tool không được ghi đè videos_restored bằng 0 —
    # giữ giá trị đã ghi (đúng là 114 của snapshot r2) khi lần chạy này không vá gì.
    if changed or "videos_restored" not in manifest:
        manifest["videos_restored"] = changed
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"rooms_patched": changed, "catalog_sha256": manifest["catalog_sha256"]}


def patch_neon(patches: dict[str, list[dict]], manifest_result: dict,
               app_database: str, log=print) -> dict:
    """C-3: vá Neon — một transaction cho mỗi database, chỉ đúng các bản ghi của
    các phòng được vá. chotot_raw_ads không đụng tới; revision không đổi."""
    import psycopg
    from psycopg.types.json import Jsonb

    crawl_url = os.getenv("HOMEMATCH_CRAWL_DATABASE_URL")
    app_url = os.getenv("HOMEMATCH_DATABASE_URL")
    if not crawl_url or not app_url:
        raise SystemExit("Cần HOMEMATCH_CRAWL_DATABASE_URL và HOMEMATCH_DATABASE_URL trong môi trường.")
    head, _, _ = app_url.rpartition("/")
    app_url = f"{head}/{app_database}"
    r2_dir = ROOT / ".local" / "chotot" / R2_SNAPSHOT
    catalog_text = (r2_dir / "catalog.json").read_text(encoding="utf-8")
    manifest_text = (r2_dir / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    rooms_by_id = {room["id"]: room for room in json.loads(catalog_text)["rooms"]}
    result = {"chotot_listings": 0, "chotot_snapshots": 0, "hm_rooms": 0}
    with psycopg.connect(crawl_url, connect_timeout=20) as connection:
        with connection.transaction():
            for room_id, videos in patches.items():
                room = rooms_by_id[room_id]
                cursor = connection.execute(
                    "UPDATE chotot_listings SET room=%s WHERE snapshot_id=%s AND room_id=%s",
                    (Jsonb(room), R2_SNAPSHOT, room_id))
                result["chotot_listings"] += cursor.rowcount
            cursor = connection.execute(
                "UPDATE chotot_snapshots SET catalog_sha256=%s, manifest=%s, catalog_json=%s, "
                "manifest_json=%s WHERE snapshot_id=%s",
                (manifest["catalog_sha256"], Jsonb(manifest), catalog_text, manifest_text,
                 R2_SNAPSHOT))
            result["chotot_snapshots"] = cursor.rowcount
    with psycopg.connect(app_url, connect_timeout=20) as connection:
        with connection.transaction():
            for room_id, videos in patches.items():
                room = rooms_by_id[room_id]
                row = connection.execute("SELECT payload_json FROM hm_rooms WHERE id=%s",
                                         (room_id,)).fetchone()
                if row is None:
                    continue
                payload = json.loads(row[0])
                if payload.get("revision") != room["revision"]:
                    raise SystemExit(f"{room_id}: revision trên DB khác catalog; dừng, không vá.")
                payload["source_videos"] = videos
                cursor = connection.execute("UPDATE hm_rooms SET payload_json=%s WHERE id=%s",
                                            (json.dumps(payload, ensure_ascii=False), room_id))
                result["hm_rooms"] += cursor.rowcount
    log(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="Vá file catalog.json + manifest của r2 ở máy (mặc định chỉ in).")
    parser.add_argument("--apply-neon", action="store_true",
                        help="Vá cả Neon (chotot_listings/chotot_snapshots của r2 và hm_rooms "
                             "của --app-database) sau khi đã --write.")
    parser.add_argument("--app-database", default="homematch_5k2",
                        help="Database app chứa hm_rooms cần vá (mặc định homematch_5k2).")
    arguments = parser.parse_args()
    r2_path = ROOT / ".local" / "chotot" / R2_SNAPSHOT
    source_path = ROOT / ".local" / "chotot" / SOURCE_SNAPSHOT
    patches, stats = build_patch(r2_path / "catalog.json", source_path / "catalog.json")
    print(json.dumps({"rooms_to_patch": len(patches), **stats}, ensure_ascii=False))
    if not arguments.write:
        print("DRY-RUN: chưa ghi gì. Chạy lại với --write để vá file local.")
        return
    result = _patch_catalog_file(r2_path, patches)
    print(json.dumps({"local": result}, ensure_ascii=False))
    if arguments.apply_neon:
        patch_neon(patches, result, arguments.app_database)


if __name__ == "__main__":
    main()
