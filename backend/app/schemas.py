"""Public response contracts. Internal ledger and graph fields stay private."""
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .models import Actor, Candidate, CostResult, DraftProfile, Model, Profile, Room


RunStatus = Literal["generating", "generation_failed", "published", "invalidated",
                    "no_match", "needs_verification"]


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
    # Reported input/output split (AG-03); null when the provider only reports a total.
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class MessageResult(SessionResult):
    intent: Literal["find_room", "calculate_cost", "simulate_finance", "human_support", "handbook", "unknown"]
    status: Literal["needs_clarification", "cost_estimate", "support_requested", "handbook_answer",
                    "simulation", "needs_results"]
    questions: list[str] | None = None
    interpreter_mode: str | None = None
    cost: CostResult | None = None
    # Loan what-if answered by the finance agent from a deterministic tool (AG-02):
    # {room_id, room_title, scenario:{annual_rate, term_months, principal_vnd}, result}.
    simulation: dict | None = None
    ticket_id: str | None = None
    message: str | None = None
    answers: list[dict] | None = None
    house_rules: list[str] | None = None
    disclaimer: str | None = None
    usage: Usage
    # AG-13: các bước tool vòng lặp agent đã chạy ("tool: mô tả", không PII) và
    # chế độ chạy ("loop" | "graph_fallback", chỉ có ở chế độ openai).
    steps: list[str] | None = None
    agent_mode: str | None = None
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
    # Aggregate hard-filter counts (scanned/kept/rejected/verification) cho ca
    # kho rỗng — chỉ số liệu tổng hợp, không chứa danh tính phòng nào.
    diagnostics_summary: dict | None = None
    # Các bước pipeline deterministic đã chạy thật của run này (minh bạch quy trình).
    steps: list[str] | None = None

    @model_validator(mode="after")
    def published_only(self):
        # Kết quả chỉ đi kèm run đã công bố (auto-publish, quyết định 05/11/2026).
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


class RoomWithMedia(Room):
    """Room DTO extended with the media fields the service attaches on read
    paths (BE-06/BE-07). Never accepted as catalog input, never stored:
    RoomInput/CatalogStatus payloads keep the canonical Room schema."""
    # Listing photos in display order: [{id, url}].
    photos: list[dict] | None = None
    # Active landlord promotion: {text, valid_until} or null when none/expired.
    promotion: dict | None = None


class CatalogResult(Model):
    rooms: list[RoomWithMedia]
    catalog_version: str
    shared_catalog: bool


class RoomResult(Model):
    room: RoomWithMedia
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
    status: Literal["requested", "in_progress", "resolved"]
    assignee: str | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class SupportUpdate(Model):
    # Any current status may be replayed (idempotent no-op); the lifecycle
    # itself is enforced by SUPPORT_TRANSITIONS in the service layer.
    status: Literal["requested", "in_progress", "resolved"]
    note: str | None = Field(default=None, max_length=2000)


class MediaResult(Model):
    # One photo of a listing or maintenance ticket; url is always /media/{id}.
    id: str
    url: str
    content_type: str
    size_bytes: int
    position: int


class PromotionResult(Model):
    room_id: str
    text: str
    valid_until: str


class HealthResult(Model):
    status: Literal["ok"]
    prototype: bool
    storage: Literal["sqlite", "postgresql"]
    auth_mode: Literal["seed", "demo"]
    matching_method: Literal["B1", "P"]
    workers: Literal[1]
    # public=true khi HOMEMATCH_PUBLIC=true; frontend dùng để tắt trải nghiệm
    # đăng nhập nhanh bằng tài khoản seed (chỉ dành cho môi trường demo local).
    public: bool


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


class CostMetric(Model):
    """Operator cost estimate for the reported token usage (BE-05).

    estimated_cost_vnd stays None when any needed price, fx rate or token
    split is missing; `missing` lists the offending keys.
    """

    estimated_cost_vnd: int | None
    price_effective_date: str | None
    missing: list[str] = Field(default_factory=list)
    basis: dict[str, dict[str, int]] = Field(default_factory=dict)


class MetricsResult(Model):
    scope: Literal["current_process"]
    requests: list[RequestMetric]
    generations: list[GenerationMetric]
    # Per-model usage lives under the nested "by_model" key (AG-03): a dict of
    # per-model counters, hence the two-level int|dict union.
    provider_usage: dict[str, int | dict[str, int | dict[str, int]]]
    semantic_usage: dict[str, int] = Field(default_factory=dict)
    # Null when HOMEMATCH_PROVIDER_PRICES_PATH is not configured.
    cost: CostMetric | None = None


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
    contact_phone: str | None = None
    consents: dict[str, bool]
    organizations: list[OrgMembershipSummary]


class SessionEntry(Model):
    token_id: str
    expires_at: datetime
    revoked: bool


class SessionRevokeResult(Model):
    status: Literal["revoked"]
