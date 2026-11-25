"""W-01/W-02 checks: capability matrix, organizations/memberships, audit and
migration from a v2-style database. Permission positives and negatives run at
both the service layer and the HTTP layer."""
import pytest
from fastapi.testclient import TestClient

from backend.app import organizations
from backend.app.auth import SeedAuth
from backend.app.capabilities import (ACCOUNT_STATES, ACCOUNT_TRANSITIONS, ADMIN_CAPABILITIES,
                                      MEMBERSHIP_STATES, MEMBERSHIP_TRANSITIONS,
                                      ORGANIZATION_STATES, ORGANIZATION_TRANSITIONS,
                                      ROLE_CAPABILITIES, assert_capability, capabilities_for)
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.migrations import MIGRATIONS, SCHEMA_VERSION
from backend.app.models import Actor, DomainError
from backend.app.repository import Repository


def _create_user(repo, user_id, role):
    repo.db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES(?,?,?)",
                    (user_id, role, "fixture-hash-not-a-password"))


def _bootstrap_with_staff(service, extra=()):
    for user_id, role in (("admin", "admin"), ("owner1", "owner"), ("owner2", "owner"), *extra):
        _create_user(service.repo, user_id, role)
    organizations.ensure_bootstrap(service.repo)


# --- Capability matrix (single source of truth, W-01) ---

def test_matrix_covers_exactly_three_roles_with_scoped_staff_rights():
    assert set(ROLE_CAPABILITIES) == {"renter", "owner", "admin"}
    assert "org.create" in capabilities_for("admin")
    assert "org.members.manage" in capabilities_for("owner")
    # Quyết định 05/11/2026: không còn quyền duyệt gợi ý cho vai nào.
    assert "recommendation.review.assigned" not in capabilities_for("owner")
    # Admin is not a wildcard: it never gains renter resource capabilities.
    assert not (ADMIN_CAPABILITIES & capabilities_for("renter"))
    assert "session.create" not in capabilities_for("admin")
    # Renters never hold organization or staff capabilities.
    renter_scope = capabilities_for("renter")
    assert not renter_scope & {"org.create", "org.members.manage", "audit.read",
                               "catalog.status.update"}


def test_state_dictionaries_are_closed_and_self_consistent():
    for states, transitions in ((ORGANIZATION_STATES, ORGANIZATION_TRANSITIONS),
                                (MEMBERSHIP_STATES, MEMBERSHIP_TRANSITIONS),
                                (ACCOUNT_STATES, ACCOUNT_TRANSITIONS)):
        assert set(transitions) == set(states)
        for targets in transitions.values():
            assert targets <= set(states)
    assert "revoked" in MEMBERSHIP_TRANSITIONS["active"]
    assert MEMBERSHIP_TRANSITIONS["revoked"] == frozenset()


def test_assert_capability_raises_forbidden_403():
    with pytest.raises(DomainError) as error:
        assert_capability("renter", "org.create")
    assert error.value.code == "forbidden" and error.value.http_status == 403
    assert_capability("admin", "org.create")  # positive does not raise


# --- Service-level organization/membership permissions and audit ---

def test_bootstrap_is_idempotent_and_maps_room_ownership(service):
    _bootstrap_with_staff(service)
    memberships = service.repo.db.execute(
        "SELECT organization_id,user_id,role FROM hm_memberships ORDER BY user_id").fetchall()
    assert {row["user_id"] for row in memberships} == {"admin", "owner1", "owner2"}
    organizations.ensure_bootstrap(service.repo)
    assert service.repo.db.execute("SELECT COUNT(*) AS c FROM hm_memberships").fetchone()["c"] == len(memberships)
    rooms = service.catalog.rooms()
    organizations.ensure_bootstrap(service.repo)
    owned = service.repo.db.execute("SELECT room_id,organization_id,owner_id FROM hm_room_ownership").fetchall()
    assert {row["room_id"] for row in owned} == {room.id for room in rooms}
    assert all(row["organization_id"] == organizations.DEFAULT_ORGANIZATION_ID for row in owned)
    assert all(row["owner_id"] == "owner2" for row in owned)


def test_only_admin_creates_organization_and_creator_becomes_member(service, admin, landlord):
    _bootstrap_with_staff(service)
    created = organizations.create_organization(service.repo, admin, "Đơn vị owner B")
    assert created["status"] == "active" and created["revision"] == 1
    with pytest.raises(DomainError) as error:
        organizations.create_organization(service.repo, landlord, "Đơn vị trái phép")
    assert error.value.code == "forbidden" and error.value.http_status == 403
    entries = organizations.audit_entries(service.repo, action="organization.created")
    assert [entry["resource_id"] for entry in entries] == [created["id"]]
    assert entries[0]["actor_id"] == "admin"


