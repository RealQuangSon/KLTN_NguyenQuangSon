import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.catalog import Catalog
from backend.app.interpreter import OpenAIInterpreter
from backend.app.main import create_app
from backend.app.models import CatalogStatus, DomainError, DraftPatch, Review
from backend.app.semantic import OpenAIEmbeddings
from backend.app.service import HomeMatchService


def test_seed_auth_password_hash_expiry_logout_and_safe_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    service = HomeMatchService(tmp_path / "auth.sqlite")
    app = create_app(lambda: service)
    with TestClient(app) as client:
        assert client.post("/auth/login", json={"username": "renter-a", "password": "bad"}).status_code == 401
        login = client.post("/auth/login", json={"username": "renter-a", "password": "local-renter-a-password"}).json()
        token = login["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/auth/me", headers=headers).json() == {"id": "renter-a", "role": "renter"}
        user = service.repo.db.execute("SELECT password_hash FROM hm_users WHERE id='renter-a'").fetchone()
        assert user["password_hash"].startswith("scrypt$") and "local-renter" not in user["password_hash"]
        assert token not in str([dict(row) for row in service.repo.db.execute("SELECT * FROM hm_tokens")])
        assert client.get("/landlord/rooms", headers=headers).status_code == 403
        invalid = client.post("/sessions/not-owned/confirm", headers=headers, json={"secret": "raw-private-value"})
        assert invalid.status_code == 422 and "raw-private-value" not in invalid.text
        assert invalid.headers["X-Request-ID"] == invalid.json()["request_id"]
        client.post("/auth/logout", headers=headers)
        assert client.get("/auth/me", headers=headers).status_code == 401
        new = client.post("/auth/login", json={"username": "renter-a", "password": "local-renter-a-password"}).json()
        service.repo.db.execute("UPDATE hm_tokens SET expires_at=?", (time.time() - 1,))
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"}).status_code == 401


def test_public_guard_rejects_demo_defaults_and_invalid_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_PUBLIC", "true")
    with pytest.raises(ValueError, match="Public mode"):
        with TestClient(create_app(lambda: HomeMatchService(tmp_path / "public.sqlite"))):
            pass
    monkeypatch.setenv("HOMEMATCH_PUBLIC", "false")
    monkeypatch.setenv("HOMEMATCH_TOKEN_TTL_SECONDS", "0")
    with pytest.raises(ValueError, match="TTL"):
        with TestClient(create_app(lambda: HomeMatchService(tmp_path / "ttl.sqlite"))):
            pass


def test_draft_cas_correction_and_privileged_fields(service, renter):
    sid = service.create_session(renter)["session_id"]
    first = service.message(sid, renter, "Tìm phòng TP.HCM có máy lạnh, thoáng")
    assert 1 <= len(first["questions"]) <= 2 and "air_conditioning" in first["draft"]["preferences"]
    corrected = service.message(sid, renter, "Không cần máy lạnh nữa")
    assert "air_conditioning" not in corrected["draft"]["preferences"]
    revision = corrected["draft_revision"]
    changed = service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision,
        set={"soft_description": "phòng sáng thoáng", "people": 2}, remove_preferences=["window"]))
    assert changed["profile_version"] == 0 and changed["active_run_id"] is None
    assert changed["draft"]["people"] == 2 and changed["draft"]["preferences"] == []
    with pytest.raises(DomainError, match="đổi"):
        service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=revision, set={"people": 1}))
    with pytest.raises(DomainError) as error:
        service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=changed["draft_revision"], set={"role": "manager"}))
    assert error.value.code == "invalid_patch"


def test_shared_catalog_cas_and_stale_publication(service, renter, landlord, profile):
    sid = service.create_session(renter)["session_id"]
    run = service.confirm(sid, renter, profile, 0)
    service.review(run["run_id"], landlord, Review(
        decision="approve", expected_profile_version=1, reason="Đã kiểm tra", idempotency_key="catalog-review"))
    room = service.catalog.rooms()[0]
    service.change_room_status(room.id, landlord, CatalogStatus(expected_revision=room.revision, available=False))
    assert service.results(sid, renter)["status"] == "invalidated"
    with pytest.raises(DomainError):
        service.change_room_status(room.id, landlord, CatalogStatus(expected_revision=room.revision, published=False))
    with pytest.raises(DomainError):
        service.rooms(renter)


