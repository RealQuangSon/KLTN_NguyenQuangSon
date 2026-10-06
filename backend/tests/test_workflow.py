import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.catalog import Catalog
from backend.app.models import Actor, DomainError, Review
from backend.app.service import HomeMatchService


def pending(service, renter, profile):
    session_id = service.create_session(renter)["session_id"]
    result = service.confirm(session_id, renter, profile, 0)
    return session_id, result["run_id"]


def approval(version=1, **changes):
    return Review(decision="approve", expected_profile_version=version,
                  reason="Đã kiểm tra dữ liệu demo.", idempotency_key="review-1", **changes)


def test_pending_draft_is_hidden_and_wrong_manager_cannot_approve(service, renter, landlord, profile):
    sid, run_id = pending(service, renter, profile)
    view = service.results(sid, renter)
    assert view["status"] == "pending_review" and view["results"] == []
    assert "items" not in view and "diagnostics" not in view
    with pytest.raises(DomainError, match="không có quyền"):
        service.review(run_id, Actor(id="owner-b", role="owner"), approval())
    with pytest.raises(DomainError):
        service.results(sid, Actor(id="renter-b", role="renter"))
    with pytest.raises(DomainError):
        service.draft(run_id, renter)
    assert service.draft(run_id, landlord)["items"]


def test_approval_subset_order_idempotence_and_conflict(service, renter, landlord, profile):
    sid, run_id = pending(service, renter, profile)
    ids = [item["room_id"] for item in service.draft(run_id, landlord)["items"]][:2][::-1]
    with pytest.raises(DomainError) as missing:
        service.review(run_id, landlord, approval(keep_room_ids=ids))
    assert missing.value.code == "override_reason_required"
    request = approval(keep_room_ids=ids, override_reason="Khách ưu tiên phòng rẻ hơn.")
    first = service.review(run_id, landlord, request)
    assert first["decision"]["overridden"] and first["decision"]["agent_order"][:2] == ids[::-1]
    assert service.review(run_id, landlord, request)["decision"] == first["decision"]
    assert [item["room_id"] for item in service.results(sid, renter)["results"]] == ids
    with pytest.raises(DomainError):
        service.review(run_id, landlord, approval(keep_room_ids=ids[:1]))


@pytest.mark.parametrize("decision", ["reject", "needs_revision"])
def test_other_review_decisions_do_not_publish(service, renter, landlord, profile, decision):
    sid, run_id = pending(service, renter, profile)
    service.review(run_id, landlord, Review(decision=decision, expected_profile_version=1,
                                          reason="Cần kiểm tra lại.", idempotency_key="review"))
    assert service.results(sid, renter)["results"] == []
    assert service.results(sid, renter)["status"] in {"rejected", "needs_revision"}


def test_manager_cannot_inject_room_outside_eligible_draft(service, renter, landlord, profile):
    _, run_id = pending(service, renter, profile)
    with pytest.raises(DomainError):
        service.review(run_id, landlord, approval(keep_room_ids=["demo-06"]))


def test_profile_revision_invalidates_old_approval(service, renter, landlord, profile):
    sid, run_id = pending(service, renter, profile)
    revision = service.session(sid, renter)["draft_revision"]
    service.confirm(sid, renter, profile, revision)
    assert service.repo.run(run_id)["status"] == "invalidated"
    with pytest.raises(DomainError):
        service.review(run_id, landlord, approval())
    with pytest.raises(DomainError):
        service.confirm(sid, renter, profile, revision)


@pytest.mark.parametrize("already_published", [False, True])
def test_catalog_change_invalidates_draft_or_published(tmp_path, renter, landlord, profile, already_published):
    path = tmp_path / "rooms.json"
    payload = {"rooms": [room.model_dump(mode="json") for room in Catalog().rooms()]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    service = HomeMatchService(tmp_path / "db.sqlite", catalog=Catalog(path))
    try:
        sid, run_id = pending(service, renter, profile)
        if already_published:
            service.review(run_id, landlord, approval())
        payload["rooms"][0]["quote"]["rent_vnd"] += 100_000
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert service.results(sid, renter)["status"] == "invalidated"
        assert service.results(sid, renter)["results"] == []
        with pytest.raises(DomainError):
            service.review(run_id, landlord, approval())
    finally:
        service.close()


@pytest.mark.parametrize("event_already_saved", [False, True])
def test_durable_restart_and_review_event_retry(tmp_path, renter, landlord, profile, event_already_saved):
    path = tmp_path / "durable.sqlite"
    first = HomeMatchService(path)
    sid, run_id = pending(first, renter, profile)
    if event_already_saved:
        first.repo.review(run_id, landlord.id, approval())  # crash window before graph resume
    first.close()
    second = HomeMatchService(path)
    try:
        assert second.results(sid, renter)["results"] == []
        second.review(run_id, landlord, approval())
        assert second.results(sid, renter)["status"] == "published"
        assert second.results(sid, renter)["results"]
    finally:
        second.close()


def test_compare_visibility_and_limit(service, renter, landlord, profile):
    sid, run_id = pending(service, renter, profile)
    with pytest.raises(DomainError):
        service.compare(sid, renter, ["demo-01", "demo-02"])
    service.review(run_id, landlord, approval())
    ids = [item["room_id"] for item in service.results(sid, renter)["results"]]
    assert len(service.compare(sid, renter, ids[:2])["items"]) == 2
    with pytest.raises(DomainError):
        service.compare(sid, renter, ids[:4])


def test_viewing_is_internal_pending_idempotent_and_authorized(service, renter, landlord, profile):
    sid, run_id = pending(service, renter, profile)
    time = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(DomainError):
        service.request_viewing(sid, renter, "demo-01", time, "key")
    service.review(run_id, landlord, approval())
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
    _, run_id = pending(service, renter, profile)
    assert service.repo.run(run_id)["status"] == "no_match"