def test_grant_revoke_membership_permissions_isolation_and_audit(service, admin, owner, landlord):
    _bootstrap_with_staff(service, extra=(("candidate-a", "renter"),))
    org = organizations.create_organization(service.repo, admin, "Đơn vị B")["id"]
    # An owner of another organization cannot read or grant in this one.
    with pytest.raises(DomainError) as error:
        organizations.list_memberships(service.repo, landlord, org)
    assert error.value.code == "forbidden" and error.value.http_status == 403
    with pytest.raises(DomainError) as error:
        organizations.grant_membership(service.repo, landlord, org, "candidate-a", "admin")
    assert error.value.code == "forbidden"
    # Global admin grants owner2, who then manages the org; self-service is blocked.
    organizations.grant_membership(service.repo, admin, org, "owner2", "owner")
    granted = organizations.grant_membership(service.repo, owner, org, "candidate-a", "admin")
    assert granted["role"] == "admin" and granted["status"] == "active"
    # Duplicate grant, self-modification and unknown users are rejected.
    with pytest.raises(DomainError) as error:
        organizations.grant_membership(service.repo, owner, org, "candidate-a", "admin")
    assert error.value.code == "membership_exists" and error.value.http_status == 409
    with pytest.raises(DomainError) as error:
        organizations.grant_membership(service.repo, owner, org, "owner2", "owner")
    assert error.value.code == "cannot_modify_own_membership" and error.value.http_status == 403
    with pytest.raises(DomainError) as error:
        organizations.grant_membership(service.repo, owner, org, "ghost-user", "admin")
    assert error.value.code == "user_not_found" and error.value.http_status == 404
    # Revocation: owner can revoke others but not themselves; replay conflicts.
    own_membership_id = next(item["id"] for item in organizations.list_memberships(service.repo, owner, org)
                             if item["user_id"] == owner.id)
    with pytest.raises(DomainError) as error:
        organizations.revoke_membership(service.repo, owner, org, own_membership_id)
    assert error.value.code == "cannot_modify_own_membership" and error.value.http_status == 403
    revoked = organizations.revoke_membership(service.repo, owner, org, granted["id"])
    assert revoked["status"] == "revoked" and revoked["revision"] == granted["revision"] + 1
    with pytest.raises(DomainError) as error:
        organizations.revoke_membership(service.repo, owner, org, granted["id"])
    assert error.value.code == "membership_revoked"
    # Revoked members lose read access immediately; re-grant reactivates.
    with pytest.raises(DomainError) as error:
        organizations.list_memberships(service.repo, Actor(id="candidate-a", role="renter"), org)
    assert error.value.code == "forbidden"
    reactivated = organizations.grant_membership(service.repo, owner, org, "candidate-a", "admin")
    assert reactivated["status"] == "active" and reactivated["revision"] == granted["revision"] + 2
    actions = [entry["action"] for entry in organizations.audit_entries(service.repo, organization_id=org)]
    assert actions.count("membership.granted") == 3 and "membership.revoked" in actions


def test_organization_listing_scopes_by_membership(service, admin, owner, landlord, renter):
    _bootstrap_with_staff(service)
    visible = organizations.list_organizations(service.repo, owner)
    assert [org["id"] for org in visible] == [organizations.DEFAULT_ORGANIZATION_ID]
    assert visible[0]["actor_role"] == "owner"
    assert len(organizations.list_organizations(service.repo, admin)) >= 1
    # A renter with no membership sees nothing.
    assert organizations.list_organizations(service.repo, renter) == []


def test_unverified_account_cannot_be_granted_membership(service, admin, owner):
    from backend.app.auth import register_account
    _bootstrap_with_staff(service, extra=(("pending-a", "renter"),))
    org = organizations.create_organization(service.repo, admin, "Đơn vị C")["id"]
    organizations.grant_membership(service.repo, admin, org, "owner2", "owner")
    register_account(service.repo, "unverified-a", "very-safe-password-1", "unverified-a@example.com")
    with pytest.raises(DomainError) as error:
        organizations.grant_membership(service.repo, owner, org, "unverified-a", "admin")
    assert error.value.code == "account_unverified" and error.value.http_status == 409


# --- Migration from a v2-style database (W-02) ---

