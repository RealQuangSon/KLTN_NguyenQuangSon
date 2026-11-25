"""MP-01: đường đi từ căn tới điểm neo (điểm đến của hồ sơ đã xác nhận).

Không gọi mạng: mọi nguồn chỉ đường đi qua fetch giả."""
import pytest
from fastapi.testclient import TestClient

from backend.app import provider_breaker
from backend.app.main import create_app
from backend.app.models import Actor, Destination, DomainError
from backend.app.routes_map import Router, decode_polyline, haversine_m

HUST = (21.004, 105.8431)
ROOM = (21.0123, 105.8456)


class FakeFetch:
    def __init__(self, responses):
        self.responses = responses  # {"goong"|"osrm": (status, body) | Exception}
        self.calls = []

    def __call__(self, url, params, timeout_s):
        provider = "goong" if "goong" in url else "osrm"
        self.calls.append((provider, url, dict(params)))
        response = self.responses[provider]
        if isinstance(response, Exception):
            raise response
        return response


GOONG_OK = (200, {"routes": [{"legs": [{"distance": {"value": 3200}, "duration": {"value": 660}}],
                              "overview_polyline": {"points": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"}}]})
OSRM_OK = (200, {"code": "Ok", "routes": [{"distance": 4667.2, "duration": 465.4, "geometry": {
    "type": "LineString", "coordinates": [[105.84561, 21.01231], [105.8440, 21.0080], [105.84311, 21.00401]]}}]})
# trả lời dạng bảng/ma trận (2 gốc, 1 đích) — không có geometry.
OSRM_TABLE_OK = (200, {"code": "Ok", "durations": [[388.9], [206.2]], "distances": [[5025.0], [2207.1]]})
GOONG_MATRIX_OK = (200, {"rows": [
    {"elements": [{"status": "OK", "distance": {"value": 5025}, "duration": {"value": 389}}]},
    {"elements": [{"status": "OK", "distance": {"value": 2207}, "duration": {"value": 206}}]}]})


def test_decode_polyline_matches_google_reference():
    # Ví dụ chuẩn trong tài liệu polyline của Google.
    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [
        [-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]]
    with pytest.raises(ValueError):
        decode_polyline("_p~iF~ps|U_")


def test_goong_route_sends_only_rounded_coordinates():
    fetch = FakeFetch({"goong": GOONG_OK, "osrm": OSRM_OK})
    router = Router("auto", goong_key="rest-key", fetch=fetch)
    route = router.route((21.012345, 105.845678), HUST, "ride", "renter")
    assert route["provider"] == "goong" and route["vehicle"] == "motorbike"
    assert route["distance_m"] == 3200 and route["duration_s"] == 660
    assert route["geometry"]["type"] == "LineString" and len(route["geometry"]["coordinates"]) == 3
    assert route["fallback_reason"] is None
    assert route["straight_line_m"] == round(haversine_m(21.012345, 105.845678, *HUST))
    (provider, _url, params), = fetch.calls
    assert provider == "goong" and params["vehicle"] == "bike"
    # Riêng tư: tọa độ làm tròn 4 chữ số, không có nhãn điểm neo hay user id.
    assert params["origin"] == "21.0123,105.8457" and params["destination"] == "21.004,105.8431"
    assert set(params) == {"origin", "destination", "vehicle", "api_key"}


def test_cache_hit_does_not_call_provider_again():
    fetch = FakeFetch({"goong": GOONG_OK, "osrm": OSRM_OK})
    router = Router("auto", goong_key="rest-key", fetch=fetch)
    first = router.route(ROOM, HUST, "ride", "renter")
    # Lệch < 5 m vẫn trúng cache (khóa theo tọa độ làm tròn).
    second = router.route((ROOM[0] + 0.00001, ROOM[1]), HUST, "ride", "other")
    assert len(fetch.calls) == 1 and second["distance_m"] == first["distance_m"]


def test_tiles_key_denied_falls_back_to_osrm_and_stops_asking_goong():
    fetch = FakeFetch({"goong": (403, {"error": {"code": "API_KEY_UNAUTHORIZED"}}), "osrm": OSRM_OK})
    router = Router("auto", goong_key="tiles-key", fetch=fetch)
    route = router.route(ROOM, HUST, "ride", "renter")
    assert route["provider"] == "osrm" and route["vehicle"] == "car"
    assert route["distance_m"] == 4667 and route["duration_s"] == 465
    assert "routed-car" in fetch.calls[1][1]
    router.route((10.77, 106.70), (10.78, 106.69), "ride", "renter")
    assert [call[0] for call in fetch.calls] == ["goong", "osrm", "osrm"]


def test_walk_skips_goong_and_uses_osrm_foot():
    fetch = FakeFetch({"goong": GOONG_OK, "osrm": OSRM_OK})
    route = Router("auto", goong_key="rest-key", fetch=fetch).route(ROOM, HUST, "walk", "renter")
    assert route["provider"] == "osrm" and route["vehicle"] == "foot"
    assert [call[0] for call in fetch.calls] == ["osrm"] and "routed-foot" in fetch.calls[0][1]


@pytest.mark.parametrize("failure", [TimeoutError("slow"), (500, None), (200, {"code": "NoRoute", "routes": []})])
def test_provider_failure_returns_straight_line_without_duration(failure):
    provider_breaker.reset()
    fetch = FakeFetch({"goong": failure, "osrm": failure})
    route = Router("auto", goong_key="rest-key", fetch=fetch).route(ROOM, HUST, "ride", "renter")
    assert route["provider"] == "straight_line" and route["vehicle"] is None
    assert route["duration_s"] is None and route["fallback_reason"] == "provider_error"
    assert route["distance_m"] == route["straight_line_m"]
    assert route["geometry"]["coordinates"] == [[ROOM[1], ROOM[0]], [HUST[1], HUST[0]]]


def test_off_mode_never_fetches():
    fetch = FakeFetch({})
    route = Router("off", goong_key="rest-key", fetch=fetch).route(ROOM, HUST, "ride", "renter")
    assert route["fallback_reason"] == "no_provider" and fetch.calls == []


def test_rate_limit_falls_back_to_straight_line():
    fetch = FakeFetch({"osrm": OSRM_OK})
    router = Router("osrm", fetch=fetch, calls_per_hour=2)
    router.route((21.01, 105.84), HUST, "ride", "renter")
    router.route((21.02, 105.84), HUST, "ride", "renter")
    limited = router.route((21.03, 105.84), HUST, "ride", "renter")
    assert limited["fallback_reason"] == "rate_limited" and len(fetch.calls) == 2
    # Khách khác có hạn mức riêng.
    assert router.route((21.03, 105.84), HUST, "ride", "renter-2")["provider"] == "osrm"


def test_from_env_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("HOMEMATCH_ROUTE_PROVIDER", "google")
    with pytest.raises(ValueError):
        Router.from_env()


# --- matrix() — quãng đường/thời gian của cả danh sách căn, một lần gọi ---

HCM_DEST = (10.72501, 106.69502)


def test_matrix_osrm_table_url_params_and_room_mapping():
    fetch = FakeFetch({"osrm": OSRM_TABLE_OK})
    router = Router("osrm", fetch=fetch)
    result = router.matrix([("r1", (10.73021, 106.70014)), ("r2", (10.74011, 106.71231))],
                           HCM_DEST, "ride", "renter")
    (provider, url, params), = fetch.calls
    assert provider == "osrm"
    # Thứ tự lng,lat, chỉ tọa độ đã làm tròn 4 chữ số, đích đứng cuối.
    assert url.endswith("/routed-car/table/v1/driving/"
                        "106.7001,10.7302;106.7123,10.7401;106.695,10.725")
    assert params["sources"] == "0;1" and params["destinations"] == "2"
    assert params["annotations"] == "duration,distance"
    assert result["items"]["r1"] == {"travel": "ride", "provider": "osrm", "vehicle": "car",
                                     "distance_m": 5025, "duration_s": 389,
                                     "straight_line_m": round(haversine_m(10.73021, 106.70014, *HCM_DEST)),
                                     "fallback_reason": None}
    assert result["items"]["r2"]["distance_m"] == 2207 and result["items"]["r2"]["duration_s"] == 206
    assert result["attribution"] == "Đường đi © OpenStreetMap, OSRM (FOSSGIS)"


def test_matrix_duplicate_rounded_origins_sent_once():
    fetch = FakeFetch({"osrm": (200, {"code": "Ok", "durations": [[100.0]], "distances": [[800.0]]})})
    result = Router("osrm", fetch=fetch).matrix(
        [("r1", ROOM), ("r2", (ROOM[0] + 0.00001, ROOM[1]))], HUST, "ride", "renter")
    (provider, url, params), = fetch.calls
    # Chỉ 1 tọa độ gốc + 1 đích; cả hai căn đều có kết quả thật như nhau
    # (straight_line_m chênh ~1 m vì tính từ tọa độ gốc của từng căn).
    assert url.count(";") == 1 and params["sources"] == "0" and params["destinations"] == "1"
    assert {key: value for key, value in result["items"]["r1"].items() if key != "straight_line_m"} \
        == {key: value for key, value in result["items"]["r2"].items() if key != "straight_line_m"}
    assert result["items"]["r1"]["distance_m"] == 800 and result["items"]["r1"]["duration_s"] == 100


def test_matrix_null_element_falls_back_for_that_room_only():
    fetch = FakeFetch({"osrm": (200, {"code": "Ok", "durations": [[388.9], [None]],
                                      "distances": [[5025.0], [None]]})})
    result = Router("osrm", fetch=fetch).matrix(
        [("r1", (10.7302, 106.7001)), ("r2", (10.7401, 106.7123))], HCM_DEST, "ride", "renter")
    assert result["items"]["r1"]["provider"] == "osrm" and result["items"]["r1"]["fallback_reason"] is None
    r2 = result["items"]["r2"]
    assert r2["provider"] == "straight_line" and r2["fallback_reason"] == "provider_error"
    assert r2["duration_s"] is None and r2["distance_m"] == r2["straight_line_m"]


def test_matrix_reuses_route_cache_pair():
    fetch = FakeFetch({"osrm": OSRM_OK})
    router = Router("osrm", fetch=fetch)
    route = router.route(ROOM, HUST, "ride", "renter")
    # Đổi trả lời để chắc chắn số liệu r1 đến từ cache của route(), không phải gọi lại.
    fetch.responses["osrm"] = (200, {"code": "Ok", "durations": [[99.0]], "distances": [[1111.0]]})
    result = router.matrix([("r1", ROOM), ("r2", (21.02, 105.85))], HUST, "ride", "renter")
    assert len(fetch.calls) == 2  # 1 lần route() + 1 lần matrix() chỉ cho cặp còn thiếu
    assert "105.85,21.02" in fetch.calls[1][1] and "105.8456,21.0123" not in fetch.calls[1][1]
    assert fetch.calls[1][2]["sources"] == "0" and fetch.calls[1][2]["destinations"] == "1"
    assert result["items"]["r1"]["distance_m"] == route["distance_m"]
    assert result["items"]["r1"]["duration_s"] == route["duration_s"]
    assert result["items"]["r1"]["provider"] == route["provider"] == "osrm"
    assert result["items"]["r1"]["vehicle"] == route["vehicle"]
    assert result["items"]["r2"]["distance_m"] == 1111 and result["items"]["r2"]["duration_s"] == 99


def test_matrix_second_call_uses_matrix_cache():
    fetch = FakeFetch({"osrm": (200, {"code": "Ok", "durations": [[100.0]], "distances": [[800.0]]})})
    router = Router("osrm", fetch=fetch)
    first = router.matrix([("r1", ROOM)], HUST, "ride", "renter")
    second = router.matrix([("r1", ROOM)], HUST, "ride", "other-actor")
    assert len(fetch.calls) == 1 and second["items"]["r1"] == first["items"]["r1"]
    assert second["attribution"] == first["attribution"]


def test_matrix_costs_one_allow_then_rate_limited():
    fetch = FakeFetch({"osrm": OSRM_TABLE_OK})
    router = Router("osrm", fetch=fetch, calls_per_hour=1)
    result = router.matrix([("r1", (10.7302, 106.7001)), ("r2", (10.7401, 106.7123))],
                           HCM_DEST, "ride", "renter")
    # Cả danh sách chỉ tốn 1 lượt hạn mức: hai căn đều thật sau MỘT lần gọi.
    assert all(item["provider"] == "osrm" for item in result["items"].values())
    assert len(fetch.calls) == 1
    limited = router.matrix([("r3", (10.75, 106.72))], HCM_DEST, "ride", "renter")
    assert limited["items"]["r3"]["fallback_reason"] == "rate_limited"
    assert limited["items"]["r3"]["provider"] == "straight_line"
    assert len(fetch.calls) == 1


def test_matrix_goong_params_then_denied_falls_back_to_osrm():
    fetch = FakeFetch({"goong": GOONG_MATRIX_OK, "osrm": OSRM_TABLE_OK})
    router = Router("auto", goong_key="rest-key", fetch=fetch)
    result = router.matrix([("r1", ROOM), ("r2", (21.02, 105.85))], HUST, "ride", "renter")
    (provider, _url, params), = fetch.calls
    assert provider == "goong"
    # Riêng tư: chỉ tọa độ làm tròn, không có room_id/nhãn/user id.
    assert params["origins"] == "21.0123,105.8456|21.02,105.85"
    assert params["destinations"] == "21.004,105.8431"
    assert params["vehicle"] == "bike" and params["api_key"] == "rest-key"
    assert set(params) == {"origins", "destinations", "vehicle", "api_key"}
    assert result["items"]["r1"]["distance_m"] == 5025 and result["items"]["r2"]["duration_s"] == 206
    assert result["attribution"] == "Đường đi © Goong"
    # Key sai loại (403): chuyển sang OSRM trong cùng lần gọi, các lần sau không hỏi Goong.
    denied = FakeFetch({"goong": (403, {"error": {"code": "API_KEY_UNAUTHORIZED"}}), "osrm": OSRM_TABLE_OK})
    router2 = Router("auto", goong_key="tiles-key", fetch=denied)
    result2 = router2.matrix([("r1", ROOM)], HUST, "ride", "renter")
    assert result2["items"]["r1"]["provider"] == "osrm" and "routed-car/table" in denied.calls[1][1]
    router2.matrix([("r9", (21.05, 105.86))], HUST, "ride", "renter")
    assert [call[0] for call in denied.calls] == ["goong", "osrm", "osrm"]


def test_matrix_walk_skips_goong_and_uses_osrm_foot():
    fetch = FakeFetch({"goong": GOONG_MATRIX_OK, "osrm": OSRM_TABLE_OK})
    result = Router("auto", goong_key="rest-key", fetch=fetch).matrix([("r1", ROOM)], HUST, "walk", "renter")
    assert result["items"]["r1"]["vehicle"] == "foot" and result["items"]["r1"]["travel"] == "walk"
    assert [call[0] for call in fetch.calls] == ["osrm"] and "routed-foot/table" in fetch.calls[0][1]


def test_matrix_off_mode_never_fetches():
    fetch = FakeFetch({})
    result = Router("off", fetch=fetch).matrix([("r1", ROOM), ("r2", (21.02, 105.85))],
                                               HUST, "ride", "renter")
    assert fetch.calls == [] and result["attribution"] is None
    assert all(item["fallback_reason"] == "no_provider" and item["duration_s"] is None
               for item in result["items"].values())


def test_matrix_rejects_more_than_ten_origins():
    fetch = FakeFetch({"osrm": OSRM_TABLE_OK})
    router = Router("osrm", fetch=fetch)
    with pytest.raises(ValueError):
        router.matrix([(f"r{i}", ROOM) for i in range(11)], HUST, "ride", "renter")
    assert fetch.calls == []


def _published_with_anchor(service, renter, profile, place="gần Phú Mỹ Hưng"):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, place)
    session = service.session(sid, renter)
    destination = Destination.model_validate(session["draft"]["destination"])
    result = service.confirm(sid, renter, profile.model_copy(update={"destination": destination}),
                             session["draft_revision"])
    assert result["status"] == "published" and result["results"]
    return sid, result, destination


def test_service_route_uses_confirmed_anchor_from_server(service, renter, profile):
    sid, result, destination = _published_with_anchor(service, renter, profile)
    fetch = FakeFetch({"osrm": OSRM_OK})
    service.router = Router("osrm", fetch=fetch)
    item = next(entry for entry in result["results"] if entry["latitude"] is not None)
    route = service.room_route(sid, renter, item["room_id"], "ride")
    assert route["provider"] == "osrm" and route["run_id"] == result["run_id"]
    assert route["anchor"] == {"label": destination.label, "latitude": destination.latitude,
                               "longitude": destination.longitude,
                               "max_distance_m": destination.max_distance_m,
                               "uncertainty_m": destination.uncertainty_m}
    assert route["origin"]["latitude"] == item["latitude"]
    assert f"{round(destination.longitude, 4)},{round(destination.latitude, 4)}" in fetch.calls[0][1]


def test_service_route_rejects_rooms_outside_results_and_other_renters(service, renter, profile):
    sid, result, _ = _published_with_anchor(service, renter, profile)
    visible = {entry["room_id"] for entry in result["results"]}
    hidden = next(room.id for room in service.catalog.rooms() if room.id not in visible)
    with pytest.raises(DomainError) as error:
        service.room_route(sid, renter, hidden, "ride")
    assert error.value.code == "not_visible"
    with pytest.raises(DomainError):
        service.room_route(sid, Actor(id="renter-2", role="renter"), result["results"][0]["room_id"], "ride")
    with pytest.raises(DomainError) as error:
        service.room_route(sid, renter, result["results"][0]["room_id"], "fly")
    assert error.value.code == "invalid_request"


def test_service_route_without_anchor_says_so(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    result = service.confirm(sid, renter, profile, service.session(sid, renter)["draft_revision"])
    assert result["results"]
    with pytest.raises(DomainError) as error:
        service.room_route(sid, renter, result["results"][0]["room_id"], "ride")
    assert error.value.code == "no_destination"


# --- session_routes() — cả danh sách căn qua một lần gọi ma trận ---

OSRM_TABLE_FOUR = (200, {"code": "Ok", "durations": [[310.0], [320.0], [330.0], [340.0]],
                         "distances": [[3100.0], [3200.0], [3300.0], [3400.0]]})


def _with_area_only_candidate(service, monkeypatch):
    """Tiêm một ứng viên `area_only` (chỉ biết khu vực) vào đầu tập đã qua lọc:
    pipeline thật loại căn không tọa độ khi hồ sơ có điểm neo, nên phải thêm sau
    filter (và đứng đầu, vì B1 không sort lại sau eligible_candidates) để dựng
    đúng tình huống 'kết quả hiển thị có căn thiếu tọa độ'."""
    real = service.catalog.eligible_candidates

    def inject(profile):
        candidates, diagnostics = real(profile)
        if candidates:
            injected = candidates[0].model_copy(
                update={"room_id": "synthetic-room-063", "score": candidates[0].score + 1,
                        "latitude": None, "longitude": None,
                        "location_accuracy": "area_only", "uncertainty_m": None})
            candidates = [injected] + candidates
        return candidates, diagnostics

    monkeypatch.setattr(service.catalog, "eligible_candidates", inject)


def test_service_session_routes_skips_area_only_and_keeps_result_order(service, renter, profile, monkeypatch):
    _with_area_only_candidate(service, monkeypatch)
    sid, result, destination = _published_with_anchor(service, renter, profile)
    fetch = FakeFetch({"osrm": OSRM_TABLE_FOUR})
    service.router = Router("osrm", fetch=fetch)
    routes = service.session_routes(sid, renter, "ride")
    assert routes["run_id"] == result["run_id"]
    assert routes["skipped"] == ["synthetic-room-063"]
    # items giữ đúng thứ tự trong kết quả, bỏ căn thiếu tọa độ.
    visible_ids = [entry["room_id"] for entry in result["results"]]
    assert [item["room_id"] for item in routes["items"]] == [
        room_id for room_id in visible_ids if room_id != "synthetic-room-063"]
    assert all(item["provider"] == "osrm" and item["fallback_reason"] is None
               for item in routes["items"])
    assert "geometry" not in routes["items"][0]
    assert routes["anchor"] == {"label": destination.label, "latitude": destination.latitude,
                                "longitude": destination.longitude,
                                "max_distance_m": destination.max_distance_m,
                                "uncertainty_m": destination.uncertainty_m}
    # Cả danh sách chỉ MỘT lần gọi nguồn ngoài cho 4 căn có tọa độ.
    assert len(fetch.calls) == 1 and fetch.calls[0][2]["sources"] == "0;1;2;3"
    assert fetch.calls[0][2]["destinations"] == "4"
    assert routes["attribution"] == "Đường đi © OpenStreetMap, OSRM (FOSSGIS)"


def test_service_session_routes_rejects_other_renters_and_bad_travel(service, renter, profile):
    sid, result, _ = _published_with_anchor(service, renter, profile)
    with pytest.raises(DomainError):
        service.session_routes(sid, Actor(id="renter-2", role="renter"), "ride")
    with pytest.raises(DomainError) as error:
        service.session_routes(sid, renter, "fly")
    assert error.value.code == "invalid_request"


def test_service_session_routes_without_anchor_says_so(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    result = service.confirm(sid, renter, profile, service.session(sid, renter)["draft_revision"])
    assert result["results"]
    with pytest.raises(DomainError) as error:
        service.session_routes(sid, renter, "ride")
    assert error.value.code == "no_destination"


def test_session_routes_endpoint_offline_returns_summaries(service, renter, profile):
    sid, result, _ = _published_with_anchor(service, renter, profile)
    headers = {"Authorization": "Bearer demo-renter"}
    with TestClient(create_app(lambda: service)) as client:
        response = client.get(f"/sessions/{sid}/routes", headers=headers, params={"travel": "walk"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["run_id"] == result["run_id"] and body["travel"] == "walk"
        assert body["anchor"]["label"] == "Khu đô thị Phú Mỹ Hưng" and body["skipped"] == []
        assert [item["room_id"] for item in body["items"]] == [
            entry["room_id"] for entry in result["results"]]
        assert all(item["provider"] == "straight_line" and item["fallback_reason"] == "no_provider"
                   and item["duration_s"] is None and "geometry" not in item
                   for item in body["items"])
        assert body["attribution"] is None
        bad = client.get(f"/sessions/{sid}/routes", headers=headers, params={"travel": "fly"})
        assert bad.status_code == 422
        other = client.get(f"/sessions/{sid}/routes", headers={"Authorization": "Bearer demo-owner2"})
        assert other.status_code in (403, 404)


def test_session_routes_endpoint_without_run_returns_empty_not_500(service, renter, profile):
    # QA vòng 1: hồ sơ có điểm neo nhưng chưa có lượt tìm (giữa hai bước confirm
    # hoặc run hỏng giữa chừng) — phải trả 200 rỗng, không phải 500.
    sid, _result, _ = _published_with_anchor(service, renter, profile)
    with service.repo.db:
        service.repo.db.execute("UPDATE hm_sessions SET active_run_id=NULL WHERE id=?", (sid,))
    fetch = FakeFetch({})
    service.router = Router("osrm", fetch=fetch)
    headers = {"Authorization": "Bearer demo-renter"}
    with TestClient(create_app(lambda: service)) as client:
        response = client.get(f"/sessions/{sid}/routes", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["run_id"] is None and body["items"] == [] and body["skipped"] == []
                and body["attribution"] is None)
        assert body["anchor"]["label"] == "Khu đô thị Phú Mỹ Hưng"
        assert fetch.calls == []  # không có căn nào thì không gọi nguồn ngoài


def test_route_endpoint_offline_returns_straight_line(service, renter, profile):
    sid, result, _ = _published_with_anchor(service, renter, profile)
    room_id = result["results"][0]["room_id"]
    headers = {"Authorization": "Bearer demo-renter"}
    with TestClient(create_app(lambda: service)) as client:
        response = client.get(f"/sessions/{sid}/rooms/{room_id}/route", headers=headers,
                              params={"travel": "walk"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["provider"] == "straight_line" and body["fallback_reason"] == "no_provider"
        assert body["duration_s"] is None
        assert body["travel"] == "walk" and body["anchor"]["label"] == "Khu đô thị Phú Mỹ Hưng"
        bad = client.get(f"/sessions/{sid}/rooms/{room_id}/route", headers=headers,
                         params={"travel": "fly"})
        assert bad.status_code == 422
        other = client.get(f"/sessions/{sid}/rooms/{room_id}/route",
                           headers={"Authorization": "Bearer demo-owner2"})
        assert other.status_code in (403, 404)
