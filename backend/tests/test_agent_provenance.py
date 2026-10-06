"""Provenance on assistant turns and result payloads, plus pending-recommendation
isolation in renter-visible output.

Provenance stamps are service-layer data (agent_trace); HTTP exposure needs an
optional schema field owned by the backend agent.
"""
import pytest

from backend.app.models import CostRequest, Review, Scenario
from backend.app.service import HomeMatchService


@pytest.fixture
def own_service(tmp_path):
    agent = HomeMatchService(tmp_path / "provenance.sqlite")
    yield agent
    agent.close()


def approval(version=1, **changes):
    return Review(decision="approve", expected_profile_version=version,
                  reason="Đã kiểm tra dữ liệu demo.", idempotency_key="review-1", **changes)


def test_chat_turns_carry_provenance_per_node(own_service, renter):
    sid = own_service.create_session(renter)["session_id"]
    own_service.message(sid, renter, "Tìm studio TP.HCM cho 2 người")
    trace = own_service.agent_trace(sid, renter)["chat"]
    assert trace["provenance"]["source"] == "interpreter"
    assert trace["provenance"]["node"] == "interview"
    assert trace["provenance"]["interpreter_mode"] == "demo_rules"
    quote = next(room.quote for room in own_service.catalog.rooms() if room.id == "demo-01")
    own_service.message(sid, renter, "Tính chi phí", CostRequest(quote=quote, scenario=Scenario()))
    trace = own_service.agent_trace(sid, renter)["chat"]
    assert trace["provenance"]["source"] == "deterministic-engine"
    assert trace["provenance"]["node"] == "finance"
    assert trace["provenance"]["source"] != "interpreter"


def test_results_payload_has_engine_provenance(own_service, renter, landlord, profile):
    sid = own_service.create_session(renter)["session_id"]
    run_id = own_service.confirm(sid, renter, profile, 0)["run_id"]
    trace = own_service.agent_trace(sid, renter)["results"]
    assert trace["provenance"]["source"] == "deterministic-engine"
    assert trace["provenance"]["node"] == "rank"
    assert trace["provenance"]["matching_method"] == "B1"
    assert trace["provenance"]["catalog_version"] == own_service.catalog.version
    assert trace["run_id"] == run_id


def test_pending_recommendations_never_reach_renter_chat_or_results(own_service, renter, landlord, profile):
    sid = own_service.create_session(renter)["session_id"]
    run_id = own_service.confirm(sid, renter, profile, 0)["run_id"]
    # Pending: no items, no diagnostics, no results anywhere renter-visible.
    pending = own_service.results(sid, renter)
    assert pending["status"] == "pending_review" and pending["results"] == []
    assert "items" not in pending and "diagnostics" not in pending
    reply = own_service.message(sid, renter, "Phòng nào phù hợp vậy?")
    assert "items" not in reply and "diagnostics" not in reply and "results" not in reply
    assert own_service.agent_trace(sid, renter)["results"]["visible_room_ids"] == []
    # Manager sees the draft; the renter still does not.
    assert own_service.draft(run_id, landlord)["items"]
    assert own_service.results(sid, renter)["results"] == []
    # After approval, results appear only in the results payload, never in chat.
    own_service.review(run_id, landlord, approval())
    published = own_service.results(sid, renter)
    assert published["status"] == "published" and published["results"]
    reply = own_service.message(sid, renter, "Cho hỏi thêm")
    assert "items" not in reply and "diagnostics" not in reply and "results" not in reply
    trace = own_service.agent_trace(sid, renter)["results"]
    assert trace["provenance"]["run_status"] == "published"
    assert set(trace["visible_room_ids"]) <= {item["room_id"] for item in published["results"]}
