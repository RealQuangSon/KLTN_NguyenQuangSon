"""LOC-001: tra địa danh trên bản đồ cho `find_place` khi danh mục tĩnh không có.

Nguồn: Goong Geocode (key REST) hoặc Nominatim (OpenStreetMap). Chỉ gửi ra ngoài
TÊN địa danh đã bỏ PII, kèm tên thành phố; câu có số nhà hay dấu hiệu liên lạc
thì không gửi. Không gửi session id, user id hay tọa độ nào. Lỗi mạng/HTTP coi
như không tìm thấy, không bao giờ ném ra ngoài tool. `HOMEMATCH_GEOCODER=off`
(mặc định của test) không gọi mạng.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Callable

from .locations import fold

PROVIDERS = ("auto", "nominatim", "goong", "off")
USER_AGENT = "HomeMatch-localhost/1.0"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GOONG_URL = "https://rsapi.goong.io/geocode"
TIMEOUT_S = 3.0
MIN_INTERVAL_S = 1.1          # Nominatim: tối đa 1 yêu cầu/giây
CACHE_SIZE = 512
MAX_QUERY_CHARS = 80
UNCERTAINTY_RANGE_M = (150.0, 2000.0)

# (lon_min, lat_min, lon_max, lat_max) — khung bao thô của hai thành phố.
CITY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "Hà Nội": (105.28, 20.55, 106.02, 21.40),
    "TP.HCM": (106.35, 10.35, 107.05, 11.20),
}

# fetch(url, params, timeout_s) -> (http_status, json_body | None)
Fetch = Callable[[str, dict, float], tuple[int, object]]

_LEADING = re.compile(r"^(?:gần|gan|cạnh|canh|sát|sat|quanh|ở gần|o gan|gần khu|near)\s+", re.I)
# Số nhà / dấu hiệu địa chỉ riêng: không gửi ra ngoài.
_ADDRESS_PATTERNS = (
    re.compile(r"\b(?:số|so|sn)\s*\d", re.I),
    re.compile(r"\b\d+[a-zA-Z]?\s*[/-]\s*\d+"),
    re.compile(r"\b(?:ngõ|ngo|ngách|ngach|hẻm|hem|kiệt|kiet|tổ|to|khu phố|kp|ấp|ap)\s*\d", re.I),
    re.compile(r"\b\d+[a-zA-Z]?\s+(?:ngõ|ngo|ngách|ngach|hẻm|hem|đường|duong|phố|pho|đ\.)\b", re.I),
    re.compile(r"^\s*\d+[a-zA-Z]?\s+[^\d\s]"),
    re.compile(r"\b(?:tầng|tang|lầu|lau|phòng|phong|căn hộ|can ho|block|tòa|toa)\s*[a-zA-Z]?\d", re.I),
)
_CONTACT = re.compile(r"@|(?<!\d)(?:\+84|0)(?:[ .-]*\d){8,10}(?!\d)|\d{6,}")
_GENERIC_TOKENS = {"dai", "hoc", "dh", "truong", "benh", "vien", "bv", "khu", "cong", "nghiep",
                   "ben", "xe", "ga", "chung", "cu", "cho", "trung", "tam", "thuong", "mai",
                   "quan", "phuong", "cong", "ty", "hoc", "vien", "kcn", "tttm", "san", "bay",
                   "va", "cua", "o", "tai", "thanh", "pho", "ha", "noi", "ho", "chi", "minh",
                   "tp", "hcm", "sai", "gon"}
_COARSE_TYPES = {"country", "state", "region", "province", "city", "municipality", "county",
                 "state_district", "continent", "archipelago"}
_AREA_TYPES = {"suburb", "city_district", "district", "borough", "quarter", "neighbourhood",
               "neighborhood", "village", "town", "ward", "hamlet", "city_block"}


def sanitize_query(text: str) -> tuple[str | None, str | None]:
    """(tên địa danh an toàn để gửi, lý do không gửi). Bỏ chữ "gần", cắt 80 ký tự."""
    value = " ".join(str(text or "").split())
    value = _LEADING.sub("", value).strip(" ,.;:-")
    if not value:
        return None, "empty"
    if _CONTACT.search(value) or any(pattern.search(value) for pattern in _ADDRESS_PATTERNS):
        return None, "address_not_sent"
    from .interpreter import redact
    if redact(value) != value:
        return None, "address_not_sent"
    return value[:MAX_QUERY_CHARS], None


def _meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


def in_city(city: str, latitude: float, longitude: float) -> bool:
    box = CITY_BBOX.get(city)
    return bool(box) and box[0] <= longitude <= box[2] and box[1] <= latitude <= box[3]


def city_of(latitude: float, longitude: float) -> str | None:
    return next((city for city in CITY_BBOX if in_city(city, latitude, longitude)), None)


def short_label(item: dict) -> str:
    name = str(item.get("name") or "").strip()
    if not name:
        name = str(item.get("display_name") or "").split(",")[0].strip()
    return name[:80]


def uncertainty_from_bbox(box) -> float | None:
    """Nominatim boundingbox [south, north, west, east] → nửa đường chéo, kẹp [150, 2000]."""
    try:
        south, north, west, east = (float(value) for value in box)
    except (TypeError, ValueError):
        return None
    half_diagonal = _meters(south, west, north, east) / 2
    low, high = UNCERTAINTY_RANGE_M
    return round(min(max(half_diagonal, low), high), 0)


def nominatim_params(query: str, city: str, limit: int = 3) -> dict:
    left, bottom, right, top = CITY_BBOX[city]
    return {"q": query, "format": "jsonv2", "countrycodes": "vn", "limit": limit,
            "viewbox": f"{left},{top},{right},{bottom}", "bounded": 1,
            "accept-language": "vi"}


def _matches_query(query: str, label: str, display_name: str) -> bool:
    """Chặn khớp tự do vô nghĩa: ít nhất một từ riêng của tên phải có trong kết quả."""
    tokens = [token for token in re.findall(r"[a-z0-9]+", fold(query)) if token not in _GENERIC_TOKENS]
    if not tokens:
        return True
    haystack = fold(f"{label} {display_name}")
    return any(token in haystack for token in tokens)


def _http_fetch(url: str, params: dict, timeout_s: float) -> tuple[int, object]:
    import httpx
    response = httpx.get(url, params=params, timeout=timeout_s,
                         headers={"User-Agent": USER_AGENT, "Accept-Language": "vi"})
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


class Geocoder:
    """Một instance mỗi HomeMatchService; cache LRU và hạn mức trong process."""

    def __init__(self, provider: str = "auto", goong_key: str | None = None,
                 fetch: Fetch | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, cache_size: int = CACHE_SIZE):
        if provider not in PROVIDERS:
            raise ValueError(f"HOMEMATCH_GEOCODER phải là một trong {PROVIDERS}")
        self.provider = provider
        self.goong_key = goong_key or None
        self.fetch = fetch or _http_fetch
        self.clock = clock
        self.sleep = sleep
        self.cache_size = cache_size
        self._goong_denied = False
        self._lock = threading.Lock()
        self._last_nominatim: float | None = None
        self._cache: OrderedDict[tuple[str, str], dict] = OrderedDict()

    @classmethod
    def from_env(cls) -> "Geocoder":
        return cls(provider=os.getenv("HOMEMATCH_GEOCODER", "auto").strip().lower(),
                   goong_key=(os.getenv("GOONG_API_KEY") or "").strip() or None)

    @property
    def enabled(self) -> bool:
        return self.provider != "off"

    # ---- nguồn ----
    def _wait_turn(self) -> None:
        with self._lock:
            now = self.clock()
            if self._last_nominatim is not None:
                delay = MIN_INTERVAL_S - (now - self._last_nominatim)
                if delay > 0:
                    self.sleep(delay)
            self._last_nominatim = self.clock()

    def _nominatim(self, query: str, city: str) -> list[dict]:
        self._wait_turn()
        status, body = self.fetch(NOMINATIM_URL, nominatim_params(query, city), TIMEOUT_S)
        if status != 200 or not isinstance(body, list):
            raise RuntimeError(f"nominatim {status}")
        found = []
        for item in body:
            parsed = self._parse_nominatim(item, query, city)
            if parsed:
                found.append(parsed)
        return found

    @staticmethod
    def _parse_nominatim(item: dict, query: str, city: str) -> dict | None:
        try:
            latitude, longitude = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        if not in_city(city, latitude, longitude):
            return None
        addresstype = str(item.get("addresstype") or "")
        if addresstype in _COARSE_TYPES:
            return None
        label = short_label(item)
        if not label or not _matches_query(query, label, str(item.get("display_name") or "")):
            return None
        kind = "area" if (addresstype in _AREA_TYPES or item.get("category") == "boundary") else "point"
        return {"label": label, "city": city, "latitude": round(latitude, 6),
                "longitude": round(longitude, 6), "kind": kind,
                "uncertainty_m": uncertainty_from_bbox(item.get("boundingbox")) or 300.0}

    def _goong(self, query: str, city: str) -> list[dict]:
        status, body = self.fetch(GOONG_URL, {"address": f"{query}, {city}", "api_key": self.goong_key},
                                  TIMEOUT_S)
        if status in (401, 403):
            self._goong_denied = True
            raise RuntimeError("goong denied")
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"goong {status}")
        found = []
        for item in (body.get("results") or [])[:3]:
            try:
                location = item["geometry"]["location"]
                latitude, longitude = float(location["lat"]), float(location["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if not in_city(city, latitude, longitude):
                continue
            label = str(item.get("name") or str(item.get("formatted_address") or "").split(",")[0]).strip()[:80]
            if not label or not _matches_query(query, label, str(item.get("formatted_address") or "")):
                continue
            types = set(item.get("types") or [])
            kind = "area" if types & {"administrative_area_level_2", "administrative_area_level_3",
                                      "locality", "sublocality"} and not types & {"establishment", "point_of_interest"} else "point"
            found.append({"label": label, "city": city, "latitude": round(latitude, 6),
                          "longitude": round(longitude, 6), "kind": kind, "uncertainty_m": 300.0})
        return found

    def _search(self, query: str, city: str) -> list[dict]:
        """Thử Goong (nếu có key chưa bị từ chối) rồi Nominatim. Lỗi → thử nguồn kế."""
        order = []
        if self.provider in ("auto", "goong") and self.goong_key and not self._goong_denied:
            order.append(self._goong)
        if self.provider in ("auto", "nominatim") or (self.provider == "goong" and not order):
            order.append(self._nominatim)
        last_error: Exception | None = None
        for source in order:
            try:
                return source(query, city)
            except Exception as error:  # noqa: BLE001 - lỗi nguồn ngoài không được lan ra tool
                last_error = error
        if last_error is not None:
            raise last_error
        return []

    # ---- API ----
    def lookup(self, text: str, city: str | None = None) -> dict:
        """Kết quả có `status`: ok | area | ambiguous | not_found | address_not_sent | off."""
        if not self.enabled:
            return {"status": "off"}
        query, reason = sanitize_query(text)
        if query is None:
            return {"status": "address_not_sent" if reason == "address_not_sent" else "not_found"}
        key = (fold(query), city or "")
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
        cities = [city] if city in CITY_BBOX else list(CITY_BBOX)
        per_city: dict[str, list[dict]] = {}
        try:
            for name in cities:
                hits = self._search(query, name)
                if hits:
                    per_city[name] = hits
        except Exception:  # noqa: BLE001
            return {"status": "not_found", "error": True}   # lỗi tạm: không cache
        result = self._decide(query, per_city)
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return result

    @staticmethod
    def _decide(query: str, per_city: dict[str, list[dict]]) -> dict:
        if not per_city:
            return {"status": "not_found"}
        tops = {name: hits[0] for name, hits in per_city.items()}
        if len(tops) > 1:
            return {"status": "ambiguous", "query": query,
                    "candidates": [{"label": hit["label"], "city": name} for name, hit in tops.items()]}
        name, top = next(iter(tops.items()))
        if top["kind"] == "area":
            return {"status": "area", "query": query, "label": top["label"], "city": name}
        place_id = "geo:" + hashlib.sha1(
            f"{fold(top['label'])}|{top['latitude']:.4f},{top['longitude']:.4f}".encode()).hexdigest()[:8]
        return {"status": "ok", "query": query, "place_id": place_id, **top}
