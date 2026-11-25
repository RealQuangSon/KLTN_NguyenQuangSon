"""MP-01 — đường đi từ một căn trong kết quả tới điểm neo của hồ sơ.

Điểm neo là `destination` của hồ sơ đã xác nhận: nơi khách muốn ở gần (trường,
công ty, địa điểm). Chuỗi nguồn chỉ đường, thử lần lượt:

1. Goong Direction (`GOONG_API_KEY` loại REST): xe máy (`vehicle=bike`) cho chế
   độ đi xe. Goong không có hồ sơ đi bộ nên chế độ đi bộ bỏ qua Goong. Key trả
   401/403 (sai loại key, ví dụ key "Map tiles") thì tắt Goong tới hết process.
2. OSRM công khai của OpenStreetMap (`HOMEMATCH_OSRM_URL`, mặc định máy chủ
   FOSSGIS routing.openstreetmap.de, không cần key): ô tô cho chế độ đi xe, đi
   bộ cho chế độ đi bộ. Thời gian ô tô không tính kẹt xe.
3. Đoạn thẳng (đường chim bay): không có thời gian, không bịa số phút.

`HOMEMATCH_ROUTE_PROVIDER=auto|goong|osrm|off` chọn nguồn (test đặt `off`).

Riêng tư: chỉ gửi tọa độ làm tròn 4 chữ số (~10 m), không gửi nhãn điểm neo,
user id hay nội dung chat. Cache trong process theo tọa độ làm tròn + chế độ
(API chạy một worker). Giới hạn 60 lượt gọi nguồn ngoài/khách/giờ; vượt thì
trả đoạn thẳng. Đường đi chỉ để hiển thị: lọc và xếp hạng vẫn dùng chim bay
(`catalog.distance_m`).

`matrix()` lấy cùng lúc quãng đường/thời gian từ N căn tới điểm neo
bằng MỘT lần gọi nguồn ngoài (Goong `DistanceMatrix` hoặc bảng `table` của
OSRM), không trả đường vẽ. Một lần gọi ma trận tính 1 lượt hạn mức; cặp đã có
trong cache của `route()` thì dùng lại để thẻ căn và đường vẽ không lệch nhau.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import OrderedDict, deque
from typing import Callable

from . import provider_breaker

logger = logging.getLogger(__name__)

TRAVELS = ("ride", "walk")
PROVIDERS = ("auto", "goong", "osrm", "off")
CACHE_TTL_S = 7 * 24 * 3600
CACHE_MAX = 512
CALLS_PER_HOUR = 60
# Máy OSRM đi bộ công khai lúc nguội trả lời tới ~5 s (đo 22/11/2026); gọi
# ngoài service.lock nên chờ lâu không chặn worker.
TIMEOUT_S = 8.0
DEFAULT_OSRM_URL = "https://routing.openstreetmap.de"
GOONG_URL = "https://rsapi.goong.io/Direction"
GOONG_MATRIX_URL = "https://rsapi.goong.io/DistanceMatrix"
# Service chỉ gửi kết quả đang hiển thị (tối đa 5 căn); trần này chỉ chặn bug.
MATRIX_MAX_ORIGINS = 10
# Máy chủ OSRM công khai yêu cầu User-Agent nhận diện ứng dụng; không chứa
# thông tin người dùng.
USER_AGENT = "HomeMatch-thesis/1.0 (localhost demo)"
ATTRIBUTION = {"goong": "Đường đi © Goong",
               "osrm": "Đường đi © OpenStreetMap, OSRM (FOSSGIS)"}

# fetch(url, params, timeout_s) -> (http_status, json_body | None)
Fetch = Callable[[str, dict, float], tuple[int, object]]


class _Denied(Exception):
    """Nguồn từ chối key (401/403): không thử lại tới hết process."""


class _RouteFailed(Exception):
    """Nguồn lỗi tạm thời hoặc trả dữ liệu không dùng được: thử nguồn kế tiếp."""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Khoảng cách chim bay (m), cùng công thức với `catalog.distance_m`."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(value)))


def decode_polyline(points: str, precision: int = 5) -> list[list[float]]:
    """Giải mã polyline định dạng Google (Goong dùng) thành [[lng, lat], ...]."""
    coordinates: list[list[float]] = []
    index = lat = lng = 0
    factor = 10 ** precision
    while index < len(points):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                if index >= len(points):
                    raise ValueError("polyline bị cắt cụt")
                byte = ord(points[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        coordinates.append([round(lng / factor, 6), round(lat / factor, 6)])
    return coordinates


def _http_fetch(url: str, params: dict, timeout_s: float) -> tuple[int, object]:
    import httpx
    response = httpx.get(url, params=params, timeout=timeout_s,
                         headers={"User-Agent": USER_AGENT})
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


def _line(points: list[list[float]]) -> dict:
    return {"type": "LineString",
            "coordinates": [[round(lng, 5), round(lat, 5)] for lng, lat in points]}


class Router:
    """Một instance mỗi HomeMatchService; trạng thái cache/hạn mức trong process."""

    def __init__(self, provider: str = "auto", goong_key: str | None = None,
                 osrm_url: str = DEFAULT_OSRM_URL, fetch: Fetch | None = None,
                 calls_per_hour: int = CALLS_PER_HOUR, clock: Callable[[], float] = time.time):
        if provider not in PROVIDERS:
            raise ValueError(f"HOMEMATCH_ROUTE_PROVIDER phải là một trong {PROVIDERS}")
        self.provider = provider
        self.goong_key = goong_key or None
        self.osrm_url = osrm_url.rstrip("/")
        self.fetch = fetch or _http_fetch
        self.calls_per_hour = calls_per_hour
        self.clock = clock
        self._goong_denied = False
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        # Cache tóm tắt riêng của matrix(): cùng TTL/giới hạn, khóa tách khỏi
        # cache của route() để hai luồng không đạp nhau.
        self._matrix_cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        self._calls: dict[str, deque[float]] = {}

    @classmethod
    def from_env(cls) -> "Router":
        return cls(provider=os.getenv("HOMEMATCH_ROUTE_PROVIDER", "auto").strip().lower(),
                   goong_key=(os.getenv("GOONG_API_KEY") or "").strip() or None,
                   osrm_url=os.getenv("HOMEMATCH_OSRM_URL", DEFAULT_OSRM_URL))

    def _chain(self, travel: str) -> list[tuple[str, str]]:
        """(nguồn, phương tiện) theo thứ tự thử cho một chế độ đi."""
        chain: list[tuple[str, str]] = []
        if (self.provider in ("auto", "goong") and travel == "ride"
                and self.goong_key and not self._goong_denied):
            chain.append(("goong", "motorbike"))
        if self.provider in ("auto", "osrm"):
            chain.append(("osrm", "car" if travel == "ride" else "foot"))
        return chain

    def _allow(self, actor_id: str) -> bool:
        now = self.clock()
        with self._lock:
            calls = self._calls.setdefault(actor_id, deque())
            while calls and now - calls[0] > 3600:
                calls.popleft()
            if len(calls) >= self.calls_per_hour:
                return False
            calls.append(now)
            return True

    def _cache_get(self, key: tuple, cache: OrderedDict | None = None) -> dict | None:
        cache = self._cache if cache is None else cache
        with self._lock:
            entry = cache.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if self.clock() - stored_at > CACHE_TTL_S:
                del cache[key]
                return None
            cache.move_to_end(key)
            return value

    def _cache_put(self, key: tuple, value: dict, cache: OrderedDict | None = None) -> None:
        cache = self._cache if cache is None else cache
        with self._lock:
            cache[key] = (self.clock(), value)
            cache.move_to_end(key)
            while len(cache) > CACHE_MAX:
                cache.popitem(last=False)

    def _goong(self, origin: tuple[float, float], destination: tuple[float, float]) -> dict:
        status, body = self.fetch(GOONG_URL, {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "vehicle": "bike", "api_key": self.goong_key}, TIMEOUT_S)
        if status in (401, 403):
            raise _Denied(status)
        if status != 200 or not isinstance(body, dict) or not body.get("routes"):
            raise _RouteFailed(f"goong http {status}")
        try:
            route = body["routes"][0]
            leg = route["legs"][0]
            points = decode_polyline(route["overview_polyline"]["points"])
            distance, duration = leg["distance"]["value"], leg["duration"]["value"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise _RouteFailed(f"goong payload: {error}") from error
        if len(points) < 2:
            raise _RouteFailed("goong route rỗng")
        return {"distance_m": round(distance), "duration_s": round(duration), "geometry": _line(points)}

    def _osrm(self, origin: tuple[float, float], destination: tuple[float, float], vehicle: str) -> dict:
        profile = "routed-car" if vehicle == "car" else "routed-foot"
        url = (f"{self.osrm_url}/{profile}/route/v1/driving/"
               f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}")
        status, body = self.fetch(url, {"overview": "full", "geometries": "geojson"}, TIMEOUT_S)
        if status != 200 or not isinstance(body, dict) or body.get("code") != "Ok" or not body.get("routes"):
            raise _RouteFailed(f"osrm http {status}")
        try:
            route = body["routes"][0]
            points = route["geometry"]["coordinates"]
            distance, duration = route["distance"], route["duration"]
        except (KeyError, IndexError, TypeError) as error:
            raise _RouteFailed(f"osrm payload: {error}") from error
        if not isinstance(points, list) or len(points) < 2:
            raise _RouteFailed("osrm route rỗng")
        return {"distance_m": round(distance), "duration_s": round(duration), "geometry": _line(points)}

    def _goong_matrix(self, origins: list[tuple[float, float]],
                      destination: tuple[float, float]) -> list[dict | None]:
        """Ma trận Goong: trả list cùng thứ tự origins; phần tử None = lỗi riêng
        của một cặp (status khác OK), cả lần gọi lỗi thì ném _RouteFailed."""
        status, body = self.fetch(GOONG_MATRIX_URL, {
            "origins": "|".join(f"{lat},{lng}" for lat, lng in origins),
            "destinations": f"{destination[0]},{destination[1]}",
            "vehicle": "bike", "api_key": self.goong_key}, TIMEOUT_S)
        if status in (401, 403):
            raise _Denied(status)
        if status != 200 or not isinstance(body, dict):
            raise _RouteFailed(f"goong http {status}")
        rows = body.get("rows")
        if not isinstance(rows, list) or len(rows) < len(origins):
            raise _RouteFailed("goong payload thiếu rows")
        results: list[dict | None] = []
        for row in rows:
            element = None
            if isinstance(row, dict):
                elements = row.get("elements")
                if isinstance(elements, list) and elements and isinstance(elements[0], dict):
                    element = elements[0]
            if element is None or element.get("status") != "OK":
                results.append(None)
                continue
            try:
                results.append({"distance_m": round(element["distance"]["value"]),
                                "duration_s": round(element["duration"]["value"])})
            except (KeyError, TypeError, ValueError):
                results.append(None)
        return results

    def _osrm_matrix(self, origins: list[tuple[float, float]],
                     destination: tuple[float, float], vehicle: str) -> list[dict | None]:
        """Bảng OSRM `table`: origins rồi destination trong cùng chuỗi tọa độ,
        `sources` là chỉ số các căn, `destinations` là chỉ số điểm neo."""
        profile = "routed-car" if vehicle == "car" else "routed-foot"
        coords = ";".join(f"{lng},{lat}" for lat, lng in [*origins, destination])
        url = f"{self.osrm_url}/{profile}/table/v1/driving/{coords}"
        params = {"sources": ";".join(str(index) for index in range(len(origins))),
                  "destinations": str(len(origins)), "annotations": "duration,distance"}
        status, body = self.fetch(url, params, TIMEOUT_S)
        if status != 200 or not isinstance(body, dict) or body.get("code") != "Ok":
            raise _RouteFailed(f"osrm http {status}")
        durations, distances = body.get("durations"), body.get("distances")
        if (not isinstance(durations, list) or not isinstance(distances, list)
                or len(durations) < len(origins) or len(distances) < len(origins)):
            raise _RouteFailed("osrm payload thiếu durations/distances")
        results: list[dict | None] = []
        for duration_row, distance_row in zip(durations, distances):
            try:
                duration, distance = duration_row[0], distance_row[0]
            except (IndexError, TypeError):
                results.append(None)
                continue
            if duration is None or distance is None:
                results.append(None)
                continue
            results.append({"distance_m": round(distance), "duration_s": round(duration)})
        return results

    @staticmethod
    def _straight(origin: tuple[float, float], destination: tuple[float, float],
                  straight_m: float, reason: str) -> dict:
        return {"provider": "straight_line", "vehicle": None, "distance_m": round(straight_m),
                "duration_s": None,
                "geometry": _line([[origin[1], origin[0]], [destination[1], destination[0]]]),
                "attribution": None, "fallback_reason": reason}

    def route(self, origin: tuple[float, float], destination: tuple[float, float],
              travel: str, actor_id: str, external: bool = True) -> dict:
        """origin/destination là (lat, lng). Không bao giờ ném lỗi nguồn ra ngoài:
        mọi lỗi rơi về đoạn thẳng có `fallback_reason`. `external=False`
        (điểm neo thiết bị mà khách chưa đồng ý) thì chỉ chim bay "no_consent" —
        không fetch, không tốn lượt hạn mức, không đụng cache."""
        if travel not in TRAVELS:
            raise ValueError(travel)
        rounded_o = (round(origin[0], 4), round(origin[1], 4))
        rounded_d = (round(destination[0], 4), round(destination[1], 4))
        straight_m = haversine_m(origin[0], origin[1], destination[0], destination[1])
        base = {"travel": travel, "straight_line_m": round(straight_m)}
        if not external:
            return {**base, **self._straight(origin, destination, straight_m, "no_consent")}
        chain = self._chain(travel)
        if not chain:
            return {**base, **self._straight(origin, destination, straight_m, "no_provider")}
        key = (rounded_o, rounded_d, travel)
        cached = self._cache_get(key)
        if cached is not None:
            return {**base, **cached}
        if not self._allow(actor_id):
            return {**base, **self._straight(origin, destination, straight_m, "rate_limited")}
        for provider, vehicle in chain:
            breaker_key = f"route:{provider}"
            if provider_breaker.open_(breaker_key):
                continue
            try:
                found = (self._goong(rounded_o, rounded_d) if provider == "goong"
                         else self._osrm(rounded_o, rounded_d, vehicle))
            except _Denied as error:
                self._goong_denied = True
                logger.warning("route_provider_denied provider=%s status=%s", provider, error)
                continue
            except Exception as error:  # mạng, timeout, payload lạ: thử nguồn kế tiếp
                provider_breaker.record(breaker_key, False)
                logger.warning("route_provider_failed provider=%s error=%s", provider, type(error).__name__)
                continue
            provider_breaker.record(breaker_key, True)
            result = {"provider": provider, "vehicle": vehicle, **found,
                      "attribution": ATTRIBUTION[provider], "fallback_reason": None}
            self._cache_put(key, result)
            return {**base, **result}
        return {**base, **self._straight(origin, destination, straight_m, "provider_error")}

    @staticmethod
    def _summary(travel: str, straight_m: float, found: dict) -> dict:
        """Tóm tắt một cặp cho matrix(): giống route() nhưng không có geometry."""
        return {"travel": travel, "provider": found["provider"], "vehicle": found["vehicle"],
                "distance_m": found["distance_m"], "duration_s": found["duration_s"],
                "straight_line_m": round(straight_m), "fallback_reason": found.get("fallback_reason")}

    def matrix(self, origins: list[tuple[str, tuple[float, float]]],
               destination: tuple[float, float], travel: str, actor_id: str,
               external: bool = True) -> dict:
        """Quãng đường/thời gian từ N căn tới điểm neo bằng MỘT lần gọi nguồn ngoài.

        `origins` là [(room_id, (lat, lng))]. Chỉ gửi tọa độ đã làm tròn ra ngoài
        (căn trùng tọa độ sau làm tròn chỉ gửi một lần, không gửi room_id). Cặp đã
        có trong cache của route() dùng lại số liệu cũ. Không bao giờ ném lỗi
        nguồn ra ngoài: mọi lỗi rơi về chim bay có `fallback_reason`.
        `external=False` (điểm neo thiết bị mà khách chưa đồng ý) thì cả danh sách
        là chim bay "no_consent" — không fetch, không tốn lượt, không đụng cache."""
        if travel not in TRAVELS:
            raise ValueError(travel)
        if len(origins) > MATRIX_MAX_ORIGINS:
            raise ValueError(f"matrix() chỉ nhận tối đa {MATRIX_MAX_ORIGINS} căn mỗi lần gọi")
        rounded_d = (round(destination[0], 4), round(destination[1], 4))
        if not external:
            items: dict[str, dict] = {}
            for room_id, (lat, lng) in origins:
                straight = haversine_m(lat, lng, destination[0], destination[1])
                items[room_id] = {"travel": travel, "provider": "straight_line", "vehicle": None,
                                  "distance_m": round(straight), "duration_s": None,
                                  "straight_line_m": round(straight), "fallback_reason": "no_consent"}
            return {"items": items, "attribution": None}
        items: dict[str, dict] = {}
        attributions: list[str] = []
        # Tọa độ đã làm tròn -> [(room_id, straight_line_m)]: các căn cần hỏi ngoài.
        pending: OrderedDict[tuple, list[tuple[str, float]]] = OrderedDict()
        for room_id, (lat, lng) in origins:
            straight_m = haversine_m(lat, lng, destination[0], destination[1])
            rounded_o = (round(lat, 4), round(lng, 4))
            key = (rounded_o, rounded_d, travel)
            cached = (self._cache_get(key) or self._cache_get(key, self._matrix_cache))
            if cached is not None:
                items[room_id] = self._summary(travel, straight_m, cached)
                if cached.get("attribution") and cached["attribution"] not in attributions:
                    attributions.append(cached["attribution"])
            else:
                pending.setdefault(rounded_o, []).append((room_id, straight_m))
        found: list[dict | None] | None = None
        provider_used = vehicle_used = None
        rate_limited = False
        chain = self._chain(travel)
        if pending and chain and self._allow(actor_id):
            for provider, vehicle in chain:
                breaker_key = f"route:{provider}"
                if provider_breaker.open_(breaker_key):
                    continue
                try:
                    found = (self._goong_matrix(list(pending), rounded_d) if provider == "goong"
                             else self._osrm_matrix(list(pending), rounded_d, vehicle))
                except _Denied as error:
                    self._goong_denied = True
                    logger.warning("route_provider_denied provider=%s status=%s", provider, error)
                    continue
                except Exception as error:  # mạng, timeout, payload lạ: thử nguồn kế tiếp
                    provider_breaker.record(breaker_key, False)
                    logger.warning("route_provider_failed provider=%s error=%s", provider, type(error).__name__)
                    continue
                provider_breaker.record(breaker_key, True)
                provider_used, vehicle_used = provider, vehicle
                break
        elif pending and chain:
            rate_limited = True
        for index, (rounded_o, entries) in enumerate(pending.items()):
            real = found[index] if found is not None else None
            if real is not None:
                entry = {"provider": provider_used, "vehicle": vehicle_used, **real,
                         "attribution": ATTRIBUTION[provider_used], "fallback_reason": None}
                self._cache_put((rounded_o, rounded_d, travel), entry, self._matrix_cache)
                for room_id, straight_m in entries:
                    items[room_id] = self._summary(travel, straight_m, entry)
                if entry["attribution"] not in attributions:
                    attributions.append(entry["attribution"])
                continue
            reason = ("rate_limited" if rate_limited
                      else "no_provider" if not chain else "provider_error")
            for room_id, straight_m in entries:
                items[room_id] = {"travel": travel, "provider": "straight_line", "vehicle": None,
                                  "distance_m": round(straight_m), "duration_s": None,
                                  "straight_line_m": round(straight_m), "fallback_reason": reason}
        return {"items": items, "attribution": "; ".join(attributions) or None}
