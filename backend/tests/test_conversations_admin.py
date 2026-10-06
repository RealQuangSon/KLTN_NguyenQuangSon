import pytest
from fastapi.testclient import TestClient

from backend.app.conversations import mask_pii
from backend.app.main import create_app
from backend.app.models import Actor, DomainError, Review

ADMIN = Actor(id="admin-a", role="admin")


def published_session(service, renter, landlord, profile):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM Quận 7, gọi tôi 0901234567 hoặc a@b.com")
    run_id = service.confirm(sid, renter, profile.model_copy(update={"monthly_income_vnd": 20_000_000}),
                             service.session(sid, renter)["draft_revision"])["run_id"]
    service.review(run_id, landlord, Review(decision="approve", expected_profile_version=1, reason="ok",
                                            idempotency_key="k"))
    return sid, service.results(sid, renter)["results"][0]["room_id"]


def test_pii_masking():
    masked = mask_pii("Gọi 0901 234 567, mail x.y@z.vn, STK 0123456789012")
    assert "0901" not in masked and "@" not in masked and "0123456789012" not in masked


def test_handover_carries_context_without_income_and_pii(service, renter, landlord, profile):
    sid, room_id = published_session(service, renter, landlord, profile)
    conversation = service.start_conversation(renter, room_id, sid)
    context = conversation["context"]
    assert context["room"]["id"] == room_id and context["needs"]["area"] == "Quận 7"
    assert "monthly_income_vnd" not in str(context) and "housing_ratio" not in str(context)
    assert context["affordability_band"] in {"phu_hop", "can_nhac", "vuot", "chua_ro"}
    assert any(turn["speaker"] == "user" for turn in context["recent_ai_chat"])
    assert "0901234567" not in str(context) and "a@b.com" not in str(context)
    assert service.start_conversation(renter, room_id, sid)["id"] == conversation["id"]  # one per room


def test_live_chat_scoped_to_participants_with_unread_and_first_response(service, renter, landlord, profile):
    sid, room_id = published_session(service, renter, landlord, profile)
    conversation_id = service.start_conversation(renter, room_id, sid)["id"]
    service.send_conversation_message(renter, conversation_id, "Phòng còn trống không ạ?")
    inbox = service.conversations(landlord)
    assert [item["id"] for item in inbox] == [conversation_id] and inbox[0]["unread"] == 1
    thread = service.conversation_messages(landlord, conversation_id)
    assert [message["sender_role"] for message in thread["messages"]] == ["system", "renter"]
    assert service.conversations(landlord)[0]["unread"] == 0
    reply = service.send_conversation_message(landlord, conversation_id, "Còn bạn nhé, chiều nay xem được.")
    assert service.conversations(renter)[0]["unread"] == 1
    assert service.conversation_messages(renter, conversation_id, after=reply["created_at"])["messages"] == []
    for outsider in (Actor(id="owner-b", role="owner"), Actor(id="renter-b", role="renter")):
        with pytest.raises(DomainError):
            service.conversation_messages(outsider, conversation_id)
    report = service.admin_handovers(ADMIN)
    stats = {item["landlord_id"]: item for item in report["landlords"]}
    assert stats["owner-a"]["response_rate"] == 1.0 and stats["owner-a"]["median_response_minutes"] is not None


def test_admin_audits_masked_transcripts_and_reads_are_logged(service, renter, landlord, profile):
    sid, _ = published_session(service, renter, landlord, profile)
    sessions = service.admin_transcripts(ADMIN)
    assert sessions[0]["session_id"] == sid and sessions[0]["turns"] >= 2
    transcript = service.admin_transcript(ADMIN, sid)
    assert transcript["retention_days"] == 90
    assert "0901234567" not in str(transcript) and "[SĐT đã che]" in transcript["turns"][0]["text"]
    audit = service.repo.db.execute("SELECT action,resource_id FROM hm_audit_log WHERE action='transcript.viewed'"
                                    ).fetchall()
    assert [(row["action"], row["resource_id"]) for row in audit] == [("transcript.viewed", sid)]
    with pytest.raises(DomainError):
        service.admin_transcript(landlord, sid)


def test_conversation_and_admin_routes(service, renter, landlord, profile):
    sid, room_id = published_session(service, renter, landlord, profile)
    with TestClient(create_app(lambda: service)) as client:
        renter_headers = {"Authorization": "Bearer demo-renter-a"}
        started = client.post("/conversations", headers=renter_headers, json={"room_id": room_id, "session_id": sid})
        assert started.status_code == 201
        conversation_id = started.json()["id"]
        sent = client.post(f"/conversations/{conversation_id}/messages", headers={"Authorization": "Bearer demo-owner-a"},
                           json={"body": "Chào bạn"})
        assert sent.status_code == 201
        admin = {"Authorization": "Bearer demo-admin-a"}
        assert client.get("/admin/handovers", headers=admin).json()["landlords"][0]["answered"] == 1
        assert client.get("/admin/users", headers=admin).status_code == 200
        assert client.get("/admin/transcripts", headers=renter_headers).status_code == 403
