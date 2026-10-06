"""Organizations, memberships, room ownership and the audit log (W-01/W-02).

Deterministic, server-side only: roles and organization grants never come
from the client. Every mutation writes an audit entry in the same
transaction. Bootstrap is idempotent so existing demo databases migrate
into the default organization without deleting or reclassifying records.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from .capabilities import ADMIN, assert_capability
from .models import Actor, DomainError

# Local timestamp helper to keep this module import-cycle-free from repository.


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

DEFAULT_ORGANIZATION_ID = "org-demo"
DEFAULT_ORGANIZATION_NAME = "Đơn vị demo HomeMatch"

# Staff seed accounts that receive a membership in the default organization.
# Renters are customers and stay organization-less by design.
STAFF_SEED_MEMBERSHIPS = (
    ("owner-a", "owner"),
    ("owner-b", "owner"),
    ("owner-c", "owner"),
    ("owner-d", "owner"),
    ("manager-a", "manager"),
    ("manager-b", "manager"),
    ("admin-a", "admin"),
)


def ensure_bootstrap(repo) -> None:
    """Idempotently create the default organization, seed-staff memberships
    and ownership mappings for catalog rooms that have none.

    Runs on every repository open so legacy databases and freshly imported
    rooms converge to the same ownership state without manual steps.
    """
    now = utc_now()
    with repo.db:
        repo.db.execute(
            "INSERT INTO hm_organizations(id,name,revision,status,created_at,updated_at) "
            "VALUES(?,?,1,'active',?,?) ON CONFLICT(id) DO NOTHING",
            (DEFAULT_ORGANIZATION_ID, DEFAULT_ORGANIZATION_NAME, now, now))
        for username, role in STAFF_SEED_MEMBERSHIPS:
            if repo.db.execute("SELECT id FROM hm_users WHERE id=?", (username,)).fetchone() is None:
                continue
            membership_id = f"mbr-{DEFAULT_ORGANIZATION_ID}-{username}"
            repo.db.execute(
                "INSERT INTO hm_memberships(id,organization_id,user_id,role,status,revision,"
                "created_at,updated_at) VALUES(?,?,?,?,'active',1,?,?) "
                "ON CONFLICT(organization_id,user_id) DO NOTHING",
                (membership_id, DEFAULT_ORGANIZATION_ID, username, role, now, now))
        # Shared demo catalog rooms belong to the default organization; the
        # owner column stays NULL when no owner account exists yet.
        owner_id = "owner-a" if repo.db.execute(
            "SELECT id FROM hm_users WHERE id='owner-a'").fetchone() else None
        unclaimed = repo.db.execute(
            "SELECT id FROM hm_rooms WHERE id NOT IN (SELECT room_id FROM hm_room_ownership)").fetchall()
        for row in unclaimed:
            repo.db.execute(
                "INSERT INTO hm_room_ownership(room_id,organization_id,owner_id,created_at,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(room_id) DO NOTHING",
                (row["id"], DEFAULT_ORGANIZATION_ID, owner_id, now, now))


def record_audit(repo, actor: Actor, action: str, resource_type: str, resource_id: str,
                 organization_id: str | None = None, detail: dict | None = None) -> dict:
    """Append an audit entry; call inside the caller's transaction for atomicity."""
    entry = {"id": str(uuid4()), "actor_id": actor.id, "actor_role": actor.role,
             "organization_id": organization_id, "action": action,
             "resource_type": resource_type, "resource_id": resource_id,
             "detail_json": json.dumps(detail or {}, ensure_ascii=False), "created_at": utc_now()}
    repo.db.execute(
        "INSERT INTO hm_audit_log(id,actor_id,actor_role,organization_id,action,"
        "resource_type,resource_id,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (entry["id"], entry["actor_id"], entry["actor_role"], entry["organization_id"],
         entry["action"], entry["resource_type"], entry["resource_id"],
         entry["detail_json"], entry["created_at"]))
    return {key: (json.loads(value) if key == "detail_json" else value) for key, value in entry.items()}


