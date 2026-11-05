"""AG-09: handover sang chủ nhà từ câu chat — intent tách khỏi human_support,
không lộ thu nhập trong ngữ cảnh, căn ngoài kết quả hiện tại bị từ chối."""
import pytest

from backend.app.interpreter import fixed_intent
from backend.app.models import Actor, DomainError


def test_intent_routing_splits_landlord_from_admin():
    assert fixed_intent("cho tôi chat với chủ nhà") == "landlord_handover"
    assert fixed_intent("muốn nói chuyện với chủ nhà căn này") == "landlord_handover"
    assert fixed_intent("gặp chủ nhà giúp mình") == "landlord_handover"
    # Người thật/nhân viên/quản trị vẫn là ticket admin.
    assert fixed_intent("cho gặp người thật") == "human_support"
    assert fixed_intent("gặp quản lý") == "human_support"


def test_handover_from_chat_publishes_conversation_without_income(service, renter, landlord, profile):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile.model_copy(update={"monthly_income_vnd": 20_000_000}), 0)
    reply = service.message(sid, renter, "cho tôi chat với chủ nhà căn số 1")
    assert reply["intent"] == "landlord_handover" and reply["status"] == "handover"
    assert reply["conversation_id"]
    # Ngữ cảnh chuyển cho chủ nhà chỉ gồm band, không bao giờ thu nhập.
    row = service.repo.db.execute(
        "SELECT context_json FROM hm_conversations WHERE id=?", (reply["conversation_id"],)).fetchone()
    blob = row["context_json"] or "{}"
    assert "monthly_income_vnd" not in blob and "20000000" not in blob
    # Chủ nhà nhận thông báo hội thoại mới.
    rows = service.repo.db.execute(
        "SELECT kind FROM hm_notifications WHERE user_id=?", (landlord.id,)).fetchall()
    assert any(item["kind"] == "conversation_started" for item in rows)


def test_handover_without_a_named_room_asks_with_visible_options(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile, 0)
    reply = service.message(sid, renter, "cho tôi nói chuyện với chủ nhà")
    assert reply["intent"] == "landlord_handover" and reply["status"] == "needs_clarification"
    assert any("căn nào" in question for question in reply["questions"] or [])
    assert any("căn 1" in question.lower() for question in reply["questions"] or [])


def test_handover_refuses_rooms_outside_the_current_results(service, renter, profile):
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile, 0)
    visible = {item["room_id"] for item in service.results(sid, renter)["results"]}
    hidden = next(room.id for room in service.catalog.rooms() if room.id not in visible)
    with pytest.raises(DomainError) as error:
        service.message(sid, renter, f"chat với chủ nhà căn {hidden}")
    assert error.value.code == "not_visible"
