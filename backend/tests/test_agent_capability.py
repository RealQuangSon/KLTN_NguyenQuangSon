"""Capability scope per actor/resource for agent-reachable actions, deterministic
human handoff from chat, and chat-side viewing request preparation.

Every negative here is enforced by service code (the capability matrix), never
by model output; offline demo mode only.
"""
import pytest

from backend.app.agent_capability import CAPABILITIES, Resource, assert_unprivileged, require
from backend.app.models import Actor, DomainError, Review
from backend.app.service import HomeMatchService


class NoModel:
    mode = "must_not_be_called"
    last_usage = {"logical_calls": 0, "tokens": None}

    def extract(self, text, draft=None):
        raise AssertionError("Capability-blocked flow must not reach the interpreter")


@pytest.fixture
def own_service(tmp_path):
    agent = HomeMatchService(tmp_path / "capability.sqlite")
    yield agent
    agent.close()


def test_capability_matrix_covers_every_public_entry():
    expected = {"session:create", "session:read", "chat:message", "draft:patch", "profile:confirm",
                "results:read", "compare:run", "viewing:prepare", "viewing:request", "viewing:read",
                "viewing:respond", "support:handoff", "support:list", "run:draft_list", "run:read",
                "run:review", "run:retry", "catalog:read", "catalog:write"}
    assert expected == set(CAPABILITIES)


def test_wrong_role_is_blocked_before_execution(own_service, renter, landlord):
    sid = own_service.create_session(renter)["session_id"]
    for call in (lambda: own_service.message(sid, landlord, "Tìm phòng"),
                 lambda: own_service.create_session(landlord),
                 lambda: own_service.patch_draft(sid, landlord, None)):
        with pytest.raises(DomainError) as error:
            call()
        assert error.value.code == "forbidden" and error.value.http_status == 403
    own_rooms = own_service.rooms(landlord)  # a landlord reads only own listings
    assert own_rooms["shared_catalog"] is False
    assert {room["id"] for room in own_rooms["rooms"]}  # demo rooms default to owner-a
    for call in (lambda: own_service.rooms(renter), lambda: own_service.drafts(renter),
                 lambda: own_service.support_tickets(renter)):
        with pytest.raises(DomainError):
            call()


def test_wrong_owner_and_unassigned_manager_are_blocked(own_service, renter, landlord, profile):
    sid = own_service.create_session(renter)["session_id"]
    run_id = own_service.confirm(sid, renter, profile, 0)["run_id"]
    intruder = Actor(id="renter-b", role="renter")
    for call in (lambda: own_service.session(sid, intruder),
                 lambda: own_service.message(sid, intruder, "Tìm phòng"),
                 lambda: own_service.results(sid, intruder),
                 lambda: own_service.agent_trace(sid, intruder)):
        with pytest.raises(DomainError) as error:
            call()
        assert error.value.code == "forbidden"
    # Even a forged manager role fails resource ownership: review targets a run
    # whose session is assigned to manager-a, not to whoever claims the role.
    forged = Actor(id="renter-a", role="manager")
    with pytest.raises(DomainError) as error:
        own_service.review(run_id, forged, Review(
            decision="approve", expected_profile_version=1, reason="Không có quyền.",
            idempotency_key="forged"))
    assert error.value.code == "forbidden"
    assert own_service.repo.run(run_id)["status"] == "pending_review"


def test_unknown_action_and_privileged_payload_are_rejected(renter):
    with pytest.raises(DomainError) as error:
        require("model:grant_role", renter)
    assert error.value.code == "unknown_action"
    with pytest.raises(DomainError) as error:
        assert_unprivileged({"event_id": "e1", "role": "manager"})
    assert error.value.code == "untrusted_resume"
    assert assert_unprivileged({"event_id": "e1"}) is None
    assert Resource.for_session({"owner_id": "r", "manager_id": "m"}).kind == "session"


def test_handoff_from_chat_is_deterministic_idempotent_and_honest(own_service, renter, landlord):
    own_service.interpreter = NoModel()
    sid = own_service.create_session(renter)["session_id"]
    first = own_service.message(sid, renter, "Tôi muốn gặp người thật")
    assert first["status"] == "support_requested" and first["ticket_id"]
    second = own_service.message(sid, renter, "gặp người thật")
    assert second["ticket_id"] == first["ticket_id"]  # one open ticket per session
    # Honest state: requested, not connected; no one was contacted.
    assert "đang chờ quản trị viên tiếp nhận" in first["message"]
    assert "đã kết nối" not in first["message"].lower()
    tickets = own_service.support_tickets(Actor(id="admin-a", role="admin"))
    assert [ticket["id"] for ticket in tickets] == [first["ticket_id"]]
    assert tickets[0]["session_id"] == sid and tickets[0]["status"] == "requested"
    trace = own_service.agent_trace(sid, renter)["chat"]
    assert trace["provenance"] == {"source": "deterministic-engine", "node": "support", "agent": "support",
                                   "tools": ["request_support"], "steps": 1}
    assert trace["guard"]["budget"]["used"] == 0  # clear-intent routing skips the LLM


def test_viewing_preparation_from_chat_requires_approved_current_room(own_service, renter, landlord, profile):
    sid = own_service.create_session(renter)["session_id"]
    run_id = own_service.confirm(sid, renter, profile, 0)["run_id"]
    # Pending run: nothing is approved, so preparation must refuse before creating.
    with pytest.raises(DomainError) as error:
        own_service.message(sid, renter, "Cho tôi đặt lịch xem demo-01")
    assert error.value.code == "not_visible"
    assert own_service.viewings(renter) == []
    own_service.review(run_id, landlord, Review(
        decision="approve", expected_profile_version=1, reason="Đã kiểm tra.",
        idempotency_key="viewing-prep"))
    reply = own_service.message(sid, renter, "Cho tôi đặt lịch xem demo-01")
    assert reply["status"] == "needs_clarification"
    assert "demo-01" in reply["message"] and "chưa tạo lịch xem" in reply["message"]
    assert "không tự giữ phòng" in reply["questions"][0]
    # Preparation creates nothing; the form action with time + key is still required.
    assert own_service.viewings(renter) == []
    trace = own_service.agent_trace(sid, renter)["chat"]
    assert trace["provenance"]["node"] == "viewing_prepare"
    assert trace["provenance"]["outcome"] == "prepared"
    assert trace["provenance"]["run_id"] == run_id
    assert trace["guard"]["budget"]["used"] == 0  # deterministic path, no LLM call


def test_viewing_preparation_without_room_reference_asks(own_service, renter, profile):
    sid = own_service.create_session(renter)["session_id"]
    reply = own_service.message(sid, renter, "Tôi muốn hẹn xem phòng")
    assert reply["status"] == "needs_clarification"
    assert "mã phòng" in reply["questions"][0]
    assert own_service.agent_trace(sid, renter)["chat"]["provenance"]["outcome"] == "missing_room_reference"