def test_v2_style_database_migrates_to_v3_without_data_loss(storage):
    db = Database(storage)
    db.executescript(MIGRATIONS[0][2])
    db.executescript(MIGRATIONS[1][2])
    db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES('manager-a','manager','legacy-hash')")
    db.execute("INSERT INTO hm_sessions(id,owner_id,manager_id,draft_revision,draft_json) "
               "VALUES('legacy-session','renter','manager-a',0,'{}')")
    db.execute("INSERT INTO hm_runs(id,session_id,profile_version,catalog_version,profile_json,status,created_at) "
               "VALUES('legacy-run','legacy-session',1,'legacy-catalog','{}','pending_review',"
               "'2026-01-01T00:00:00+00:00')")
    db.execute("INSERT INTO hm_rooms(id,revision,payload_json) VALUES('legacy-room',1,'{}')")
    db.close()
    # First open migrates and bootstraps; the second proves idempotency.
    first = Repository(storage)
    first.close()
    repo = Repository(storage)
    try:
        assert repo.schema_version == SCHEMA_VERSION
        assert repo.db.execute("SELECT COUNT(*) AS c FROM hm_schema_migrations").fetchone()["c"] == len(MIGRATIONS)
        # Migration 16 (bỏ duyệt gợi ý): run cũ đang chờ duyệt chuyển hết hiệu lực.
        assert repo.run("legacy-run")["status"] == "invalidated"
        # Migration 24 (bỏ vai manager): tài khoản staff cũ bị xóa cùng membership.
        assert repo.db.execute("SELECT COUNT(*) AS c FROM hm_users WHERE id='manager-a'").fetchone()["c"] == 0
        assert repo.db.execute(
            "SELECT COUNT(*) AS c FROM hm_memberships WHERE user_id='manager-a'").fetchone()["c"] == 0
        # Default organization exists; business data (session, run) survives.
        orgs = repo.db.execute("SELECT id FROM hm_organizations").fetchall()
        assert [row["id"] for row in orgs] == [organizations.DEFAULT_ORGANIZATION_ID]
        assert repo.db.execute("SELECT COUNT(*) AS c FROM hm_sessions").fetchone()["c"] == 1
        # Unmapped legacy rooms converge into the default organization.
        owned = repo.db.execute(
            "SELECT organization_id FROM hm_room_ownership WHERE room_id='legacy-room'").fetchone()
        assert owned["organization_id"] == organizations.DEFAULT_ORGANIZATION_ID
    finally:
        repo.close()