def test_generation_failure_manual_retry_requires_new_approval(service, renter, landlord, admin, profile):
    sid = service.create_session(renter)["session_id"]
    graph = service.recommendation_graph
    service.recommendation_graph = SimpleNamespace(invoke=lambda *args: (_ for _ in ()).throw(RuntimeError("private error")))
    failed = service.confirm(sid, renter, profile, 0)
    assert failed["status"] == "generation_failed" and failed["results"] == []
    service.recommendation_graph = graph
    new = service.retry(failed["run_id"], admin)
    assert new["run_id"] != failed["run_id"] and new["status"] == "pending_review" and new["decision"] is None
    assert service.results(sid, renter)["results"] == []
    assert service.repo.run(failed["run_id"])["status"] == "invalidated"


def test_p_same_complete_eligible_set_and_explicit_unavailable(profile):
    profile.soft_description = "phòng sáng thoáng"
    catalog = Catalog()
    baseline, _ = catalog.rank(profile, "B1")
    with pytest.raises(DomainError) as error:
        catalog.rank(profile, "P")
    assert error.value.code == "semantic_unavailable"
    # Unit fixture validates blending/interface only; these are not research vectors.
    catalog.semantic_scorer = SimpleNamespace(similarities=lambda query, ids: {key: .9 for key in ids})
    proposed, diagnostics = catalog.rank(profile, "P")
    assert {item.room_id for item in proposed} == {item.room_id for item in baseline}
    by_id = {item.room_id: item for item in baseline}
    for item in proposed:
        assert item.cost == by_id[item.room_id].cost
        assert item.score == round(.7 * by_id[item.room_id].score + .3 * .9, 6)
    assert diagnostics["algorithm"] == "P"


def test_context_budget_skips_provider_and_finance_never_enters_context(monkeypatch):
    captured = {}
    def parse(**kwargs):
        captured.update(kwargs)
        from backend.app.models import Extraction
        return SimpleNamespace(status="completed", output_parsed=Extraction(intent="find_room", city=None,
            area=None, people=None, preferences=[], needs_destination=False))
    adapter = OpenAIInterpreter(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    adapter.extract("Tìm phòng", {"budget_hint_vnd": 5_000_000, "preferences": ["quiet"], "role": "manager"})
    context = json.loads(captured["input"][1]["content"])
    assert context["draft"] == {"preferences": ["quiet"]}
    captured.clear()
    monkeypatch.setenv("HOMEMATCH_CONTEXT_TOKEN_CAP", "10")
    with pytest.raises(DomainError) as error:
        adapter.extract("Tìm phòng")
    assert error.value.code == "context_limit" and not captured


def test_embedding_adapter_cache_and_privacy_without_paid_call():
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[.1, .2])], usage=SimpleNamespace(total_tokens=3))
    provider = OpenAIEmbeddings(client=SimpleNamespace(embeddings=SimpleNamespace(create=create)), dimensions=2)
    assert provider.embed("phòng thoáng") == provider.embed("phòng thoáng")
    assert len(calls) == 1 and provider.tokens == 3
    with pytest.raises(DomainError, match="Không embedding"):
        provider.embed("tầm 3 triệu, gọi 0901234567")


def test_no_match_offers_soft_suggestions_and_never_relaxes_automatically(service, renter, profile):
    # Tight budget pushes every room into rejection/verification buckets, not into results.
    session_id = service.create_session(renter)["session_id"]
    tight = profile.model_copy(update={"max_monthly_cost_vnd": 500_000})
    service.confirm(session_id, renter, tight, 0)
    result = service.results(session_id, renter)
    assert result["status"] in ("no_match", "needs_verification") and result["results"] == []
    assert result["suggestions"] and any("trần" in text or "xác minh" in text
                                         for text in result["suggestions"])
    # Nothing is auto-relaxed: reading again returns the same empty, constrained result.
    repeat = service.results(session_id, renter)
    assert repeat["status"] == result["status"] and repeat["results"] == []

    # An area with no listings at all yields a true no_match, still with soft suggestions.
    elsewhere = service.create_session(renter)["session_id"]
    remote = profile.model_copy(update={"area": "Quận 9"})
    service.confirm(elsewhere, renter, remote, 0)
    empty = service.results(elsewhere, renter)
    assert empty["status"] == "no_match" and empty["results"] == []
    assert any("khu vực" in text for text in empty["suggestions"])

    other = service.create_session(renter)["session_id"]
    service.confirm(other, renter, profile, 0)
    normal = service.results(other, renter)
    assert normal["status"] == "pending_review" and "suggestions" not in normal
