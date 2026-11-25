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
        # Lỗi 1/việc nhỏ (15/11): budget_scope do lớp hỏi lại tự chấp nhận (p_max
        # ≥ ngưỡng, giả định được nêu trong câu trả lời) → evidence clarify:auto;
        # các trường trích từ câu khách giữ evidence chat:r1.
        if key == "budget_scope":
            assert draft["evidence_ref"][key].startswith(("chat:", "clarify:auto-")), key
        else:
            assert draft["evidence_ref"][key] == "chat:r1", key


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


def test_fresh_session_asks_only_city(service, renter):
    # Không hỏi người/xe (mặc định 1/1, sửa được trong
    # "Nhu cầu của tôi") — chỉ hỏi thứ thật sự chặn là địa bàn.
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Cho tôi xin chỗ ở")
    assert reply["questions"] == ["Bạn muốn thuê tại thành phố nào?"]


def test_first_message_with_a_district_pins_the_city(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter,
                            "Mình muốn thuê chỗ ở thoáng mát, gần trường học cho 2 người ở Bình Thạnh")
    draft = reply["draft"]
    assert draft["city"] == "TP.HCM"
    assert draft["area"] == "Quận Bình Thạnh"
    assert draft["people"] == 2
    assert draft["field_status"]["city"] == "inferred"
    assert draft["evidence_ref"]["city"] == "chat:r1"
    # Room type is never interrogated; the district already answered the city.
    # 18/11: chưa có mức tiền thì CHƯA chạy tìm — hỏi mức tiền thay vì hứa "Mình chạy
    # tìm… kết quả sẽ tự hiện" (câu cũ sai). "Gần trường học" chưa nêu tên được ghi
    # loại điểm đến để hỏi trường nào khi đã đủ dữ liệu tìm.
    assert reply["questions"] == ["Bạn muốn chi bao nhiêu mỗi tháng?"]
    assert draft["needs_destination"] is True and draft["destination_kind"] == "school"
    assert not any("thành phố nào" in question for question in reply["questions"])
    assert not any("phòng trọ, studio" in question for question in reply["questions"])


def test_filled_fields_are_not_reasked_and_destination_asks_details(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter,
                            "Tìm phòng trọ TP.HCM cho 2 người gần trường, tầm 3 triệu")
    # Không hỏi lại mức tiền (hiểu là trần tổng tháng) hay số người (mặc định 1/1).
    # HN-13.2: "gần trường" không nêu tên → chip ĐIỂM MỘC THẬT hỏi "gần đâu?".
    # 18/11: khách nói "trường" → câu hỏi và chip theo đúng loại (các trường).
    assert len(reply["questions"]) == 1
    assert reply["questions"][0] == "Bạn muốn ở gần trường nào?"
    options = (reply.get("clarification") or {}).get("options") or []
    assert options and all(option["text"].startswith("gần ") and option["count"] > 0
                           for option in options)
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
    headers = {"Authorization": "Bearer demo-renter"}
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
