import logging

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.migrations import SCHEMA_VERSION
from backend.app.schemas import ResultsResult
from infra.smoke_api import run


def test_openapi_defines_success_and_safe_error_contracts(service):
    spec = create_app(lambda: service).openapi()
    assert spec["info"]["version"] == "0.4.0"
    for operations in spec["paths"].values():
        for operation in operations.values():
            responses = operation["responses"]
            success = responses.get("200", responses.get("201"))
            assert success["content"]["application/json"]["schema"]
            assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith("ErrorResult")
    with pytest.raises(ValueError, match="Unpublished"):
        ResultsResult.model_validate({"session_id": "fixture", "status": "pending_review", "results": [
            {"room_id": "fixture", "room_revision": 1, "title": "Fixture", "city": "TP.HCM", "area": "Quận 7",
             "area_m2": 20, "cost": {"monthly_known_vnd": 0, "monthly_total_vnd": 0, "initial_known_vnd": 0,
                                   "initial_total_vnd": 0, "missing_monthly": [], "missing_initial": [], "lines": [], "assumptions": {}},
             "score": 0, "components": {}, "reasons": [], "tradeoffs": [], "source": "synthetic", "synthetic": True}
        ]})


def test_full_api_flow_against_response_schemas(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service), base_url="http://127.0.0.1:8000") as client:
        assert run("http://127.0.0.1:8000", client)["status"] == "passed"
        assert client.get("/ready").json()["schema_version"] == SCHEMA_VERSION


def test_all_http_errors_have_safe_envelope_and_request_id(service, monkeypatch):
    with TestClient(create_app(lambda: service), raise_server_exceptions=False) as client:
        for response in (client.get("/auth/me"), client.get("/private-value-does-not-exist"), client.put("/health"),
                         client.post("/auth/login", json={"username": "renter-a", "password": "private-bad-password"})):
            assert response.status_code in {401, 404, 405}
            assert response.json()["request_id"] == response.headers["X-Request-ID"]
            assert "private" not in response.text and "detail" not in response.json()
        assert client.get("/auth/me").headers["WWW-Authenticate"] == "Bearer"

        def broken(*args):
            raise RuntimeError("private-internal-token")

        monkeypatch.setattr(service, "create_session", broken)
        failed = client.post("/sessions", headers={"Authorization": "Bearer demo-renter-a"})
        assert failed.status_code == 500 and failed.json()["error"]["code"] == "internal_error"
        assert failed.json()["request_id"] == failed.headers["X-Request-ID"] and "private" not in failed.text


def test_readiness_detects_checkpoint_and_schema_failure(service):
    with TestClient(create_app(lambda: service)) as client:
        assert client.get("/ready").status_code == 200
        service.repo.db.execute("DELETE FROM hm_schema_migrations WHERE version=?", (SCHEMA_VERSION,))
        response = client.get("/ready")
        assert response.status_code == 503 and response.json()["error"]["code"] == "not_ready"
        assert client.get("/health").status_code == 200
        service.checkpoint_connection.close()
        assert client.get("/ready").status_code == 503
        service.repo.close()
        assert client.get("/health").status_code == 503


def test_metrics_and_logs_use_templates_and_hide_sensitive_inputs(service, caplog):
    caplog.set_level(logging.INFO, logger="homematch.api")
    with TestClient(create_app(lambda: service)) as client:
        renter = {"Authorization": "Bearer demo-renter-a"}
        admin = {"Authorization": "Bearer demo-admin-a"}
        sid = client.post("/sessions", headers=renter).json()["session_id"]
        client.post(f"/sessions/{sid}/messages", headers=renter, json={"text": "Tìm phòng TP.HCM; email private-person@example.com; 5 triệu"})
        client.get("/private-token-in-path?password=secret")
        assert client.get("/admin/metrics", headers=renter).status_code == 403
        assert client.get("/admin/metrics", headers={"Authorization": "Bearer demo-owner-a"}).status_code == 403
        metrics = client.get("/admin/metrics", headers=admin)
        assert metrics.status_code == 200
        assert metrics.json()["scope"] == "current_process"
        assert metrics.json()["provider_usage"]["logical_calls"] == 0
        routes = {item["route"] for item in metrics.json()["requests"]}
        assert "/sessions/{session_id}/messages" in routes and "<unmatched>" in routes
        for private in (sid, "private-person", "5 triệu", "demo-renter-a", "private-token-in-path", "secret"):
            assert private not in caplog.text and private not in metrics.text


def test_failed_provider_invocation_counts_usage_without_claiming_zero_tokens(service, renter):
    from types import SimpleNamespace
    from backend.app.interpreter import OpenAIInterpreter

    def fail(**kwargs):
        raise RuntimeError("private-provider-error")

    service.interpreter = OpenAIInterpreter(client=SimpleNamespace(responses=SimpleNamespace(parse=fail)))
    sid = service.create_session(renter)["session_id"]
    # Provider failure no longer raises: service returns a deterministic
    # guided-form fallback while the failed logical call is still counted
    # without pretending tokens were reported.
    reply = service.message(sid, renter, "Tìm phòng TP.HCM")
    assert reply["status"] == "needs_clarification" and reply["intent"] == "unknown"
    assert any("ai_unavailable" in question for question in reply["questions"])
    usage = service.metrics.snapshot()["provider_usage"]
    assert usage == {"logical_calls": 1, "reported_tokens": 0, "calls_without_token_usage": 1}
