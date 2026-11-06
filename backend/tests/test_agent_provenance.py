"""Provenance on assistant turns and result payloads, plus pending-recommendation
isolation in renter-visible output.

Provenance stamps are service-layer data (agent_trace); HTTP exposure needs an
optional schema field owned by the backend agent.
"""
import pytest

from backend.app.models import CostRequest, Scenario
from backend.app.service import HomeMatchService


@pytest.fixture
def own_service(tmp_path):
    agent = HomeMatchService(tmp_path / "provenance.sqlite")
    yield agent
    agent.close()


def test_chat_turns_carry_provenance_per_node(own_service, renter):
    sid = own_service.create_session(renter)["session_id"]
    reply = own_service.message(sid, renter, "Tìm studio TP.HCM cho 2 người")
    assert reply["provenance"]["source"] == "interpreter"
    assert reply["provenance"]["node"] == "interview"
    assert reply["provenance"]["interpreter_mode"] == "demo_rules"
    quote = next(room.quote for room in own_service.catalog.rooms() if room.id == "demo-01")
    reply = own_service.message(sid, renter, "Tính chi phí", CostRequest(quote=quote, scenario=Scenario()))
    assert reply["provenance"]["source"] == "deterministic-engine"
    assert reply["provenance"]["node"] == "finance"


def test_results_payload_has_engine_provenance(own_service, renter, landlord, profile):
    sid = own_service.create_session(renter)["session_id"]
    run_id = own_service.confirm(sid, renter, profile, 0)["run_id"]
    trace = own_service.agent_trace(sid, renter)["results"]
    assert trace["provenance"]["source"] == "deterministic-engine"
    assert trace["provenance"]["node"] == "rank"
    assert trace["provenance"]["matching_method"] == "B1"
    assert trace["provenance"]["catalog_version"] == own_service.catalog.version
    assert trace["run_id"] == run_id


def test_results_reach_renter_once_published_never_in_chat(own_service, renter, profile):
    sid = own_service.create_session(renter)["session_id"]
    # Chưa có run: không kết quả nào hiển thị và chat không lộ gì.
    early = own_service.results(sid, renter)
    assert early["status"] == "awaiting_confirmation" and early["results"] == []
    reply = own_service.message(sid, renter, "Phòng nào phù hợp vậy?")
    assert "items" not in reply and "diagnostics" not in reply and "results" not in reply
    assert (own_service.agent_trace(sid, renter)["results"] or {}).get("visible_room_ids", []) == []
    # Kết quả chỉ xuất hiện trong payload results, không bao giờ trong chat.
    revision = own_service.session(sid, renter)["draft_revision"]
    run_id = own_service.confirm(sid, renter, profile, revision)["run_id"]
    published = own_service.results(sid, renter)
    assert published["status"] == "published" and published["results"]
    assert "items" not in published and "diagnostics" not in published
    reply = own_service.message(sid, renter, "Cho hỏi thêm")
    assert "items" not in reply and "diagnostics" not in reply and "results" not in reply
    trace = own_service.agent_trace(sid, renter)["results"]
    assert trace["provenance"]["run_status"] == "published"
    assert trace["run_id"] == run_id
    assert set(trace["visible_room_ids"]) == {item["room_id"] for item in published["results"]}
