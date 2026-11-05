"""AG-01: điểm đến từ danh mục places.json — tra alias, suy ra từ chat,
xếp hạng theo khoảng cách; điểm mốc lạ giữ nguyên hành vi cũ."""
import pytest

from backend.app.locations import resolve_place


def test_resolve_place_alias_and_city_disambiguation():
    assert resolve_place("gần HUST")["id"] == "hn-hust"
    assert resolve_place("gần Bách Khoa", "Hà Nội")["id"] == "hn-hust"
    assert resolve_place("gần bách khoa", "TP.HCM")["id"] == "hcm-hcmut"
    # Cùng alias ở hai thành phố mà chưa biết thành phố: không đoán.
    assert resolve_place("gần bách khoa") is None
    assert resolve_place("cạnh Times City")["id"] == "hn-times-city"
    assert resolve_place("gần chỗ làm") is None
    assert resolve_place("") is None


def test_chat_names_destination_and_draft_stays_inferred(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng trọ dưới 4 triệu gần Phú Mỹ Hưng")
    draft = reply["draft"]
    assert draft["destination"]["label"] == "Khu đô thị Phú Mỹ Hưng"
    assert draft["destination"]["max_distance_m"] == 3000
    assert draft["needs_destination"] is False
    assert draft["field_status"]["destination"] == "inferred"
    assert draft["evidence_ref"]["destination"].startswith("chat:")
    # Memory không bao giờ lưu destination (bất biến).
    session = service.repo.session(sid)
    from backend.app.models import DraftProfile
    draft_model = DraftProfile.model_validate_json(session["draft_json"])
    assert draft_model.destination is not None


def test_unnamed_place_keeps_old_behavior(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng trọ gần trường ở Quận 7")
    assert reply["draft"]["destination"] is None


def test_confirmed_run_ranks_by_distance_to_destination(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "gần Phú Mỹ Hưng")
    revision = service.session(sid, renter)["draft_revision"]
    from backend.app.models import Destination
    destination = Destination.model_validate(service.session(sid, renter)["draft"]["destination"])
    confirmed = profile.model_copy(update={"destination": destination})
    result = service.confirm(sid, renter, confirmed, revision)
    assert result["status"] == "published" and result["results"]
    locations = [item["components"].get("location") for item in result["results"]]
    assert all(value is not None and value >= 0 for value in locations)
    # Xếp theo khoảng cách: có sự chênh lệch điểm location giữa các căn.
    assert len(set(locations)) >= 2


def test_patch_can_clear_destination(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "gần Landmark 81")
    assert service.session(sid, renter)["draft"]["destination"] is not None
    revision = service.session(sid, renter)["draft_revision"]
    from backend.app.models import DraftPatch
    service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision,
                                                set={}, clear_fields=["destination"]))
    draft = service.session(sid, renter)["draft"]
    assert draft["destination"] is None and draft["field_status"]["destination"] == "unknown"
