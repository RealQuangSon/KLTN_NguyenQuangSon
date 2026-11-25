"""BE-03: landlord self-signup (account_type="owner") with admin approval.

A new landlord verifies email, then stays landlord_status='pending': they can
log in and draft/edit listings but never publish until an admin approves.
Seed owners (owner-*) are always treated as approved. Delivery stays the
labelled dev stub; everything runs offline.
"""
import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from backend.app.catalog import DEFAULT_CATALOG
from backend.app.main import create_app
from backend.app.organizations import audit_entries

QUOTE = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))["rooms"][0]["quote"]
PASSWORD = "very-safe-password-1"


def _headers(client, username, password=None):
    response = client.post("/auth/login", json={
        "username": username, "password": password or "123456"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _register_landlord(client, caplog, username="new-owner"):
    """Register an owner, verify through the dev-stub code and log in."""
    registered = client.post("/auth/register", json={
        "username": username, "password": PASSWORD, "email": f"{username}@example.com",
        "display_name": "Chủ nhà mới", "account_type": "owner"})
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"] == {"id": username, "role": "owner"}
    code = re.findall(r"verification_code=(\S+)", caplog.text)[-1]
    assert client.post("/auth/verify", json={"username": username, "token": code}).status_code == 200
    return _headers(client, username, PASSWORD)


def _room_payload(published=False):
    return {"title": "Studio mới Quận 7", "city": "TP.HCM", "area": "Quận 7", "room_type": "studio",
            "area_m2": 28, "capacity": 2, "published": published, "quote": QUOTE}


def test_pending_landlord_can_draft_but_never_publish(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        landlord = _register_landlord(client, caplog)
        me = client.get("/auth/me", headers=landlord)
        assert me.status_code == 200 and me.json()["landlord_status"] == "pending"
        # Drafting without publishing works and stays invisible to renters.
        created = client.post("/landlord/rooms", headers=landlord, json=_room_payload(published=False))
        assert created.status_code == 201, created.text
        room_id = created.json()["room"]["id"]
        assert created.json()["room"]["published"] is False
        assert client.get(f"/listings/{room_id}").status_code == 404
        # Explicit publish attempts are rejected with the contract error code.
        for response in (
            client.post("/landlord/rooms", headers=landlord, json=_room_payload(published=True)),
            client.put(f"/landlord/rooms/{room_id}", headers=landlord,
                       json={**_room_payload(published=True), "expected_revision": 1}),
            client.patch(f"/landlord/rooms/{room_id}/status", headers=landlord,
                         json={"expected_revision": 1, "published": True}),
        ):
            assert response.status_code == 403, response.text
            assert response.json()["error"]["code"] == "landlord_not_approved"
        # Editing an unpublished draft still works while pending.
        edited = client.put(f"/landlord/rooms/{room_id}", headers=landlord,
                            json={**_room_payload(published=False), "expected_revision": 1,
                                  "title": "Studio mới Quận 7 (đã sửa)"})
        assert edited.status_code == 200 and edited.json()["room"]["revision"] == 2


def test_admin_approval_publishes_grants_membership_audits_and_notifies(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        landlord = _register_landlord(client, caplog)
        room_id = client.post("/landlord/rooms", headers=landlord,
                              json=_room_payload(published=False)).json()["room"]["id"]
        admin = _headers(client, "admin")
        applications = client.get("/admin/landlord-applications", headers=admin, params={"status": "pending"})
        assert applications.status_code == 200
        entry = next(item for item in applications.json() if item["user_id"] == "new-owner")
        assert entry["landlord_status"] == "pending" and entry["email"] == "new-owner@example.com"
        assert entry["verified"] is True and entry["display_name"] == "Chủ nhà mới"
        approved = client.post("/admin/landlord-applications/new-owner/approve", headers=admin)
        assert approved.status_code == 200
        assert approved.json() == {"user_id": "new-owner", "landlord_status": "approved"}
        # The landlord account is approved and the draft can finally be published.
        assert client.get("/auth/me", headers=landlord).json()["landlord_status"] == "approved"
        published = client.patch(f"/landlord/rooms/{room_id}/status", headers=landlord,
                                 json={"expected_revision": 1, "published": True})
        assert published.status_code == 200 and published.json()["room"]["published"] is True
        assert client.get(f"/listings/{room_id}").status_code == 200
        # Approval grants the default-organization owner membership.
        membership = service.repo.db.execute(
            "SELECT role,status,organization_id FROM hm_memberships WHERE user_id='new-owner'").fetchone()
        assert membership["role"] == "owner" and membership["status"] == "active"
        assert membership["organization_id"] == "org-demo"
        # The decision is audited and the landlord is notified once.
        audit = audit_entries(service.repo, resource_type="account", resource_id="new-owner",
                              action="account.landlord_approved")
        assert len(audit) == 1 and audit[0]["actor_id"] == "admin"
        notifications = client.get("/notifications", headers=landlord).json()["items"]
        assert [item["kind"] for item in notifications] == ["landlord_review"]
        # A repeated approve stays idempotent for the inbox (dedup key) and the ledger.
        again = client.post("/admin/landlord-applications/new-owner/approve", headers=admin)
        assert again.status_code == 200 and again.json()["landlord_status"] == "approved"
        assert len(audit_entries(service.repo, resource_type="account", resource_id="new-owner",
                                 action="account.landlord_approved")) == 2
        assert len(client.get("/notifications", headers=landlord).json()["items"]) == 1


def test_review_is_admin_only_and_unknown_user_is_404(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        _register_landlord(client, caplog)
        owner = _headers(client, "owner2")
        renter = _headers(client, "renter")
        admin = _headers(client, "admin")
        for headers in (owner, renter):
            assert client.get("/admin/landlord-applications", headers=headers).status_code == 403
            assert client.post("/admin/landlord-applications/new-owner/approve",
                               headers=headers).status_code == 403
            assert client.post("/admin/landlord-applications/new-owner/reject",
                               headers=headers, json={"reason": "Không đủ giấy tờ."}).status_code == 403
        assert client.get("/admin/landlord-applications").status_code == 401
        # Per-record check: the target must be an owner with an application state.
        missing = client.post("/admin/landlord-applications/who-is-this/approve", headers=admin)
        assert missing.status_code == 404
        renter_target = client.post("/admin/landlord-applications/renter/approve", headers=admin)
        assert renter_target.status_code == 404


def test_account_type_is_validated_and_defaults_to_renter(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        invalid = client.post("/auth/register", json={
            "username": "want-admin", "password": PASSWORD, "email": "want-admin@example.com",
            "account_type": "admin"})
        assert invalid.status_code == 422
        # Without account_type the flow stays exactly the old renter flow.
        registered = client.post("/auth/register", json={
            "username": "plain-renter", "password": PASSWORD, "email": "plain-renter@example.com"})
        assert registered.status_code == 201
        assert registered.json()["user"] == {"id": "plain-renter", "role": "renter"}
        code = re.findall(r"verification_code=(\S+)", caplog.text)[-1]
        client.post("/auth/verify", json={"username": "plain-renter", "token": code})
        renter = _headers(client, "plain-renter", PASSWORD)
        me = client.get("/auth/me", headers=renter)
        assert me.status_code == 200 and me.json()["landlord_status"] is None
        # A renter never shows up in landlord applications.
        admin = _headers(client, "admin")
        applications = client.get("/admin/landlord-applications", headers=admin).json()
        assert all(item["user_id"] != "plain-renter" for item in applications)


def test_rejection_requires_reason_and_blocks_publishing(service, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="homematch.api")
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        landlord = _register_landlord(client, caplog)
        admin = _headers(client, "admin")
        missing = client.post("/admin/landlord-applications/new-owner/reject", headers=admin, json={})
        assert missing.status_code == 422
        too_long = client.post("/admin/landlord-applications/new-owner/reject", headers=admin,
                               json={"reason": "x" * 501})
        assert too_long.status_code == 422
        rejected = client.post("/admin/landlord-applications/new-owner/reject", headers=admin,
                               json={"reason": "Thiếu hình ảnh xác thực giấy tờ."})
        assert rejected.status_code == 200
        assert rejected.json() == {"user_id": "new-owner", "landlord_status": "rejected"}
        assert client.get("/auth/me", headers=landlord).json()["landlord_status"] == "rejected"
        assert client.post("/landlord/rooms", headers=landlord,
                           json=_room_payload(published=True)).status_code == 403
        notifications = client.get("/notifications", headers=landlord).json()["items"]
        assert [item["kind"] for item in notifications] == ["landlord_review"]
        assert "Thiếu hình ảnh xác thực" in notifications[0]["body"]
        # The rejected application leaves the pending queue.
        applications = client.get("/admin/landlord-applications", headers=admin,
                                  params={"status": "pending"}).json()
        assert all(item["user_id"] != "new-owner" for item in applications)


def test_seed_owners_stay_approved_and_renters_have_no_status(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        owner = _headers(client, "owner2")
        me = client.get("/auth/me", headers=owner)
        assert me.status_code == 200 and me.json()["landlord_status"] == "approved"
        created = client.post("/landlord/rooms", headers=owner, json=_room_payload(published=True))
        assert created.status_code == 201, created.text
        assert client.get(f"/listings/{created.json()['room']['id']}").status_code == 200
        renter = _headers(client, "renter")
        assert client.get("/auth/me", headers=renter).json()["landlord_status"] is None
        admin = _headers(client, "admin")
        applications = client.get("/admin/landlord-applications", headers=admin).json()
        assert all(not item["user_id"].startswith("owner-") for item in applications)
