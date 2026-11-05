import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.catalog import Catalog
from backend.app.models import Actor, DomainError
from backend.app.service import HomeMatchService


def run_for(service, renter, profile):
    session_id = service.create_session(renter)["session_id"]
    result = service.confirm(session_id, renter, profile, 0)
    return session_id, result["run_id"]


def test_confirm_publishes_results_in_one_turn(service, renter, profile):
    sid, run_id = run_for(service, renter, profile)
    run = service.repo.run(run_id)
    assert run["status"] == "published" and run["items"]
    view = service.results(sid, renter)
    assert view["status"] == "published" and view["results"]
    # DTO nhỏ có chủ đích: không bao giờ lộ state/draft/items thô của graph.
    assert "items" not in view and "diagnostics" not in view
    # Người thuê khác không đọc được kết quả của phiên người khác.
    with pytest.raises(DomainError):
        service.results(sid, Actor(id="renter-b", role="renter"))


def test_profile_revision_invalidates_old_run(service, renter, profile):
    sid, run_id = run_for(service, renter, profile)
    revision = service.session(sid, renter)["draft_revision"]
    service.confirm(sid, renter, profile, revision)
    # Run cũ hết hiệu lực; phiên dùng run mới đã công bố.
    assert service.repo.run(run_id)["status"] == "invalidated"
    assert service.results(sid, renter)["status"] == "published"
    with pytest.raises(DomainError):
        service.confirm(sid, renter, profile, revision)  # revision đã tiêu thụ


@pytest.mark.parametrize("already_published", [False, True])
def test_catalog_change_invalidates_draft_or_published(tmp_path, renter, profile, already_published):
    path = tmp_path / "rooms.json"
    payload = {"rooms": [room.model_dump(mode="json") for room in Catalog().rooms()]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    service = HomeMatchService(tmp_path / "db.sqlite", catalog=Catalog(path))
    try:
        sid, run_id = run_for(service, renter, profile)
        assert service.results(sid, renter)["status"] == "published" if already_published else True
        payload["rooms"][0]["quote"]["rent_vnd"] += 100_000
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert service.results(sid, renter)["status"] == "invalidated"
        assert service.results(sid, renter)["results"] == []
    finally:
        service.close()


def test_durable_restart_keeps_published_results(tmp_path, renter, profile):
    path = tmp_path / "durable.sqlite"
    first = HomeMatchService(path)
    sid, run_id = run_for(first, renter, profile)
    assert first.results(sid, renter)["status"] == "published"
    first.close()
    second = HomeMatchService(path)
    try:
        view = second.results(sid, renter)
        assert view["status"] == "published" and view["results"]
    finally:
        second.close()


def test_compare_visibility_and_limit(service, renter, profile):
    sid, _ = run_for(service, renter, profile)
    ids = [item["room_id"] for item in service.results(sid, renter)["results"]]
    visible = set(ids)
    outside = [room.id for room in service.catalog.rooms() if room.id not in visible][:2]
    with pytest.raises(DomainError):
        service.compare(sid, renter, outside)  # phòng ngoài kết quả hiện tại
    assert len(service.compare(sid, renter, ids[:2])["items"]) == 2
    with pytest.raises(DomainError):
        service.compare(sid, renter, ids[:4])


def test_viewing_is_internal_pending_idempotent_and_authorized(service, renter, landlord, profile):
    sid, _ = run_for(service, renter, profile)
    time = datetime.now(timezone.utc) + timedelta(days=1)
    visible = {item["room_id"] for item in service.results(sid, renter)["results"]}
    outside = next(room.id for room in service.catalog.rooms() if room.id not in visible)
    with pytest.raises(DomainError):
        service.request_viewing(sid, renter, outside, time, "key")
    room_id = service.results(sid, renter)["results"][0]["room_id"]
    viewing = service.request_viewing(sid, renter, room_id, time, "key")
    assert viewing["status"] == "requested"
    assert service.request_viewing(sid, renter, room_id, time, "key") == viewing
    with pytest.raises(DomainError):
        service.request_viewing(sid, renter, room_id, time + timedelta(hours=1), "key")
    with pytest.raises(DomainError):
        service.respond_viewing(viewing["id"], Actor(id="owner-b", role="owner"), "confirmed")
    assert service.respond_viewing(viewing["id"], landlord, "confirmed")["status"] == "confirmed"
    with pytest.raises(DomainError):
        service.respond_viewing(viewing["id"], landlord, "declined")


def test_empty_catalog_match_is_explicit(service, renter, profile):
    profile.city = "Đà Nẵng"
    _, run_id = run_for(service, renter, profile)
    assert service.repo.run(run_id)["status"] == "no_match"