def audit_entries(repo, resource_type: str | None = None, resource_id: str | None = None,
                  actor_id: str | None = None, organization_id: str | None = None,
                  action: str | None = None) -> list[dict]:
    query = "SELECT * FROM hm_audit_log WHERE 1=1"
    params: list[str] = []
    if resource_type is not None:
        query += " AND resource_type=?"
        params.append(resource_type)
    if resource_id is not None:
        query += " AND resource_id=?"
        params.append(resource_id)
    if actor_id is not None:
        query += " AND actor_id=?"
        params.append(actor_id)
    if organization_id is not None:
        query += " AND organization_id=?"
        params.append(organization_id)
    if action is not None:
        query += " AND action=?"
        params.append(action)
    query += " ORDER BY created_at,id"
    rows = repo.db.execute(query, tuple(params)).fetchall()
    result = []
    for row in rows:
        entry = dict(row)
        entry["detail"] = json.loads(entry.pop("detail_json"))
        result.append(entry)
    return result


def active_membership(repo, organization_id: str, user_id: str) -> dict | None:
    row = repo.db.execute(
        "SELECT * FROM hm_memberships WHERE organization_id=? AND user_id=? AND status='active'",
        (organization_id, user_id)).fetchone()
    return dict(row) if row else None


def membership_by_id(repo, organization_id: str, membership_id: str) -> dict:
    row = repo.db.execute("SELECT * FROM hm_memberships WHERE id=?", (membership_id,)).fetchone()
    if row is None or row["organization_id"] != organization_id:
        raise DomainError("not_found", "Không tìm thấy thành viên trong đơn vị này.", 404)
    return dict(row)


def require_org_role(repo, actor: Actor, organization_id: str, roles: tuple[str, ...]) -> dict | None:
    """Return the actor's qualifying membership; a global admin passes without one."""
    if "owner" in roles:
        assert_capability(actor.role, "org.members.manage")
    else:
        assert_capability(actor.role, "org.members.read")
    if actor.role == ADMIN:
        return None
    membership = active_membership(repo, organization_id, actor.id)
    if membership is None or membership["role"] not in roles:
        raise DomainError("forbidden", "Bạn không có quyền trong đơn vị này.", 403)
    return membership


def require_org_read(repo, actor: Actor, organization_id: str) -> dict | None:
    """Read access for an organization: any active member or a global admin."""
    if actor.role != ADMIN:
        assert_capability(actor.role, "org.read")
        membership = active_membership(repo, organization_id, actor.id)
        if membership is None:
            raise DomainError("forbidden", "Bạn không có quyền trong đơn vị này.", 403)
        return membership
    if repo.db.execute("SELECT id FROM hm_organizations WHERE id=?", (organization_id,)).fetchone() is None:
        raise DomainError("not_found", "Không tìm thấy đơn vị.", 404)
    return None


