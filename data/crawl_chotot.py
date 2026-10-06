"""Crawler tin phòng trọ TP.HCM từ API công khai của Chợ Tốt.

Xuất catalog JSON tương thích `backend.app.models.Room` để nạp bằng
`python -m backend.manage import --catalog ...`. Raw response từng trang nằm
trong `.local/` (không commit). Chỉ dùng cho mục đích nghiên cứu KLTN;
tuân thủ khoảng nghỉ giữa các request và không thu thập liên hệ người bán.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from backend.app.models import Room

ROOT = Path(__file__).resolve().parents[1]
LISTING_URL = "https://gateway.chotot.com/v1/public/ad-listing"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) KLTN-research-crawler"
REGION_HCM = 13000
CATEGORY_PHONG_TRO = 1050
PAGE_SIZE = 50
VIETNAM_TZ = timezone(timedelta(hours=7))

# Từ khoá nhận diện tiện ích: so khớp trên bản bỏ dấu, casefold; null = không xác định được.
KEYWORD_AMENITIES: dict[str, list[str]] = {
    "air_conditioning": ["may lanh", "dieu hoa"],
    "private_bathroom": ["wc rieng", "ve sinh rieng", "toilet rieng", "khep kin"],
    "window": ["cua so", "ban cong"],
    "parking": ["gui xe", "cho de xe", "de xe free", "ham xe", "parking"],
    "quiet": ["yen tinh", "khu vuc yen"],
    "washing_machine": ["may giat"],
    "balcony": ["ban cong rieng"],
    "furniture": ["noi that"],
    "pets_allowed": ["nuoi thu cung", "pet"],
}


def strip_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", unicodedata.normalize("NFC", value).casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def fetch_page(offset: int, limit: int, region: int, timeout: float) -> dict:
    query = (f"?region_v2={region}&cg={CATEGORY_PHONG_TRO}&w=1"
             f"&limit={limit}&o={offset}&st=s&key_param=&f=p")
    request = urllib.request.Request(LISTING_URL + query, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_amenities(text: str) -> dict[str, bool | None]:
    haystack = strip_diacritics(text)
    amenities: dict[str, bool | None] = {}
    for name, keywords in KEYWORD_AMENITIES.items():
        amenities[name] = any(keyword in haystack for keyword in keywords) or None
    return amenities


def to_room(ad: dict) -> dict:
    ad_id = ad.get("ad_id")
    room_id = f"chotot-{ad_id}"
    subject = str(ad.get("subject") or "").strip()
    body = str(ad.get("body") or "")
    size = ad.get("size")
    price = ad.get("price")
    deposit = ad.get("deposit")
    latitude, longitude = ad.get("latitude"), ad.get("longitude")
    has_coords = isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))
    area_name = str(ad.get("area_name") or "").strip() or "Không rõ"
    # Bổ sung ngữ vị vào title vì Room chỉ giữ các trường schema (extra="forbid").
    title = f"{subject} ({area_name}" + (f", {ad['ward_name']})" if ad.get("ward_name") else ")")
    rent = int(price)
    return {
        "id": room_id,
        "revision": 1,
        "title": title,
        "city": "TP.HCM",
        "area": area_name,
        "room_type": "studio" if "studio" in strip_diacritics(subject) else "room",
        "capacity": None,
        "area_m2": float(size),
        "published": True,
        "available": True,
        "amenities": detect_amenities(f"{subject}\n{body}"),
        "latitude": float(latitude) if has_coords else None,
        "longitude": float(longitude) if has_coords else None,
        "location_accuracy": "approximate" if has_coords else "area_only",
        "uncertainty_m": 300.0 if has_coords else None,
        "quote": {
            "rent_vnd": rent,
            "deposit_vnd": int(deposit) if deposit else None,
            "advance_months": None,
            "fees": [],
            "one_time_vnd": None,
        },
        "source": f"chotot://ad/{ad_id}",
        "synthetic": False,
    }


def crawl(pages: int, limit: int, region: int, sleep_s: float, timeout: float,
          raw_dir: Path) -> tuple[list[dict], dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    kept, skipped, seen = [], {}, set()
    for page in range(pages):
        offset = page * limit
        payload = fetch_page(offset, limit, region, timeout)
        ads = payload.get("ads") or []
        if not ads:
            break
        stamp = datetime.now(VIETNAM_TZ).strftime("%Y%m%dT%H%M%S")
        (raw_dir / f"page-{page:03d}-{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        for ad in ads:
            ad_id = ad.get("ad_id")
            if ad_id in seen:
                skipped["duplicate"] = skipped.get("duplicate", 0) + 1
                continue
            seen.add(ad_id)
            price = ad.get("price")
            size = ad.get("size")
            if not isinstance(price, (int, float)) or price <= 0:
                skipped["price_missing_or_zero"] = skipped.get("price_missing_or_zero", 0) + 1
                continue
            if not isinstance(size, (int, float)) or size <= 0:
                skipped["size_missing"] = skipped.get("size_missing", 0) + 1
                continue
            try:
                room = Room.model_validate(to_room(ad))
            except Exception as error:  # noqa: BLE001 - ghi nhận rồi bỏ qua tin lỗi schema
                skipped[f"schema:{type(error).__name__}"] = skipped.get(f"schema:{type(error).__name__}", 0) + 1
                continue
            kept.append(room.model_dump(mode="json"))
        if page + 1 < pages:
            time.sleep(sleep_s)
    return kept, {"seen": len(seen), "kept": len(kept), "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=6, help="Số trang crawl (mỗi trang tối đa 50 tin).")
    parser.add_argument("--limit", type=int, default=PAGE_SIZE, help="Số tin mỗi trang, tối đa 50.")
    parser.add_argument("--region", type=int, default=REGION_HCM, help="Mã region_v2, mặc định TP.HCM.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Nghỉ giữa các trang (giây).")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-rent", type=int, default=500_000)
    parser.add_argument("--max-rent", type=int, default=30_000_000)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "crawled" / "chotot_rooms.json")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / ".local" / "crawled-raw" / "chotot")
    arguments = parser.parse_args()
    rooms, stats = crawl(arguments.pages, min(arguments.limit, 50), arguments.region,
                         arguments.sleep, arguments.timeout, arguments.raw_dir)
    in_range = [room for room in rooms
                if arguments.min_rent <= room["quote"]["rent_vnd"] <= arguments.max_rent]
    stats["out_of_rent_range"] = len(rooms) - len(in_range)
    payload = {
        "notice": ("Tin công khai crawl từ Chợ Tốt (danh mục Phòng trọ) phục vụ nghiên cứu KLTN; "
                   "không phải dữ liệu HubHome. Giá/tiện ích theo nội dung tin đăng, chưa kiểm chứng thực địa."),
        "source_site": "chotot.com",
        "crawled_at": datetime.now(VIETNAM_TZ).isoformat(timespec="seconds"),
        "stats": stats,
        "rooms": sorted(in_range, key=lambda room: room["id"]),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(arguments.output.relative_to(ROOT)), "stats": stats},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