def test_retiring_legacy_owner_releases_owned_rooms(storage):
    # A v23 database whose demo room still belongs to a legacy owner account:
    # migration 24 must clear the ownership before deleting the user, or the
    # foreign key (enforced on PostgreSQL and SQLite) aborts startup.
    db = Database(storage)
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS hm_schema_migrations ("
                   "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
        for version, name, sql in MIGRATIONS[:-1]:
            db.executescript(sql)
            db.execute("INSERT INTO hm_schema_migrations VALUES(?,?,?)",
                       (version, name, "2026-11-01T00:00:00+00:00"))
        db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES('owner-a','owner','legacy-hash')")
        db.execute("INSERT INTO hm_organizations(id,name,revision,status,created_at,updated_at) "
                   "VALUES(?,?,1,'active','2026-11-01','2026-11-01')",
                   (organizations.DEFAULT_ORGANIZATION_ID, organizations.DEFAULT_ORGANIZATION_NAME))
        db.execute("INSERT INTO hm_rooms(id,revision,payload_json) VALUES('legacy-room',1,'{}')")
        db.execute("INSERT INTO hm_room_ownership(room_id,organization_id,owner_id,created_at,updated_at) "
                   "VALUES('legacy-room',?,'owner-a','2026-11-01','2026-11-01')",
                   (organizations.DEFAULT_ORGANIZATION_ID,))
    db.close()
    repo = Repository(storage)
    try:
        assert repo.schema_version == SCHEMA_VERSION
        assert repo.db.execute("SELECT COUNT(*) AS c FROM hm_users WHERE id='owner-a'").fetchone()["c"] == 0
        owned = repo.db.execute(
            "SELECT organization_id,owner_id FROM hm_room_ownership WHERE room_id='legacy-room'").fetchone()
        assert owned["organization_id"] == organizations.DEFAULT_ORGANIZATION_ID
        assert owned["owner_id"] is None
    finally:
        repo.close()


# --- HTTP layer: permission positives/negatives on the new endpoints ---

def _login(client, username):
    response = client.post("/auth/login", json={"username": username,
                                                "password": "123456"})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_organization_http_permission_matrix(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        admin, owner = _login(client, "admin"), _login(client, "owner2")
        landlord, renter = _login(client, "owner1"), _login(client, "renter")
        default_org = organizations.DEFAULT_ORGANIZATION_ID
        # Creation is admin-only; every role difference returns 403 with the envelope.
        created = client.post("/organizations", headers=admin, json={"name": "Đơn vị B"})
        assert created.status_code == 201 and created.json()["revision"] == 1
        org = created.json()["id"]
        for headers in (owner, landlord, renter):
            assert client.post("/organizations", headers=headers,
                               json={"name": "Không được"}).status_code == 403
        # Listing is scoped: admin sees all, member sees own, renter sees none.
        assert org in {item["id"] for item in client.get("/organizations", headers=admin).json()}
        assert {item["id"] for item in client.get("/organizations", headers=owner).json()} == {default_org}
        assert client.get("/organizations", headers=renter).json() == []
        # Membership read: member yes, outsider no.
        assert client.get(f"/organizations/{org}/memberships", headers=admin).status_code == 200
        assert client.get(f"/organizations/{org}/memberships", headers=landlord).status_code == 403
        # Grant path: admin makes owner2 an owner of the new org, then owner grants.
        assert client.post(f"/organizations/{org}/memberships", headers=admin,
                           json={"user_id": "owner2", "role": "owner"}).status_code == 201
        granted = client.post(f"/organizations/{org}/memberships", headers=owner,
                              json={"user_id": "renter", "role": "admin"})
        assert granted.status_code == 201 and granted.json()["role"] == "admin"
        # A client-proposed role/org is never honored: admin-only creation, no self-elevation.
        assert client.post(f"/organizations/{org}/memberships", headers=owner,
                           json={"user_id": "owner2", "role": "owner"}).status_code == 403
        assert client.post(f"/organizations/{org}/memberships", headers=renter,
                           json={"user_id": "renter", "role": "owner"}).status_code == 403
        assert client.post(f"/organizations/{org}/memberships", headers=owner,
                           json={"user_id": "ghost", "role": "admin"}).status_code == 404
        # Audit trail exists for every mutation of this organization.
        audit = organizations.audit_entries(service.repo, organization_id=org)
        assert {entry["action"] for entry in audit} == {"organization.created",
                                                        "membership.granted"}


def test_membership_revoke_http_and_immediate_access_loss(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        admin, owner = _login(client, "admin"), _login(client, "owner2")
        landlord = _login(client, "owner1")
        org = client.post("/organizations", headers=admin, json={"name": "Đơn vị D"}).json()["id"]
        client.post(f"/organizations/{org}/memberships", headers=admin,
                    json={"user_id": "owner1", "role": "admin"})
        membership_id = next(item["id"] for item in
                             client.get(f"/organizations/{org}/memberships", headers=admin).json()
                             if item["user_id"] == "owner1")
        assert client.get(f"/organizations/{org}/memberships", headers=landlord).status_code == 200
        revoked = client.delete(f"/organizations/{org}/memberships/{membership_id}", headers=owner)
        # owner1 is not an owner of this org: only admin may revoke here.
        assert revoked.status_code == 403
        revoked = client.delete(f"/organizations/{org}/memberships/{membership_id}", headers=admin)
        assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
        assert client.get(f"/organizations/{org}/memberships", headers=landlord).status_code == 403
        assert client.delete(f"/organizations/{org}/memberships/{membership_id}",
                             headers=admin).status_code == 409


def test_seed_login_covers_three_roles_and_demo_tokens_exist(service, monkeypatch):
    monkeypatch.setenv("HOMEMATCH_AUTH_MODE", "seed")
    with TestClient(create_app(lambda: service)) as client:
        for username, role in (("renter", "renter"), ("owner1", "owner"), ("owner2", "owner"),
                               ("admin", "admin")):
            actor = client.get("/auth/me", headers=_login(client, username)).json()
            assert (actor["id"], actor["role"]) == (username, role)


def test_public_mode_seed_startup_bootstraps_organizations(service, monkeypatch):
    """SeedAuth after seeding users must leave staff memberships in place."""
    SeedAuth(service.repo, service.lock)
    rows = service.repo.db.execute(
        "SELECT user_id,role FROM hm_memberships WHERE organization_id=?",
        (organizations.DEFAULT_ORGANIZATION_ID,)).fetchall()
    assert {row["user_id"]: row["role"] for row in rows} == {
        "owner1": "owner", "owner2": "owner", "admin": "admin"}
