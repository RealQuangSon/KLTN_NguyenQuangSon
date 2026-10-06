"""Single source of truth for roles, capabilities and entity states (W-01).

Every permission decision names a capability from this module instead of a
bare role string, so the matrix can be reviewed and tested as one artifact.
Admin is a role with explicit administrative capabilities, never a wildcard
that bypasses resource ownership checks.
"""
from __future__ import annotations

from .models import DomainError, Role

RENTER = "renter"
OWNER = "owner"
MANAGER = "manager"
ADMIN = "admin"
ROLES: tuple[Role, ...] = (RENTER, OWNER, MANAGER, ADMIN)

# Renter capabilities cover the renter-owned resources of the 0.3.0 flow.
RENTER_CAPABILITIES = frozenset({
    "session.create",
    "session.read.own",
    "cost.estimate",
    "viewing.create.own",
    "profile.manage.own",
    "auth.sessions.manage.own",
})

# Owner capabilities are organization-scoped: they only apply inside
# organizations where the actor holds an active owner membership.
OWNER_CAPABILITIES = frozenset({
    "org.read",
    "org.members.read",
    "org.members.manage",
})

# Manager capabilities enforced by the current 0.3.0 endpoints.
MANAGER_CAPABILITIES = frozenset({
    "org.read",
    "org.members.read",
    "recommendation.review.assigned",
    "recommendation.retry.assigned",
    "catalog.read.private",
    "catalog.status.update",
    "viewing.respond.assigned",
    "support.read.assigned",
    "metrics.read",
})

# Admin capabilities are administrative only; they never replace
# resource ownership checks for renter data.
ADMIN_CAPABILITIES = frozenset({
    "org.create",
    "org.read.all",
    "org.members.read",
    "org.members.manage",
    "audit.read",
})

ROLE_CAPABILITIES: dict[Role, frozenset[str]] = {
    RENTER: RENTER_CAPABILITIES,
    OWNER: OWNER_CAPABILITIES,
    MANAGER: MANAGER_CAPABILITIES,
    ADMIN: ADMIN_CAPABILITIES,
}

# State dictionaries for the entities introduced with schema v3 (W-01/W-02).
ORGANIZATION_STATES = ("active", "suspended", "archived")
ORGANIZATION_TRANSITIONS = {
    "active": frozenset({"suspended", "archived"}),
    "suspended": frozenset({"active", "archived"}),
    "archived": frozenset(),
}

MEMBERSHIP_STATES = ("active", "revoked")
MEMBERSHIP_TRANSITIONS = {
    "active": frozenset({"revoked"}),
    "revoked": frozenset(),
}

ACCOUNT_STATES = ("unverified", "active", "disabled")
ACCOUNT_TRANSITIONS = {
    "unverified": frozenset({"active", "disabled"}),
    "active": frozenset({"disabled"}),
    "disabled": frozenset({"active"}),
}

# Consent flags a user can toggle on their own profile (W-03).
CONSENT_TYPES = ("save_history", "remember_sessions")

# Purposes of single-use verification tokens.
TOKEN_PURPOSES = ("email_verification", "password_reset")


def capabilities_for(role: Role) -> frozenset[str]:
    return ROLE_CAPABILITIES[role]


def role_has_capability(role: Role, capability: str) -> bool:
    return capability in ROLE_CAPABILITIES[role]


def assert_capability(role: Role, capability: str, message: str | None = None):
    if not role_has_capability(role, capability):
        raise DomainError("forbidden",
                          message or "Vai trò không được phép thực hiện thao tác này.", 403)


def assert_state_transition(states: tuple[str, ...], transitions: dict[str, frozenset[str]],
                            current: str, target: str, entity: str):
    if current not in states or target not in states:
        raise DomainError("invalid_state", f"Trạng thái {entity} không hợp lệ.", 422)
    if target not in transitions[current]:
        raise DomainError("invalid_state",
                          f"{entity} không thể chuyển từ {current} sang {target}.", 409)
