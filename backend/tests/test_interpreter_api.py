from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.interpreter import OpenAIInterpreter
from backend.app.main import create_app
from backend.app.models import CostRequest, DomainError, Extraction, Scenario
from backend.app.service import HomeMatchService


class NoModel:
    mode = "must_not_be_called"

    def extract(self, text):
        raise AssertionError("Explicit finance/support route must skip LLM")


def test_missing_city_and_budget_ambiguity_are_not_defaulted(service, renter):
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng gần trường, tầm 3 triệu, thoáng")
    assert reply["draft"]["city"] is None
    assert reply["draft"]["monthly_budget_vnd"] is None
    assert reply["draft"]["budget_hint_vnd"] == 3_000_000
    assert reply["draft"]["needs_destination"] is True
    assert 1 <= len(reply["questions"]) <= 2


def test_finance_and_human_support_skip_llm(service, renter):
    service.interpreter = NoModel()
    sid = service.create_session(renter)["session_id"]
    quote = next(room.quote for room in service.catalog.rooms() if room.id == "demo-01")
    result = service.message(sid, renter, "Tính chi phí", CostRequest(quote=quote, scenario=Scenario()))
    assert result["cost"]["monthly_total_vnd"] == 3_250_000
    reply = service.message(sid, renter, "Tôi muốn gặp người thật")
    assert reply["status"] == "support_requested"
    assert reply["ticket_id"] == service.message(sid, renter, "gặp người thật")["ticket_id"]


def test_openai_adapter_masks_known_money_and_contacts_without_live_call():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status="completed", output_parsed=Extraction(intent="find_room", city=None,
            area=None, people=None, preferences=[], needs_destination=False))

    adapter = OpenAIInterpreter(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    adapter.extract("Tìm phòng 3,5 triệu, số 0901234567, email son@example.com")
    text = captured["input"][1]["content"]
    assert "3,5" not in text and "0901234567" not in text and "son@example.com" not in text
    assert captured["store"] is False


def test_openai_error_is_safe_and_explicit():
    def parse(**kwargs):
        raise RuntimeError("private provider payload")

    adapter = OpenAIInterpreter(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    with pytest.raises(DomainError) as error:
        adapter.extract("Tìm phòng")
    assert error.value.code == "ai_unavailable"
    assert "private" not in str(error.value)


def test_api_authorization_and_hitl_end_to_end(tmp_path, profile):
    app = create_app(lambda: HomeMatchService(tmp_path / "api.sqlite"))
    renter_headers = {"Authorization": "Bearer demo-renter-a"}
    manager_headers = {"Authorization": "Bearer demo-owner-a"}
    with TestClient(app) as client:
        assert client.post("/sessions").status_code == 401
        sid = client.post("/sessions", headers=renter_headers).json()["session_id"]
        body = {"expected_draft_revision": 0, "profile": profile.model_dump(mode="json")}
        pending = client.post(f"/sessions/{sid}/confirm", headers=renter_headers, json=body)
        assert pending.status_code == 200
        run_id = pending.json()["run_id"]
        assert pending.json()["results"] == []
        assert client.get("/landlord/recommendations", headers=renter_headers).status_code == 403
        assert client.get(f"/sessions/{sid}/results", headers={"Authorization":"Bearer demo-renter-b"}).status_code == 403
        reviewed = client.post(f"/landlord/recommendations/{run_id}/review", headers=manager_headers,
            json={"decision":"approve", "expected_profile_version":1,"reason":"Đã kiểm tra", "idempotency_key":"api-1"})
        assert reviewed.status_code == 200
        assert client.get(f"/sessions/{sid}/results", headers=renter_headers).json()["results"]
