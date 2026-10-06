import pytest

from backend.app.auth import SeedAuth
from backend.app.models import DomainError, DraftPatch, Room
from backend.app.service import HomeMatchService
from backend.app.semantic import OpenAIEmbeddings
from types import SimpleNamespace
from fastapi.testclient import TestClient
from backend.app.main import create_app


def test_empty_optional_seed_password_retains_local_default(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_PASSWORD_RENTER_A", "")
    auth = SeedAuth(service.repo, service.lock)
    assert auth.login("renter-a", "local-renter-a-password")["actor"]["id"] == "renter-a"


def test_public_existing_defaults_require_explicit_rotation_and_revoke_old_tokens(service, monkeypatch):
    from backend.app.auth import SEED_USERS

    auth = SeedAuth(service.repo, service.lock)
    old = auth.login("renter-a", "local-renter-a-password")["access_token"]
    passwords = {}
    for user, _role in SEED_USERS:
        value = "synthetic-test-strong-" + user
        passwords[user] = value
        monkeypatch.setenv("HOMEMATCH_PASSWORD_" + user.upper().replace("-", "_"), value)
    with pytest.raises(ValueError, match="Stored seed credentials differ"):
        SeedAuth(service.repo, service.lock, public=True)
    auth.rotate_passwords()
    SeedAuth(service.repo, service.lock, public=True)
    with pytest.raises(DomainError):
        auth.actor(old)
    with pytest.raises(DomainError):
        auth.login("renter-a", "local-renter-a-password")
    assert auth.login("renter-a", passwords["renter-a"])["actor"]["id"] == "renter-a"


def test_invalid_patch_list_returns_domain_error(service, renter):
    sid = service.create_session(renter)["session_id"]
    for value in (None, 3):
        with pytest.raises(DomainError) as error:
            service.patch_draft(sid, renter, DraftPatch(expected_draft_revision=0, set={"preferences": value}))
        assert error.value.code == "invalid_patch" and error.value.http_status == 422
    assert service.session(sid, renter)["draft_revision"] == 0


def test_import_batch_conflict_rolls_back_all_rows_and_version(service):
    before = service.catalog.version
    original = service.catalog.rooms()[0]
    new = Room.model_validate({**original.model_dump(), "id": "synthetic-new-import"})
    conflict = Room.model_validate({**original.model_dump(), "title": "Conflicting same revision"})
    with pytest.raises(DomainError):
        service.catalog.import_rooms([new, conflict])
    assert service.catalog.version == before
    assert "synthetic-new-import" not in {room.id for room in service.catalog.rooms()}


def test_embedding_configuration_cannot_silently_ignore_wrong_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_EMBEDDING_MODE", "invalid-mode")
    with pytest.raises(ValueError, match="must be disabled or openai"):
        HomeMatchService(tmp_path / "invalid.sqlite")
    monkeypatch.setenv("HOMEMATCH_EMBEDDING_MODE", "openai")
    with pytest.raises(ValueError, match="require PostgreSQL"):
        HomeMatchService(tmp_path / "wrong-storage.sqlite")


def test_failed_embedding_call_is_counted_but_missing_usage_is_not_zero():
    def fail(**kwargs):
        raise RuntimeError("synthetic SDK failure")
    provider = OpenAIEmbeddings(client=SimpleNamespace(embeddings=SimpleNamespace(create=fail)), dimensions=2)
    with pytest.raises(DomainError):
        provider.embed("phòng yên tĩnh")
    assert provider.calls == 1 and provider.usage_missing_calls == 1 and not provider.cache


def test_remote_peer_cannot_use_demo_auth_by_spoofing_localhost_header(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "demo")
    with TestClient(create_app(lambda: service), base_url="http://localhost", client=("203.0.113.8", 50000)) as client:
        response = client.get("/auth/me", headers={"Host": "localhost", "Authorization": "Bearer demo-renter-a"})
        assert response.status_code == 403 and response.json()["error"]["code"] == "demo_local_only"
        assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_password_rotation_during_login_cannot_issue_a_new_token_for_old_password(service, monkeypatch):
    import backend.app.auth as auth_module
    from backend.app.auth import SEED_USERS

    auth = SeedAuth(service.repo, service.lock)
    verify = auth_module.verify_password
    for user, _role in SEED_USERS:
        monkeypatch.setenv("HOMEMATCH_PASSWORD_" + user.upper().replace("-", "_"), "fixture-rotated-password-" + user)

    def rotate_after_verification(password, encoded):
        valid = verify(password, encoded)
        auth.rotate_passwords()
        return valid

    monkeypatch.setattr(auth_module, "verify_password", rotate_after_verification)
    with pytest.raises(DomainError) as error:
        auth.login("renter-a", "local-renter-a-password")
    assert error.value.code == "invalid_credentials"
    assert service.repo.db.execute("SELECT COUNT(*) AS count FROM hm_tokens").fetchone()["count"] == 0


def test_zero_embedding_is_unavailable_instead_of_a_cosine_score():
    provider = OpenAIEmbeddings(client=SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kwargs:
        SimpleNamespace(data=[SimpleNamespace(embedding=[0.0, 0.0])], usage=SimpleNamespace(total_tokens=3)))), dimensions=2)
    with pytest.raises(DomainError) as error:
        provider.embed("phòng thoáng")
    assert error.value.code == "semantic_unavailable" and not provider.cache
