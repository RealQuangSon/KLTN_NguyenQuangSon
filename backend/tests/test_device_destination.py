"""điểm neo từ vị trí thiết bị, có hỏi đồng ý gửi ra ngoài.

Trình duyệt lấy vị trí rồi PUT /sessions/{id}/destination/device: tọa độ làm
tròn 3 chữ số (~100 m) TRƯỚC khi kiểm tra/lưu, kiểm vùng phục vụ từ khung bao
các căn đang công bố, rồi chạy đúng đường chip (tự xác nhận, xếp hạng). Tọa độ
chỉ gửi ra Goong/OSRM khi khách đồng ý (PUT /sessions/{id}/route-consent);
không đồng ý thì chỉ chim bay (fallback_reason="no_consent") và tọa độ không
bao giờ vào LLM/Jev (build_context/decision_context đã redact). Không gọi mạng:
fetch giả tái dùng test_routes_map.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import clarify as clarify_layer
from backend.app import memory
from backend.app.agent_loop import build_context
from backend.app.decisions import decision_context
from backend.app.main import create_app
from backend.app.models import Actor, DomainError, DraftPatch
from backend.app.routes_map import Router
from backend.app.service import HomeMatchService
from backend.tests.test_routes_map import OSRM_OK, FakeFetch

# demo-01 trong kho test: (10.7351, 106.721) — vị trí thiết bị lệch nhỏ quanh đó.
DEVICE_LAT, DEVICE_LNG = 10.73512, 106.72104
ROUNDED_LAT, ROUNDED_LNG = 10.735, 106.721


def _ask_anchor(service, renter, text="Tìm phòng ở TP.HCM dưới 4 triệu gần tôi"):
    """Mở phiên và nói "gần tôi" — hệ thống hỏi lại điểm neo kèm chip thiết bị."""
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, text)
    return sid, reply


def _published_with_device_anchor(service, renter, allow_routing=False):
    sid, reply = _ask_anchor(service, renter)
    assert reply["clarification"]["field"] == "destination"
    revision = service.session(sid, renter)["draft_revision"]
    result = service.set_device_destination(sid, renter, DEVICE_LAT, DEVICE_LNG, 30,
                                            allow_routing, revision)
    assert result["status"] == "published" and result["message"]
    results = service.results(sid, renter)
    assert results["results"]
    return sid, results


# --- Đặt điểm neo hợp lệ ---

def test_device_destination_sets_anchor_and_runs_search(service, renter):
    sid, _ = _ask_anchor(service, renter)
    revision = service.session(sid, renter)["draft_revision"]
    result = service.set_device_destination(sid, renter, DEVICE_LAT, DEVICE_LNG, 30,
                                            False, revision)
    assert result["status"] == "published"
    assert result["message"]
    draft = service._draft(sid)
    assert draft.destination.source == "device"
    # Tọa độ đã làm tròn 3 chữ số trước khi lưu.
    assert (draft.destination.latitude, draft.destination.longitude) == (ROUNDED_LAT, ROUNDED_LNG)
    assert draft.destination.label == "Vị trí hiện tại của bạn"
    assert draft.destination.uncertainty_m == 100  # max(30, 100)
    assert draft.field_status["destination"] == "confirmed"
    assert draft.evidence_ref["destination"].startswith("clarify:")
    assert draft.needs_destination is False
    assert service.results(sid, renter)["status"] == "published"


def test_device_destination_fills_city_when_draft_has_none(service, renter):
    """Nháp chưa có thành phố (chỉ nói "gần tôi" không nêu phố) → ghi thành phố chứa vị trí."""
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "4 triệu gần tôi")
    assert service._draft(sid).city is None
    revision = service.session(sid, renter)["draft_revision"]
    result = service.set_device_destination(sid, renter, DEVICE_LAT, DEVICE_LNG, 30,
                                            False, revision)
    draft = service._draft(sid)
    assert draft.city == "TP.HCM"
    assert result["status"] == "published"


# --- Lỗi ---

def test_device_destination_outside_service_area(service, renter):
    sid, _ = _ask_anchor(service, renter)
    revision = service.session(sid, renter)["draft_revision"]
    with pytest.raises(DomainError) as error:
        service.set_device_destination(sid, renter, 12.234, 100.034, 30, False, revision)
    assert error.value.code == "outside_service_area"
    assert error.value.http_status == 422
    assert service._draft(sid).destination is None


def test_device_destination_imprecise(service, renter):
    sid, _ = _ask_anchor(service, renter)
    revision = service.session(sid, renter)["draft_revision"]
    with pytest.raises(DomainError) as error:
        service.set_device_destination(sid, renter, DEVICE_LAT, DEVICE_LNG, 5000, False, revision)
    assert error.value.code == "location_imprecise"
    assert error.value.http_status == 422


def test_device_destination_rejects_other_renter(service, renter):
    sid, _ = _ask_anchor(service, renter)
    revision = service.session(sid, renter)["draft_revision"]
    with pytest.raises(DomainError):
        service.set_device_destination(sid, Actor(id="renter-2", role="renter"),
                                       DEVICE_LAT, DEVICE_LNG, 30, False, revision)
    with pytest.raises(DomainError):
        service.set_route_consent(sid, Actor(id="renter-2", role="renter"), True)


def test_device_destination_stale_revision_same_error_as_patch_draft(service, renter):
    sid, _ = _ask_anchor(service, renter)
    revision = service.session(sid, renter)["draft_revision"]
    with pytest.raises(DomainError) as error:
        service.set_device_destination(sid, renter, DEVICE_LAT, DEVICE_LNG, 30,
                                       False, revision + 5)
    assert error.value.code == "stale_profile"
    assert error.value.http_status == 409


@pytest.fixture
def full_catalog(tmp_path, monkeypatch):
    """Kho tổng hợp hai thành phố tách biệt — để dựng lỗi khác thành phố."""
    monkeypatch.setenv("HOMEMATCH_CATALOG_PATH", "data/catalog/rooms.json")
    agent = HomeMatchService(tmp_path / "device-full.sqlite")
    yield agent
    agent.close()


def test_device_destination_outside_city_of_draft(full_catalog, renter):
    sid, reply = _ask_anchor(full_catalog, renter, "Tìm phòng ở Hà Nội dưới 4 triệu gần tôi")
    assert reply["draft"]["city"] == "Hà Nội"
    revision = full_catalog.session(sid, renter)["draft_revision"]
    with pytest.raises(DomainError) as error:
        # Vị trí ở TP.HCM (căn synthetic-room-001 + lệch nhỏ) khi nháp đang tìm Hà Nội.
        full_catalog.set_device_destination(sid, renter, DEVICE_LAT, DEVICE_LNG, 30,
                                            False, revision)
    assert error.value.code == "outside_city"
    assert error.value.http_status == 422
    assert "Hà Nội" in str(error.value)


def test_patch_draft_rejects_device_destination(service, renter):
    sid = service.create_session(renter)["session_id"]
    revision = service.session(sid, renter)["draft_revision"]
    device = {"label": "Vị trí hiện tại của bạn", "latitude": ROUNDED_LAT,
              "longitude": ROUNDED_LNG, "uncertainty_m": 100,
              "max_distance_m": 3000, "source": "device"}
    for source in ("form", "clarify"):
        with pytest.raises(DomainError) as error:
            service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision,
                                                        set={"destination": device}, source=source))
        assert error.value.code == "invalid_patch"
        assert error.value.http_status == 422


# --- Chỉ đường tôn trọng đồng ý ---

def test_no_consent_keeps_routes_straight_and_fetch_uncalled(service, renter):
    sid, results = _published_with_device_anchor(service, renter, allow_routing=False)
    fetch = FakeFetch({"osrm": OSRM_OK})
    service.router = Router("osrm", fetch=fetch)
    item = next(entry for entry in results["results"] if entry["latitude"] is not None)
    route = service.room_route(sid, renter, item["room_id"], "ride")
    assert route["provider"] == "straight_line"
    assert route["fallback_reason"] == "no_consent"
    assert route["duration_s"] is None
    assert route["distance_m"] == route["straight_line_m"]
    routes = service.session_routes(sid, renter, "ride")
    assert routes["items"]
    assert all(entry["fallback_reason"] == "no_consent" and entry["duration_s"] is None
               for entry in routes["items"])
    assert routes["attribution"] is None
    assert fetch.calls == [], "chưa đồng ý thì không được gọi nguồn ngoài"


def test_consent_switch_routes_externally_with_rounded_coordinates(service, renter, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_ROUTE_PROVIDER", "osrm")
    sid, results = _published_with_device_anchor(service, renter, allow_routing=True)
    fetch = FakeFetch({"osrm": OSRM_OK})
    service.router = Router("osrm", fetch=fetch)
    assert service.set_route_consent(sid, renter, True) == {"allow": True}
    item = next(entry for entry in results["results"] if entry["latitude"] is not None)
    route = service.room_route(sid, renter, item["room_id"], "ride")
    assert route["provider"] == "osrm" and route["fallback_reason"] is None
    assert fetch.calls, "đã đồng ý thì được gọi nguồn ngoài"
    # Chỉ tọa độ đã làm tròn 3 chữ số của điểm neo đi ra ngoài.
    assert f"{ROUNDED_LNG},{ROUNDED_LAT}" in fetch.calls[0][1]
    assert f"{DEVICE_LNG},{DEVICE_LAT}" not in fetch.calls[0][1]


def test_restart_defaults_back_to_no_consent(tmp_path, renter, monkeypatch):
    db_path = tmp_path / "device-restart.sqlite"
    monkeypatch.setenv("HOMEMATCH_ROUTE_PROVIDER", "osrm")
    service = HomeMatchService(db_path)
    sid, results = _published_with_device_anchor(service, renter, allow_routing=True)
    service.close()
    revived = HomeMatchService(db_path)
    try:
        fetch = FakeFetch({"osrm": OSRM_OK})
        revived.router = Router("osrm", fetch=fetch)
        item = next(entry for entry in results["results"] if entry["latitude"] is not None)
        route = revived.room_route(sid, renter, item["room_id"], "ride")
        assert route["fallback_reason"] == "no_consent"
        assert fetch.calls == []
    finally:
        revived.close()


# --- Tọa độ thiết bị không đi ra ngoài (mục 5) ---

def test_build_context_and_decision_context_hide_device_coordinates(service, renter):
    sid, _ = _published_with_device_anchor(service, renter)
    session = service.repo.session(sid)
    context_json = build_context(service, session, renter)
    decision_json = json.dumps(decision_context(service._agent_context(session)),
                               ensure_ascii=False, default=str)
    for payload in (context_json, decision_json):
        assert "Vị trí hiện tại của bạn" in payload
        for leaked in (str(ROUNDED_LAT), str(ROUNDED_LNG), str(DEVICE_LAT), str(DEVICE_LNG)):
            assert leaked not in payload, leaked
    # DTO cho chính khách vẫn đủ tọa độ để vẽ bản đồ.
    own = service.session(sid, renter)
    assert own["draft"]["destination"]["latitude"] == ROUNDED_LAT
    assert own["confirmed_profile"]["destination"]["source"] == "device"


def test_memory_has_no_device_destination(service, renter):
    _published_with_device_anchor(service, renter)
    stored = json.dumps(memory.recall(service.repo, renter.id), ensure_ascii=False, default=str)
    assert "destination" not in stored
    assert str(ROUNDED_LAT) not in stored and str(ROUNDED_LNG) not in stored


# --- Chip "Dùng vị trí hiện tại" ---

def test_device_chip_leads_destination_question_for_current_kind(service, renter):
    sid, reply = _ask_anchor(service, renter)
    dto = reply["clarification"]
    assert dto["field"] == "destination"
    first = dto["options"][0]
    assert first["kind"] == "device_location"
    assert first["label"] == "Dùng vị trí hiện tại"
    assert first["action"] == "geolocate"
    assert first["count"] is None
    assert first["patch"] == {"set": {}}, "chip thiết bị không áp patch — FE tự lấy vị trí"


def test_device_chip_absent_for_school_and_personal_kinds(service, renter):
    sid = service.create_session(renter)["session_id"]
    school = service.message(sid, renter, "Tìm phòng ở TP.HCM dưới 4 triệu gần trường")
    assert school["draft"]["destination_kind"] == "school"
    payload = json.dumps(school.get("clarification") or {}, ensure_ascii=False)
    assert "device_location" not in payload and "Dùng vị trí hiện tại" not in payload

    sid2 = service.create_session(renter)["session_id"]
    personal = service.message(sid2, renter, "Tìm phòng dưới 4 triệu gần công ty tôi ở Cầu Giấy")
    assert personal["draft"]["destination_kind"] == "personal"
    assert (personal.get("clarification") or {}).get("field") != "destination"
    payload2 = json.dumps(personal.get("clarification") or {}, ensure_ascii=False)
    assert "device_location" not in payload2 and "Dùng vị trí hiện tại" not in payload2


def test_current_with_empty_place_list_still_asks_with_only_device_chip(service, renter, monkeypatch):
    """Danh sách địa danh rỗng: chip thiết bị vẫn dựng được nên "gần tôi" LUÔN hỏi lại."""
    monkeypatch.setattr(clarify_layer, "_destination_interpretations", lambda *args, **kwargs: [])
    sid, reply = _ask_anchor(service, renter, "Tìm phòng ở Hà Nội dưới 4 triệu gần tôi")
    assert reply["status"] != "published"
    assert not reply.get("active_run_id")
    dto = reply["clarification"]
    assert dto["field"] == "destination"
    assert [option["kind"] for option in dto["options"]] == ["device_location"]


def test_personal_work_place_publishes_with_city_notice(service, renter, monkeypatch):
    """Giữ nguyên: "gần chỗ tôi làm" không có chip thiết bị, tìm kèm câu báo đúng một lần."""
    monkeypatch.setattr(clarify_layer, "_destination_interpretations", lambda *args, **kwargs: [])
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng ở Hà Nội dưới 4 triệu gần chỗ tôi làm")
    assert reply["status"] == "published"
    assert reply["message"].count("Mình chưa biết") == 1
    payload = json.dumps(reply.get("clarification") or {}, ensure_ascii=False)
    assert "device_location" not in payload


# --- Endpoint ---

def test_device_destination_and_consent_endpoints(service, renter):
    sid, _ = _ask_anchor(service, renter)
    revision = service.session(sid, renter)["draft_revision"]
    headers = {"Authorization": "Bearer demo-renter"}
    body = {"latitude": DEVICE_LAT, "longitude": DEVICE_LNG, "accuracy_m": 30,
            "allow_routing": False, "expected_draft_revision": revision}
    with TestClient(create_app(lambda: service)) as client:
        ok = client.put(f"/sessions/{sid}/destination/device", headers=headers, json=body)
        assert ok.status_code == 200, ok.text
        assert ok.json()["status"] == "published"
        assert ok.json()["draft"]["destination"]["source"] == "device"

        consent = client.put(f"/sessions/{sid}/route-consent", headers=headers,
                             json={"allow": True})
        assert consent.status_code == 200, consent.text
        assert consent.json() == {"allow": True}

        stale = client.put(f"/sessions/{sid}/destination/device", headers=headers,
                           json={**body, "expected_draft_revision": revision + 9})
        assert stale.status_code == 409
        imprecise = client.put(f"/sessions/{sid}/destination/device", headers=headers,
                               json={**body, "accuracy_m": 5000,
                                     "expected_draft_revision": ok.json()["draft_revision"]})
        assert imprecise.status_code == 422
        assert imprecise.json()["error"]["code"] == "location_imprecise"
        outside = client.put(f"/sessions/{sid}/destination/device", headers=headers,
                             json={**body, "latitude": 12.234, "longitude": 100.034,
                                   "expected_draft_revision": ok.json()["draft_revision"]})
        assert outside.status_code == 422
        assert outside.json()["error"]["code"] == "outside_service_area"

        forbidden = client.put(f"/sessions/{sid}/route-consent",
                               headers={"Authorization": "Bearer demo-owner2"},
                               json={"allow": True})
        assert forbidden.status_code in (403, 404)
