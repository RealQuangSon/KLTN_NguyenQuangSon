"""Centralized actor/resource capability matrix for agent-reachable actions.

Every state-changing action reachable from the chat/graph flow is checked here
(actor role + resource ownership + session assignment) before execution. API
permissions live in the service layer, outside the LLM and the graphs: model
output can never add, change or grant a capability — the matrix is static code
and the checks only trust ledger data and the authenticated Actor.

Role vocabulary is anchored to the W-01 single source in capabilities.py
(ROLE_CAPABILITIES / ROLES). This matrix stays action-grained because chat
actions map to resource-scoped checks the role matrix cannot express, but any
role used here must exist there — enforced at import below — so the two
matrices cannot drift into inconsistent role sets.
"""
from __future__ import annotations

from dataclasses import dataclass

from .capabilities import ROLES as DOMAIN_ROLES
from .models import Actor, DomainError

# action -> allowed roles. Resource ownership is verified separately per role:
# a renter must own the session, a manager must be the assigned manager.
CAPABILITIES: dict[str, frozenset[str]] = {
    "session:create": frozenset({"renter"}),
    "session:read": frozenset({"renter", "owner"}),
    "chat:message": frozenset({"renter"}),
    "draft:patch": frozenset({"renter"}),
    "profile:confirm": frozenset({"renter"}),
    "results:read": frozenset({"renter"}),
    "compare:run": frozenset({"renter"}),
    "viewing:prepare": frozenset({"renter"}),
    "viewing:request": frozenset({"renter"}),
    "viewing:read": frozenset({"renter", "owner"}),
    "viewing:respond": frozenset({"owner"}),
    "support:handoff": frozenset({"renter"}),
    "support:list": frozenset({"owner", "admin"}),
    # Landlords review only the rooms they own in a shortlist (per-landlord HITL).
    "run:draft_list": frozenset({"owner"}),
    "run:read": frozenset({"owner"}),
    "run:review": frozenset({"owner"}),
    "run:retry": frozenset({"owner", "admin"}),
    "catalog:read": frozenset({"owner", "admin"}),
    "catalog:write": frozenset({"owner", "admin"}),
}

# Import-time guard: agent actions may only reference domain roles from the
# W-01 matrix; a typo or a role added in one module but not the other fails
# loudly here instead of silently allowing or denying at request time.
_unknown_roles = frozenset().union(*CAPABILITIES.values()) - frozenset(DOMAIN_ROLES)
if _unknown_roles:
    raise ValueError(f"agent_capability references unknown roles: {sorted(_unknown_roles)}")

# Fields only the ledger/service may set. A model answer, extraction or resume
# payload carrying any of these is rejected instead of obeyed (HM-10.AG-AC1).
PRIVILEGED_KEYS = frozenset({"role", "roles", "approved", "approval", "decision",
                             "keep_room_ids", "grant", "permissions",
                             "manager_id", "owner_id"})


@dataclass(frozen=True)
class Resource:
    """Ownership view of a protected resource (currently a chat session)."""
    kind: str
    owner_id: str | None = None
    manager_id: str | None = None

    @classmethod
    def for_session(cls, session: dict) -> "Resource":
        return cls("session", owner_id=session["owner_id"], manager_id=session["manager_id"])


def require_session_role(session: dict, actor: Actor, role: str) -> None:
    """Role + ownership/assignment check on one session. Message texts match the
    long-standing service errors so existing contracts stay stable."""
    if actor.role != role:
        raise DomainError("forbidden", "Vai trò không được phép thực hiện thao tác này.", 403)
    owner = session["owner_id"] if role == "renter" else session["manager_id"]
    if owner != actor.id:
        raise DomainError("forbidden", "Bạn không có quyền xem phiên này.", 403)


def require(action: str, actor: Actor, resource: Resource | None = None) -> None:
    """Explicit capability gate: deny unknown actions, wrong roles and resources
    the actor does not own or is not assigned to. Never consults model output."""
    allowed = CAPABILITIES.get(action)
    if allowed is None:
        raise DomainError("unknown_action", "Thao tác không được hỗ trợ.", 422)
    if actor.role not in allowed:
        raise DomainError("forbidden", "Vai trò không được phép thực hiện thao tác này.", 403)
    if resource is None:
        return
    owner = resource.owner_id if actor.role == "renter" else resource.manager_id
    if owner != actor.id:
        raise DomainError("forbidden", "Bạn không có quyền xem phiên này.", 403)


def assert_unprivileged(payload: object) -> None:
    """Reject payloads (e.g. a graph resume command) that try to smuggle
    privilege fields. The only legitimate resume content is a ledger event id."""
    if isinstance(payload, dict) and PRIVILEGED_KEYS & set(payload):
        raise DomainError("untrusted_resume",
                          "Payload tiếp tục graph chứa trường đặc quyền; chỉ chấp nhận event_id từ sổ nghiệp vụ.", 403)