def organization_row(repo, organization_id: str) -> dict:
    row = repo.db.execute("SELECT * FROM hm_organizations WHERE id=?", (organization_id,)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy đơn vị.", 404)
    return dict(row)


def list_organizations(repo, actor: Actor) -> list[dict]:
    if actor.role == ADMIN:
        rows = repo.db.execute(
            "SELECT o.*, 'admin' AS actor_role FROM hm_organizations o ORDER BY o.id").fetchall()
        return [dict(row) for row in rows]
    rows = repo.db.execute(
        "SELECT o.*, m.role AS actor_role FROM hm_organizations o "
        "JOIN hm_memberships m ON m.organization_id=o.id "
        "WHERE m.user_id=? AND m.status='active' ORDER BY o.id", (actor.id,)).fetchall()
    return [dict(row) for row in rows]


def create_organization(repo, actor: Actor, name: str) -> dict:
    assert_capability(actor.role, "org.create", "Chỉ quản trị viên được tạo đơn vị.")
    name = name.strip()
    if not 2 <= len(name) <= 120:
        raise DomainError("invalid_organization", "Tên đơn vị cần 2–120 ký tự.", 422)
    organization_id = "org-" + str(uuid4())[:8]
    now = utc_now()
    with repo.db:
        repo.db.execute(
            "INSERT INTO hm_organizations(id,name,revision,status,created_at,updated_at) "
            "VALUES(?,?,1,'active',?,?)", (organization_id, name, now, now))
        repo.db.execute(
            "INSERT INTO hm_memberships(id,organization_id,user_id,role,status,revision,"
            "created_at,updated_at) VALUES(?,?,?,'admin','active',1,?,?)",
            (f"mbr-{organization_id}-{actor.id}", organization_id, actor.id, now, now))
        record_audit(repo, actor, "organization.created", "organization", organization_id,
                     organization_id=organization_id, detail={"name_length": len(name)})
    return organization_row(repo, organization_id)


def list_memberships(repo, actor: Actor, organization_id: str) -> list[dict]:
    require_org_read(repo, actor, organization_id)
    rows = repo.db.execute(
        "SELECT * FROM hm_memberships WHERE organization_id=? ORDER BY created_at,id",
        (organization_id,)).fetchall()
    return [dict(row) for row in rows]


def _require_grantable_account(repo, user_id: str) -> None:
    user = repo.db.execute("SELECT id,role FROM hm_users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        raise DomainError("user_not_found", "Không tìm thấy tài khoản.", 404)
    profile = repo.db.execute(
        "SELECT status,email_verified FROM hm_account_profiles WHERE user_id=?", (user_id,)).fetchone()
    if profile is None:
        return
    if profile["status"] == "disabled":
        raise DomainError("account_disabled", "Tài khoản đã bị vô hiệu hóa, không thể cấp quyền.", 409)
    if profile["status"] != "active" or not profile["email_verified"]:
        raise DomainError("account_unverified", "Tài khoản chưa kích hoạt, không thể cấp quyền.", 409)


def grant_membership(repo, actor: Actor, organization_id: str, user_id: str, role: str) -> dict:
    organization_row(repo, organization_id)
    require_org_role(repo, actor, organization_id, roles=("owner",))
    if user_id == actor.id:
        raise DomainError("cannot_modify_own_membership",
                          "Không thể tự thay đổi membership của chính mình.", 403)
    _require_grantable_account(repo, user_id)
    now = utc_now()
    with repo.db:
        existing = repo.db.execute(
            "SELECT * FROM hm_memberships WHERE organization_id=? AND user_id=?",
            (organization_id, user_id)).fetchone()
        if existing is not None and existing["status"] == "active":
            raise DomainError("membership_exists", "Tài khoản đã là thành viên của đơn vị.", 409)
        if existing is not None:
            # A revoked member can be re-granted, producing a new revision.
            repo.db.execute(
                "UPDATE hm_memberships SET role=?,status='active',revision=revision+1,updated_at=? WHERE id=?",
                (role, now, existing["id"]))
            membership_id = existing["id"]
        else:
            membership_id = str(uuid4())
            repo.db.execute(
                "INSERT INTO hm_memberships(id,organization_id,user_id,role,status,revision,"
                "created_at,updated_at) VALUES(?,?,?,?,'active',1,?,?)",
                (membership_id, organization_id, user_id, role, now, now))
        record_audit(repo, actor, "membership.granted", "membership", membership_id,
                     organization_id=organization_id, detail={"member_user_id": user_id, "role": role})
    return membership_by_id(repo, organization_id, membership_id)


def revoke_membership(repo, actor: Actor, organization_id: str, membership_id: str) -> dict:
    organization_row(repo, organization_id)
    require_org_role(repo, actor, organization_id, roles=("owner",))
    membership = membership_by_id(repo, organization_id, membership_id)
    if membership["user_id"] == actor.id:
        raise DomainError("cannot_modify_own_membership",
                          "Không thể tự thu hồi membership của chính mình.", 403)
    if membership["status"] != "active":
        raise DomainError("membership_revoked", "Membership này đã bị thu hồi trước đó.", 409)
    with repo.db:
        repo.db.execute(
            "UPDATE hm_memberships SET status='revoked',revision=revision+1,updated_at=? WHERE id=?",
            (utc_now(), membership_id))
        record_audit(repo, actor, "membership.revoked", "membership", membership_id,
                     organization_id=organization_id,
                     detail={"member_user_id": membership["user_id"]})
    return membership_by_id(repo, organization_id, membership_id)
