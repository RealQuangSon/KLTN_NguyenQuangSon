import pytest
from fastapi.testclient import TestClient

from backend.app.agents import AGENT_TOOLS, ToolBox
from backend.app.main import create_app
from backend.app.memory import consented
from backend.app.models import Actor, DomainError
from backend.app.semantic import QueryEmbeddingCache


def test_toolbox_enforces_allowlist_and_step_limit():
    box = ToolBox(max_steps=2)
    assert box.call("finance", "calculate_cost", lambda: "ok") == "ok"
    with pytest.raises(DomainError) as denied:
        box.call("needs", "match_catalog", lambda: None)
    assert denied.value.code == "tool_not_allowed" and box.denied == [{"agent": "needs", "tool": "match_catalog"}]
    box.call("ranking", "match_catalog", lambda: None)
    with pytest.raises(DomainError) as limited:
        box.call("ranking", "explain_candidate", lambda: None)
    assert limited.value.code == "agent_step_limit"
    # Money comes only from finance tools; no other agent can reach them.
    finance_tools = AGENT_TOOLS["finance"]
    assert all(not (tools & finance_tools) for agent, tools in AGENT_TOOLS.items() if agent != "finance")


def test_each_turn_records_the_agent_and_its_tools(service, renter):
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm căn hộ Cầu Giấy Hà Nội cho 2 người")
    provenance = service.agent_trace(sid, renter)["chat"]["provenance"]
    assert provenance["agent"] == "needs" and provenance["tools"] == ["extract_needs", "update_draft"]
    service.message(sid, renter, "Tính chi phí giúp tôi")
    provenance = service.agent_trace(sid, renter)["chat"]["provenance"]
    assert provenance["agent"] == "finance" and provenance["steps"] == 0


def test_ranking_agent_is_recorded_in_run_diagnostics(service, renter, landlord, profile):
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    assert service.draft(run_id, landlord)["diagnostics"]["agent"] == {
        "agent": "ranking", "tools": ["match_catalog"], "steps": 1}


def consent(service, user_id: str, value: bool):
    from backend.app.auth import update_account_profile
    with service.repo.db:  # the plain service fixture does not seed accounts
        service.repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,?,?) "
                                "ON CONFLICT(id) DO NOTHING", (user_id, "renter", "unused"))
    update_account_profile(service.repo, user_id, {"consents": {"remember_sessions": value}})


def test_memory_requires_consent_and_only_prefills_inferred_fields(service, renter, profile):
    first = service.create_session(renter)["session_id"]
    service.confirm(first, renter, profile, 0)
    assert service.create_session(renter)["draft"]["preferences"] == []  # no consent, nothing kept
    consent(service, renter.id, True)
    assert consented(service.repo, renter.id)
    second = service.create_session(renter)["session_id"]
    service.confirm(second, renter, profile.model_copy(update={"monthly_income_vnd": 30_000_000}), 0)
    third = service.create_session(renter)
    draft = third["draft"]
    assert draft["city"] == "TP.HCM" and draft["area"] == "Quận 7"
    assert set(draft["preferences"]) == {"window", "quiet", "private_bathroom"}
    assert draft["field_status"]["city"] == "inferred"
    assert draft["evidence_ref"]["city"] == f"memory:{second}"
    assert third["confirmed_profile"] is None and third["draft_revision"] == 0
    stored = service.repo.db.execute("SELECT payload_json FROM hm_preference_memory WHERE user_id=?",
                                     (renter.id,)).fetchone()["payload_json"]
    assert "income" not in stored and "max_" not in stored and "loan" not in stored


def test_memory_api_forget_and_consent_withdrawal(service, profile):
    renter = Actor(id="renter-a", role="renter")
    consent(service, renter.id, True)
    sid = service.create_session(renter)["session_id"]
    service.confirm(sid, renter, profile, 0)
    with TestClient(create_app(lambda: service)) as client:
        headers = {"Authorization": "Bearer demo-renter-a"}
        body = client.get("/me/memory", headers=headers).json()
        assert body["consented"] and body["memory"]["fields"]["area"] == "Quận 7"
        assert client.delete("/me/memory/area", headers=headers).json() == {"status": "forgotten", "field": "area"}
        assert client.get("/me/memory", headers=headers).json()["memory"]["fields"]["area"] is None
        assert client.delete("/me/memory/monthly_income_vnd", headers=headers).status_code == 422
        client.patch("/me/profile", headers=headers, json={"consents": {"remember_sessions": False}})
        assert service.repo.db.execute("SELECT COUNT(*) AS n FROM hm_preference_memory").fetchone()["n"] == 0
        consent(service, renter.id, True)
        assert client.get("/me/memory", headers=headers).json()["memory"] is None


class CountingProvider:
    model, dimensions = "fixture-embedding", 3

    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        return [1.0, 0.0, float(len(text))]


def test_query_embedding_cache_survives_a_new_cache_instance(service):
    provider, lookups = CountingProvider(), []
    cache = QueryEmbeddingCache(service.repo, provider, on_lookup=lambda hit: lookups.append(hit))
    first = cache.embed("yên tĩnh, nhiều ánh sáng")
    assert cache.embed("yên tĩnh, nhiều ánh sáng") == first
    # A restart builds a new cache object; the vector is read back from the ledger table.
    assert QueryEmbeddingCache(service.repo, provider).embed("yên tĩnh, nhiều ánh sáng") == first
    assert provider.calls == 1 and lookups == [False, True]
    service.metrics.semantic_query(hit=True)
    assert service.metrics.snapshot()["semantic_usage"]["query_cache_hits"] == 1
