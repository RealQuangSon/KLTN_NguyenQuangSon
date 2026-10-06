"""W-03 checks: registration, email verification, password reset, profile,
consents and session revoke. Verification delivery is the explicit dev stub."""
import hashlib
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import auth as auth_module
from backend.app.auth import DEV_STUB_LABEL, token_public_id
from backend.app.main import create_app, require_delivery_available
from backend.app.models import DomainError


def session_id_for(raw_token: str) -> str:
    """Mirror the server derivation: the public id is derived from the stored hash."""
    return token_public_id(hashlib.sha256(raw_token.encode()).hexdigest())


def _login(client, username, password=None):
    response = client.post("/auth/login", json={"username": username,
                                                "password": password or f"local-{username}-password"})
    return response


def _headers(client, username, password=None):
    response = _login(client, username, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _stub_codes(caplog):
    """Extract verification codes emitted by the log-only dev stub."""
    return re.findall(r"verification_code=(\S+)", caplog.text)


def test_require_delivery_available_blocks_public_mode():
    public_app = SimpleNamespace(state=SimpleNamespace(public=True))
    with pytest.raises(DomainError) as error:
        require_delivery_available(SimpleNamespace(app=public_app))
    assert error.value.code == "delivery_unavailable" and error.value.http_status == 503
    local_app = SimpleNamespace(state=SimpleNamespace(public=False))
    require_delivery_available(SimpleNamespace(app=local_app))  # does not raise


def test_registration_requires_verification_before_login(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        registered = client.post("/auth/register", json={
            "username": "new-renter", "password": "very-safe-password-1",
            "email": "new-renter@example.com", "display_name": "Người thuê mới"})
        assert registered.status_code == 201
        body = registered.json()
        assert body["status"] == "pending_verification"
        assert body["user"] == {"id": "new-renter", "role": "renter"}
        assert body["delivery"] == DEV_STUB_LABEL
        # The registration decision is server-side: role cannot be requested.
        assert client.post("/auth/register", json={
            "username": "staff-try", "password": "very-safe-password-1",
            "email": "staff@example.com", "role": "admin"}).status_code == 422
        assert client.post("/auth/register", json={
            "username": "new-renter", "password": "very-safe-password-1",
            "email": "other@example.com"}).status_code == 409
        assert client.post("/auth/register", json={
            "username": "other-renter", "password": "very-safe-password-1",
            "email": "new-renter@example.com"}).status_code == 409
        assert client.post("/auth/register", json={
            "username": "weak-password", "password": "short", "email": "weak@example.com"}).status_code == 422
        # Wrong password on an existing unverified account stays a generic 401.
        assert _login(client, "new-renter", "wrong-password-long").status_code == 401
        assert _login(client, "new-renter", "very-safe-password-1").status_code == 403
        unverified = _login(client, "new-renter", "very-safe-password-1")
        assert unverified.json()["error"]["code"] == "account_unverified"
        # Verification via the dev-stub code logged by the backend.
        codes = _stub_codes(caplog)
        assert codes, "dev stub must log the verification code"
        assert client.post("/auth/verify", json={"username": "new-renter",
                                                 "token": "not-a-real-token"}).status_code == 409
        verified = client.post("/auth/verify", json={"username": "new-renter", "token": codes[-1]})
        assert verified.status_code == 200 and verified.json()["status"] == "verified"
        # Tokens are single-use.
        assert client.post("/auth/verify", json={"username": "new-renter",
                                                 "token": codes[-1]}).status_code == 409
        assert _login(client, "new-renter", "very-safe-password-1").status_code == 200


def test_password_reset_flow_is_uniform_and_revokes_sessions(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        registered = client.post("/auth/register", json={
            "username": "reset-renter", "password": "very-safe-password-1",
            "email": "reset-renter@example.com"}).json()
        assert registered["delivery"] == DEV_STUB_LABEL
        code = _stub_codes(caplog)[-1]
        client.post("/auth/verify", json={"username": "reset-renter", "token": code})
        session_headers = _headers(client, "reset-renter", "very-safe-password-1")
        # Request looks identical for a known and an unknown account.
        known = client.post("/auth/password-reset/request", json={"username": "reset-renter"})
        unknown = client.post("/auth/password-reset/request", json={"username": "who-is-this"})
        seed_account = client.post("/auth/password-reset/request", json={"username": "manager-a"})
        assert known.json() == unknown.json() == seed_account.json() == {"status": "reset_requested"}
        reset_code = _stub_codes(caplog)[-1]
        assert client.post("/auth/password-reset/confirm", json={
            "username": "reset-renter", "token": reset_code,
            "new_password": "short"}).status_code == 422
        confirmed = client.post("/auth/password-reset/confirm", json={
            "username": "reset-renter", "token": reset_code, "new_password": "brand-new-password-9"})
        assert confirmed.status_code == 200 and confirmed.json()["status"] == "password_reset"
        # The reset token cannot be replayed and the old session is dead.
        assert client.post("/auth/password-reset/confirm", json={
            "username": "reset-renter", "token": reset_code,
            "new_password": "another-password-8"}).status_code == 409
        assert client.get("/auth/me", headers=session_headers).status_code == 401
        assert _login(client, "reset-renter", "very-safe-password-1").status_code == 401
        assert _login(client, "reset-renter", "brand-new-password-9").status_code == 200
        # Seed accounts cannot reset through this flow: no token is ever issued.
        caplog.clear()
        assert client.post("/auth/password-reset/confirm", json={
            "username": "manager-a", "token": "no-token-was-issued",
            "new_password": "not-issued-password"}).status_code == 409
        assert _stub_codes(caplog) == []
        assert _login(client, "manager-a").status_code == 200



def test_profile_consent_update_rules(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        headers = _headers(client, "manager-a")
        profile = client.get("/me/profile", headers=headers)
        assert profile.status_code == 200
        body = profile.json()
        assert body["id"] == "manager-a" and body["role"] == "manager" and body["status"] == "active"
        assert body["consents"] == {"save_history": False, "remember_sessions": False}
        assert body["organizations"] == [{"organization_id": "org-demo", "name": "Đơn vị demo HomeMatch",
                                          "role": "manager", "status": "active"}]
        # Consents update; unknown consent keys are rejected.
        patched = client.patch("/me/profile", headers=headers,
                               json={"display_name": "Quản lý A", "consents": {"save_history": True}})
        assert patched.status_code == 200
        assert patched.json()["display_name"] == "Quản lý A"
        assert patched.json()["consents"]["save_history"] is True
        assert patched.json()["email"] is None and patched.json()["email_verified"] is None
        # A profile patch without an email never locks a provisioned account.
        assert _login(client, "manager-a").status_code == 200
        assert client.patch("/me/profile", headers=headers,
                            json={"consents": {"weaponized_retention": True}}).status_code == 422
        # Role and organization are not patchable, structurally.
        assert client.patch("/me/profile", headers=headers,
                            json={"role": "admin"}).status_code == 422
        assert client.patch("/me/profile", headers=headers,
                            json={"organization_id": "org-demo"}).status_code == 422
        # Setting an email starts re-verification and locks login until verified.
        locked = client.patch("/me/profile", headers=headers,
                              json={"email": "manager-a@example.com"})
        assert locked.status_code == 200 and locked.json()["status"] == "unverified"
        assert locked.json()["email_verified"] is False
        assert _login(client, "manager-a").status_code == 403
        code = _stub_codes(caplog)[-1]
        assert client.post("/auth/verify", json={"username": "manager-a", "token": code}).status_code == 200
        assert _login(client, "manager-a").status_code == 200


def test_session_listing_and_revoke_by_public_token_id(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        first = _login(client, "renter-b")
        second = _login(client, "renter-b")
        headers = {"Authorization": "Bearer " + first.json()["access_token"]}
        sessions = client.get("/me/sessions", headers=headers)
        assert sessions.status_code == 200 and len(sessions.json()) >= 2
        token_ids = {item["token_id"] for item in sessions.json()}
        assert len(token_ids) == len(sessions.json())
        assert all(item["revoked"] is False for item in sessions.json())
        # A raw token or its hash never appears in the listing; the public id
        # is derived server-side from the stored hash.
        raw = first.json()["access_token"]
        assert raw not in sessions.text and session_id_for(raw) in token_ids
        assert client.delete(f"/me/sessions/{'no-such-session'}", headers=headers).status_code == 404
        target = next(item["token_id"] for item in sessions.json()
                      if item["token_id"] == session_id_for(second.json()["access_token"]))
        revoked = client.delete(f"/me/sessions/{target}", headers=headers)
        assert revoked.status_code == 200 and revoked.json() == {"status": "revoked"}
        assert client.get("/auth/me", headers={"Authorization":
                                               f"Bearer {second.json()['access_token']}"}).status_code == 401
        # The acting session stays valid; replayed revoke conflicts.
        assert client.get("/auth/me", headers=headers).status_code == 200
        assert client.delete(f"/me/sessions/{target}", headers=headers).status_code == 409
        # Sessions are strictly per user: renter-a cannot see or revoke renter-b's.
        other = {"Authorization": "Bearer " + _login(client, "renter-a").json()["access_token"]}
        listing = client.get("/me/sessions", headers=other).json()
        assert all(item["token_id"] != target for item in listing)
        assert client.delete(f"/me/sessions/{target}", headers=other).status_code == 404


def test_dev_stub_never_claims_real_delivery():
    stub = auth_module.DevDeliveryStub()
    assert stub.label == DEV_STUB_LABEL == "dev_stub_log_only"
    stub.deliver("email_verification", "user-a", "secret-code")  # log-only; must not raise or send
    assert stub.__dict__ == {}


def test_leftover_tokens_cannot_reactivate_a_disabled_account(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        client.post("/auth/register", json={
            "username": "disabled-renter", "password": "very-safe-password-1",
            "email": "disabled-renter@example.com"})
        verify_code = _stub_codes(caplog)[-1]
        service.repo.db.execute("UPDATE hm_account_profiles SET status='disabled' WHERE user_id=?",
                                ("disabled-renter",))
        assert client.post("/auth/verify", json={"username": "disabled-renter",
                                                 "token": verify_code}).status_code == 409
        # Reset tokens are not issued for disabled accounts; one issued earlier must not work either.
        reset_code = auth_module._issue_verification_token(service.repo, "disabled-renter",
                                                           "password_reset", 600)
        assert client.post("/auth/password-reset/confirm", json={
            "username": "disabled-renter", "token": reset_code,
            "new_password": "brand-new-password-9"}).status_code == 409
        status = service.repo.db.execute("SELECT status FROM hm_account_profiles WHERE user_id=?",
                                         ("disabled-renter",)).fetchone()["status"]
        assert status == "disabled"
        assert _login(client, "disabled-renter", "very-safe-password-1").status_code == 403
