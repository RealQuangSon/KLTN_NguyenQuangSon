"""AG-01/AG-03: per-field provenance contract and prioritized clarification questions."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.interpreter import DemoInterpreter
from backend.app.main import create_app
from backend.app.models import DraftPatch, DraftProfile
from backend.app.service import HomeMatchService


def test_chat_extraction_marks_touched_fields_inferred(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter,
                            "Tìm studio TP.HCM Quận 7 cho 2 người, thoáng, tầm 3 triệu")
    draft = reply["draft"]
    assert (draft["city"], draft["area"], draft["room_type"], draft["people"]) == \
        ("TP.HCM", "Quận 7", "studio", 2)
    status = draft["field_status"]
    for field in ("city", "area", "room_type", "people", "preferences", "budget_hint"):
        assert status[field] == "inferred", field
    for key in status:
        assert draft["evidence_ref"][key] == "chat:r1"


def test_form_patch_marks_confirmed_and_clear_returns_unknown(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM, thoáng")
    patched = service.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=1, set={"city": "TP.HCM", "people": 2}))
    assert patched["draft"]["field_status"]["city"] == "confirmed"
    assert patched["draft"]["evidence_ref"]["city"] == "form:r2"
    assert patched["draft"]["field_status"]["people"] == "confirmed"
    cleared = service.patch_draft(sid, renter, DraftPatch(
        expected_draft_revision=2, clear_fields=["city"]))
    assert cleared["draft"]["city"] is None
    assert cleared["draft"]["field_status"]["city"] == "unknown"
    assert "city" not in cleared["draft"]["evidence_ref"]


def test_chat_after_form_remarks_the_field_as_inferred(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0, set={"city": "Hà Nội"}))
    reply = service.message(sid, renter, "Giờ tìm ở TP.HCM")
    assert reply["draft"]["field_status"]["city"] == "inferred"
    assert reply["draft"]["evidence_ref"]["city"] == "chat:r2"


def test_fresh_session_asks_room_type_and_city_first(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Cho tôi xin chỗ ở")
    assert reply["questions"] == ["Bạn cần phòng trọ, studio hay căn hộ?",
                                  "Bạn muốn thuê tại thành phố nào?"]


def test_filled_fields_are_not_reasked_and_destination_asks_details(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter,
                            "Tìm phòng trọ TP.HCM cho 2 người gần trường, tầm 3 triệu")
    assert len(reply["questions"]) == 2
    assert reply["questions"][0].startswith("Mức tiền")
    assert "tên điểm đến" in reply["questions"][1] and "mét" in reply["questions"][1]
    assert not any("thành phố nào" in question for question in reply["questions"])
    assert not any("bao nhiêu người" in question for question in reply["questions"])


def test_draft_rejects_untracked_provenance_keys():
    assert DraftProfile().field_status == {}
    with pytest.raises(ValidationError):
        DraftProfile.model_validate({"field_status": {"max_monthly_cost_vnd": "confirmed"}})
    with pytest.raises(ValidationError):
        DraftProfile.model_validate({"field_status": {"city": "approved"}})


def test_demo_interpreter_extracts_room_type_only_when_stated():
    interpreter = DemoInterpreter()
    assert interpreter.extract("Tìm studio gần quận 7").room_type == "studio"
    assert interpreter.extract("Cần phòng trọ riêng").room_type == "room"
    assert interpreter.extract("Cần chỗ ở giá rẻ").room_type is None


def test_api_payload_carries_field_status(tmp_path):
    app = create_app(lambda: HomeMatchService(tmp_path / "field-status.sqlite"))
    headers = {"Authorization": "Bearer demo-renter-a"}
    with TestClient(app) as client:
        sid = client.post("/sessions", headers=headers).json()["session_id"]
        draft = client.post(f"/sessions/{sid}/messages", headers=headers,
                            json={"text": "Tìm phòng trọ TP.HCM, thoáng"}).json()["draft"]
        assert draft["field_status"]["city"] == "inferred"
        assert draft["evidence_ref"]["city"] == "chat:r1"
        patched = client.patch(f"/sessions/{sid}/draft", headers=headers,
                               json={"expected_draft_revision": 1, "set": {"people": 3},
                                     "clear_fields": [], "remove_preferences": []}).json()
        assert patched["draft"]["field_status"]["people"] == "confirmed"
        assert patched["draft"]["evidence_ref"]["people"] == "form:r2"
