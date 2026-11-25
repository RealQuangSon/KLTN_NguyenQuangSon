"""LOC-001: kiểm tra `data/places.json` — cấu trúc (luôn chạy) và đối chiếu Nominatim (`--live`).

    python -m data.verify_places                     # chỉ kiểm cấu trúc, không gọi mạng
    python -m data.verify_places --live              # thêm đối chiếu Nominatim (OSM)
    python -m data.verify_places --live --only hn-hust,hcm-hcmut

Mỗi điểm tra `https://nominatim.openstreetmap.org/search` (format=jsonv2,
countrycodes=vn, limit=3, viewbox + bounded theo khung bao thành phố). Chỉ gửi
tên điểm hoặc `geocode_query` (tên + đường + quận) — không email, không tên
người; User-Agent chung `HomeMatch-localhost/1.0`; cách nhau ≥ 1,1 giây. Báo cáo
in id, khoảng lệch so với tọa độ hiện tại và `display_name` để người duyệt từng
kết quả: script KHÔNG tự ghi đè tọa độ.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path

PLACES_PATH = Path(__file__).resolve().parent / "places.json"
USER_AGENT = "HomeMatch-localhost/1.0"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_S = 1.1
KINDS = {"school", "hospital", "transit", "mall", "work", "area"}
SOURCES = {"osm", "manual"}
CITIES = {"Hà Nội", "TP.HCM"}
MIN_UNCERTAINTY_M = 150
# (lon_min, lat_min, lon_max, lat_max) — trùng backend/app/geocode.py.
CITY_BBOX = {"Hà Nội": (105.28, 20.55, 106.02, 21.40), "TP.HCM": (106.35, 10.35, 107.05, 11.20)}


def fold(value: str) -> str:
    text = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def load_places(path: Path = PLACES_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["places"]


def check_structure(places: list[dict]) -> list[str]:
    """Danh sách lỗi cấu trúc (rỗng = hợp lệ)."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    alias_owner: dict[tuple[str, str], str] = {}
    for place in places:
        pid = place.get("id", "?")
        if pid in seen_ids:
            errors.append(f"{pid}: id trùng")
        seen_ids.add(pid)
        if place.get("city") not in CITIES:
            errors.append(f"{pid}: city không hợp lệ")
        if place.get("kind") not in KINDS:
            errors.append(f"{pid}: thiếu hoặc sai kind")
        if place.get("source") not in SOURCES:
            errors.append(f"{pid}: thiếu hoặc sai source")
        if not place.get("verified_at"):
            errors.append(f"{pid}: thiếu verified_at")
        if not isinstance(place.get("uncertainty_m"), (int, float)) or place["uncertainty_m"] < MIN_UNCERTAINTY_M:
            errors.append(f"{pid}: uncertainty_m < {MIN_UNCERTAINTY_M}")
        lat, lon = place.get("latitude"), place.get("longitude")
        box = CITY_BBOX.get(place.get("city"))
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not box \
                or not (box[0] <= lon <= box[2] and box[1] <= lat <= box[3]):
            errors.append(f"{pid}: tọa độ ngoài khung thành phố")
        if not place.get("names"):
            errors.append(f"{pid}: thiếu names")
        for alias in place.get("aliases") or []:
            if alias != fold(alias):
                errors.append(f"{pid}: alias '{alias}' chưa fold (không dấu, lowercase)")
            owner = alias_owner.setdefault((place.get("city", ""), fold(alias)), pid)
            if owner != pid:
                errors.append(f"{pid}: alias '{alias}' trùng với {owner} cùng thành phố")
    return errors


def query_for(place: dict) -> str:
    return place.get("geocode_query") or place["names"][0]


def nominatim_fetch(query: str, city: str) -> list[dict]:
    import httpx
    left, bottom, right, top = CITY_BBOX[city]
    params = {"q": query, "format": "jsonv2", "countrycodes": "vn", "limit": 3,
              "viewbox": f"{left},{top},{right},{bottom}", "bounded": 1, "accept-language": "vi"}
    response = httpx.get(NOMINATIM_URL, params=params, timeout=10.0,
                         headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


def run_live(places: list[dict], fetch=nominatim_fetch, sleep=time.sleep, out=print) -> list[dict]:
    rows = []
    last = None
    for place in places:
        if last is not None:
            wait = MIN_INTERVAL_S - (time.monotonic() - last)
            if wait > 0:
                sleep(wait)
        last = time.monotonic()
        query = query_for(place)
        try:
            hits = fetch(query, place["city"])
        except Exception as error:  # noqa: BLE001
            out(f"{place['id']}\tERROR\t{error}")
            rows.append({"id": place["id"], "query": query, "error": str(error), "hits": []})
            continue
        if not hits:
            out(f"{place['id']}\tNO_RESULT\tq={query!r}")
        row_hits = []
        for hit in hits:
            lat, lon = float(hit["lat"]), float(hit["lon"])
            offset = round(distance_m(place["latitude"], place["longitude"], lat, lon))
            out(f"{place['id']}\t{offset} m\t(u={place['uncertainty_m']})\t{lat:.5f},{lon:.5f}\t{hit.get('display_name', '')[:140]}")
            row_hits.append({"lat": lat, "lon": lon, "offset_m": offset,
                             "display_name": hit.get("display_name"), "type": hit.get("addresstype"),
                             "boundingbox": hit.get("boundingbox")})
        rows.append({"id": place["id"], "query": query, "hits": row_hits})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--live", action="store_true", help="đối chiếu Nominatim (gọi mạng, 1 yêu cầu/1,1 giây)")
    parser.add_argument("--only", help="danh sách id, cách nhau bởi dấu phẩy")
    parser.add_argument("--path", type=Path, default=PLACES_PATH)
    parser.add_argument("--json-out", type=Path, help="ghi kết quả live ra JSON")
    args = parser.parse_args(argv)
    places = load_places(args.path)
    errors = check_structure(places)
    for error in errors:
        print("LỖI", error)
    print(f"{len(places)} điểm, {len(errors)} lỗi cấu trúc")
    if args.live:
        wanted = {item.strip() for item in args.only.split(",")} if args.only else None
        selected = [place for place in places if wanted is None or place["id"] in wanted]
        rows = run_live(selected)
        if args.json_out:
            args.json_out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
