"""Một thay đổi trong kho chỉ làm mất hiệu lực danh sách khi nó thật sự đổi danh sách đó (D-11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.models import Actor, CatalogStatus, Profile, Scenario

VIEWING_AT = datetime.now(timezone.utc) + timedelta(days=2)


def _flip(service, room_id: str, landlord: Actor, available: bool):
    room = service.catalog.room(room_id)
    service.change_room_status(room_id, landlord, CatalogStatus(expected_revision=room.revision, available=available))


def _owner(room) -> Actor:
    return Actor(id=room.landlord, role="owner")


def _confirmed(service, renter, profile) -> tuple[str, dict]:
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile, 0)
    result = service.results(sid, renter)
    assert result["status"] == "published" and result["results"]
    return sid, result


def _unrelated_room(service, profile: Profile):
    """Một phòng hồ sơ này vốn đã loại, nên đổi nó không thể đổi danh sách."""
    eligible = {item.room_id for item in service.catalog.rank(profile)[0]}
    return next(room for room in service.catalog.rooms() if room.id not in eligible and room.available)


def test_unrelated_room_change_keeps_results_compare_and_viewing(service, renter, profile):
    sid, before = _confirmed(service, renter, profile)
    listed = [item["room_id"] for item in before["results"]]
    assert len(listed) >= 2
    viewing = service.request_viewing(sid, renter, listed[0], VIEWING_AT, "freshness-1")

    other = _unrelated_room(service, profile)
    _flip(service, other.id, _owner(other), False)

    after = service.results(sid, renter)
    assert after["status"] == "published"
    assert [item["room_id"] for item in after["results"]] == listed
    assert len(service.compare(sid, renter, listed[:2])["items"]) == 2
    owner = _owner(service.catalog.room(listed[0]))
    assert service.respond_viewing(viewing["id"], owner, "confirmed")["status"] == "confirmed"


def test_revalidation_is_stamped_so_next_read_skips_ranking(service, renter, profile, monkeypatch):
    sid, before = _confirmed(service, renter, profile)
    other = _unrelated_room(service, profile)
    _flip(service, other.id, _owner(other), False)
    service.results(sid, renter)
    assert service.repo.run(before["run_id"])["catalog_version"] == service.catalog.version

    def fail(*_args, **_kwargs):
        raise AssertionError("không được xếp hạng lại khi kho không đổi")
    monkeypatch.setattr(service.catalog, "match", fail)
    assert service.results(sid, renter)["status"] == "published"


def test_listed_room_change_still_invalidates(service, renter, profile):
    sid, before = _confirmed(service, renter, profile)
    room = service.catalog.room(before["results"][-1]["room_id"])
    _flip(service, room.id, _owner(room), False)
    after = service.results(sid, renter)
    assert after["status"] == "invalidated" and after["results"] == []


def test_room_entering_the_list_invalidates(service, renter, profile):
    top = service.catalog.match(profile)[0][0]
    room = service.catalog.room(top.room_id)
    _flip(service, room.id, _owner(room), False)
    sid, before = _confirmed(service, renter, profile)
    assert room.id not in {item["room_id"] for item in before["results"]}
    _flip(service, room.id, _owner(room), True)
    assert service.results(sid, renter)["status"] == "invalidated"


def test_empty_result_survives_unrelated_change(service, renter):
    impossible = Profile(city="TP.HCM", area="Quận 7", max_monthly_cost_vnd=1,
                         max_initial_cash_vnd=1, scenario=Scenario())
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, impossible, 0)
    status = service.results(sid, renter)["status"]
    assert status in ("no_match", "needs_verification")
    other = _unrelated_room(service, impossible)
    _flip(service, other.id, _owner(other), False)
    assert service.results(sid, renter)["status"] == status


def test_run_still_generating_is_never_revalidated(service, renter, profile):
    sid, _ = _confirmed(service, renter, profile)
    run = service.repo.create_run(service.repo.session(sid), "phien-ban-cu")
    assert service.results(sid, renter)["status"] == "invalidated"
    assert service.repo.run(run["id"])["status"] == "invalidated"


def test_revalidation_refreshes_total_matches(service, renter, profile):
    """D-12 + D-11: revalidate ghi lại tổng số căn khớp mới, không giữ số cũ."""
    sid, before = _confirmed(service, renter, profile)
    total = before["total_matches"]
    assert total is not None and total >= len(before["results"])
    other = _unrelated_room(service, profile)
    _flip(service, other.id, _owner(other), False)
    after = service.results(sid, renter)
    assert after["status"] == "published" and after["total_matches"] == total
    assert after["search_path"] and after["search_path"].startswith("/tim-kiem?")


def test_legacy_needs_verification_run_is_readable_then_invalidated_on_catalog_change(service, renter, profile):
    """D-12: run cũ needs_verification vẫn ĐỌC được (không có căn hiển thị, không có
    câu mời ước tính); khi kho đổi, xếp hạng mới cho trạng thái khác nên run hết hiệu lực."""
    sid, before = _confirmed(service, renter, profile)
    with service.repo.db:
        service.repo.db.execute("UPDATE hm_runs SET status='needs_verification', items_json='[]' WHERE id=?",
                                (before["run_id"],))
    legacy = service.results(sid, renter)
    assert legacy["status"] == "needs_verification" and legacy["results"] == []
    assert all("chấp nhận" not in text.lower() for text in legacy.get("suggested_prompts") or [])
    other = _unrelated_room(service, profile)
    _flip(service, other.id, _owner(other), False)
    assert service.results(sid, renter)["status"] == "invalidated"
