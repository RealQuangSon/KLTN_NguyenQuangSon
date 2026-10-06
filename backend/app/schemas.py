"""Public response contracts. Internal ledger and graph fields stay private."""
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .models import Actor, Candidate, CostResult, DraftProfile, Model, Profile, Review, Room


RunStatus = Literal["generating", "generation_failed", "pending_review", "partially_published", "reviewed",
                    "published", "invalidated", "no_match", "needs_verification",
                    "rejected", "needs_revision"]


class LoginResult(Model):
    access_token: str
    token_type: Literal["bearer"]
    expires_at: datetime
    actor: Actor


class LogoutResult(Model):
    status: Literal["logged_out"]


class SessionResult(Model):
    session_id: str
    draft_revision: int
    draft: DraftProfile
    profile_version: int
    confirmed_profile: Profile | None
    active_run_id: str | None


class DraftResult(SessionResult):
    status: Literal["needs_clarification"]
    questions: list[str]


class Usage(Model):
    logical_calls: int = Field(ge=0)
    tokens: int | None = Field(ge=0)
    mode: str
    model: str | None = None
    context_utf8_upper_bound: int | None = None


class MessageResult(SessionResult):
    intent: Literal["find_room", "calculate_cost", "human_support", "handbook", "unknown"]
    status: Literal["needs_clarification", "cost_estimate", "support_requested", "handbook_answer"]
    questions: list[str] | None = None
    interpreter_mode: str | None = None
    cost: CostResult | None = None
    ticket_id: str | None = None
    message: str | None = None
    answers: list[dict] | None = None
    house_rules: list[str] | None = None
    disclaimer: str | None = None
    usage: Usage
    # Where this turn's content came from (user/deterministic-engine/interpreter + node).
    provenance: dict | None = None
    # Injection/privacy screening outcome for the turn (flag, patterns, redactions).
    guard: dict | None = None


class ResultsResult(Model):
    session_id: str
    run_id: str | None = None
    status: RunStatus | Literal["awaiting_confirmation"]
    profile_version: int | None = None
    results: list[Candidate]
    # Soft, renter-driven relaxation next steps on no_match/needs_verification runs.
    suggestions: list[str] | None = None
    # Deterministic-engine provenance for the ranking read (catalog/method/run status).
    provenance: dict | None = None

    @model_validator(mode="after")
    def published_only(self):
        if self.status != "published" and self.results:
            raise ValueError("Unpublished recommendations cannot contain renter results")
        return self


class CompareResult(Model):
    run_id: str
    items: list[Candidate] = Field(min_length=2, max_length=3)
    # Deterministic pros/cons and a suggested pick within the confirmed budget.
    advice: dict | None = None


class SimulationItem(Model):
    label: str
    cost: CostResult


class SimulationResult(Model):
    run_id: str
    room_id: str
    room_revision: int
    items: list[SimulationItem] = Field(min_length=1, max_length=3)


class LocationArea(Model):
    name: str
    aliases: list[str]


class LocationCity(Model):
    name: str
    aliases: list[str]
    areas: list[LocationArea]


class LocationsResult(Model):
    cities: list[LocationCity]


class StoredMemory(Model):
    fields: dict
    source_session: str
    updated_at: str


class MemoryResult(Model):
    consented: bool
    memory: StoredMemory | None


class ForgetResult(Model):
    status: str
    field: str | None = None


class ListingSearchResult(Model):
    total: int
    page: int
    page_size: int
    items: list[dict]
    notice: str


class ReviewEvent(Model):
    event_id: str
    actor_id: str
    payload: Review
    keep_room_ids: list[str]
    # Absent on events recorded before override tracking existed.
    agent_order: list[str] | None = None
    overridden: bool | None = None
    recorded_at: datetime


class RecommendationResult(Model):
    run_id: str
    session_id: str
    status: RunStatus
    profile_version: int
    catalog_version: str
    profile: Profile
    items: list[Candidate]
    diagnostics: dict
    decision: ReviewEvent | None
    # How many landlords of this shortlist have decided so far.
    review_progress: dict | None = None


class CatalogResult(Model):
    rooms: list[Room]
    catalog_version: str
    shared_catalog: bool


class RoomResult(Model):
    room: Room
    catalog_version: str


class ViewingResult(Model):
    id: str
    session_id: str | None = None
    run_id: str | None = None
    room_id: str
    requested_at: datetime
    status: Literal["requested", "confirmed", "declined"]
    landlord_id: str | None = None
    mode: Literal["offline", "online"] = "offline"
    meeting_url: str | None = None


class SupportResult(Model):
    id: str
    session_id: str
    manager_id: str
    status: Literal["requested"]
    created_at: datetime


class HealthResult(Model):
    status: Literal["ok"]
    prototype: bool
    storage: Literal["sqlite", "postgresql"]
    auth_mode: Literal["seed", "demo"]
    matching_method: Literal["B1", "P"]
    workers: Literal[1]


class ReadyResult(Model):
    status: Literal["ready"]
    storage: Literal["sqlite", "postgresql"]
    schema_version: int
    checks: dict[str, Literal["ok"]]


class RequestMetric(Model):
    method: str
    route: str
    status: int
    count: int
    duration_seconds: float


class GenerationMetric(Model):
    status: str
    algorithm: str
    count: int
    duration_seconds: float


class MetricsResult(Model):
    scope: Literal["current_process"]
    requests: list[RequestMetric]
    generations: list[GenerationMetric]
    provider_usage: dict[str, int]
    semantic_usage: dict[str, int] = Field(default_factory=dict)


class ErrorField(Model):
    loc: list[str | int]
    type: str


class ErrorDetail(Model):
    code: str
    message: str
    fields: list[ErrorField] | None = None


class ErrorResult(Model):
    error: ErrorDetail
    request_id: str | None


# --- W-01/W-02/W-03 additions: organizations, memberships, account lifecycle ---

MembershipRole = Literal["owner", "manager", "admin"]
AccountStatus = Literal["unverified", "active", "disabled"]
OrgStatus = Literal["active", "suspended", "archived"]
MembershipStatus = Literal["active", "revoked"]


class OrganizationResult(Model):
    id: str
    name: str
    status: OrgStatus
    revision: int
    created_at: datetime
    updated_at: datetime
    # The caller's membership role in this organization; "admin" for global admins.
    actor_role: str | None = None


class MembershipResult(Model):
    id: str
    organization_id: str
    user_id: str
    role: MembershipRole
    status: MembershipStatus
    revision: int
    created_at: datetime
    updated_at: datetime


class RegisterResult(Model):
    status: Literal["pending_verification"]
    user: Actor
    delivery: Literal["dev_stub_log_only"]


class VerifyResult(Model):
    status: Literal["verified"]


class PasswordResetRequestResult(Model):
    # Identical for known, unknown, seed and disabled accounts.
    status: Literal["reset_requested"]


class PasswordResetConfirmResult(Model):
    status: Literal["password_reset"]


class OrgMembershipSummary(Model):
    organization_id: str
    name: str
    role: MembershipRole
    status: MembershipStatus


class ProfileResult(Model):
    id: str
    role: str
    display_name: str | None
    email: str | None
    email_verified: bool | None
    status: AccountStatus
    consents: dict[str, bool]
    organizations: list[OrgMembershipSummary]


class SessionEntry(Model):
    token_id: str
    expires_at: datetime
    revoked: bool


class SessionRevokeResult(Model):
    status: Literal["revoked"]
