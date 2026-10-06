from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DomainError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 409):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


# Four target roles (W-01). Renters are customers; owner/manager/admin are
# staff roles scoped by organization membership. The role always comes from
# the server-side account record, never from the client.
Role = Literal["renter", "owner", "manager", "admin"]
ORG_MEMBERSHIP_ROLES = ("owner", "manager", "admin")


class Actor(Model):
    id: str
    role: Role


class Destination(Model):
    label: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    uncertainty_m: float = Field(ge=0)
    max_distance_m: float = Field(gt=0)


class Scenario(Model):
    people: int = Field(default=1, ge=1, le=20, strict=True)
    vehicles: int = Field(default=1, ge=0, le=20, strict=True)
    electricity_kwh: Decimal = Field(default=Decimal("140"), ge=0)
    water_m3: Decimal = Field(default=Decimal("3"), ge=0)
    moving_vnd: int = Field(default=300_000, ge=0, strict=True)
    setup_vnd: int = Field(default=200_000, ge=0, strict=True)


class Fee(Model):
    name: str
    amount_vnd: Decimal | None = Field(default=None, ge=0)
    mode: Literal["fixed", "person", "vehicle", "kwh", "m3"] = "fixed"
    included_in_rent: bool = False
    source: str


class Quote(Model):
    rent_vnd: int = Field(ge=0, strict=True)
    deposit_vnd: int | None = Field(default=None, ge=0, strict=True)
    advance_months: int | None = Field(default=None, ge=1, le=24, strict=True)
    fees: list[Fee]
    one_time_vnd: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def unique_fees(self):
        names = [fee.name for fee in self.fees]
        if len(names) != len(set(names)):
            raise ValueError("Mỗi loại phí chỉ xuất hiện một lần trong quote.")
        return self


RoomType = Literal["room", "studio", "apartment"]
Occupancy = Literal["vacant", "deposited", "rented"]
# Rooms without an explicit landlord in legacy/demo data belong to this seed landlord.
DEFAULT_LANDLORD = "owner-a"


class Room(Model):
    id: str
    revision: int = Field(ge=1)
    title: str
    city: str
    area: str
    room_type: RoomType = "room"
    # Bedrooms only apply to apartments; null means unknown or not applicable.
    bedrooms: int | None = Field(default=None, ge=1, le=5)
    capacity: int | None = Field(default=None, ge=1)
    area_m2: float = Field(gt=0)
    published: bool
    available: bool | None
    amenities: dict[str, bool | None]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy: Literal["exact", "approximate", "area_only"] = "area_only"
    uncertainty_m: float | None = Field(default=None, ge=0)
    quote: Quote
    source: str
    synthetic: bool = True
    # Soft features (view, light, surroundings) for semantic matching; never money or contacts.
    features_text: str | None = Field(default=None, max_length=500)
    # Landlord account that owns the listing and reviews AI shortlists containing it.
    landlord_id: str | None = Field(default=None, max_length=64)
    # Leasing state shown to tenants; `available` stays the hard-filter flag.
    occupancy: Occupancy | None = None
    # Landlord's own rules (giờ giấc, gửi xe, cách tính điện nước) for the tenant handbook.
    house_rules: str | None = Field(default=None, max_length=2000)

    @property
    def landlord(self) -> str:
        return self.landlord_id or DEFAULT_LANDLORD


FieldStatus = Literal["unknown", "inferred", "confirmed"]
DRAFT_TRACKED_FIELDS = ("city", "area", "people", "preferences", "room_type", "bedrooms",
                        "needs_destination", "soft_description", "budget_hint")


class DraftProfile(Model):
    city: str | None = None
    area: str | None = None
    monthly_budget_vnd: int | None = Field(default=None, gt=0, strict=True)
    budget_hint_vnd: int | None = Field(default=None, gt=0, strict=True)
    people: int | None = Field(default=None, ge=1, le=20, strict=True)
    preferences: list[str] = Field(default_factory=list)
    needs_destination: bool = False
    room_type: RoomType | None = None
    bedrooms: int | None = Field(default=None, ge=1, le=5, strict=True)
    soft_description: str | None = Field(default=None, max_length=1000)
    # Provenance per tracked field: inferred from chat, confirmed via form, unknown.
    field_status: dict[str, FieldStatus] = Field(default_factory=dict)
    evidence_ref: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def tracked_field_keys(self):
        allowed = set(DRAFT_TRACKED_FIELDS)
        for mapping in (self.field_status, self.evidence_ref):
            unknown = set(mapping) - allowed
            if unknown:
                raise ValueError(f"Trường không được theo dõi trạng thái: {sorted(unknown)}")
        return self


class LoanTerms(Model):
    """Short-term loan scenario the renter enters for a move-in cash shortfall."""
    annual_rate: Decimal = Field(ge=0, le=1)
    term_months: int = Field(ge=1, le=36, strict=True)
    max_principal_vnd: int | None = Field(default=None, gt=0, strict=True)


class Profile(Model):
    city: str = Field(min_length=2, max_length=64)
    area: str | None = Field(default=None, max_length=64)
    room_type: RoomType = "room"
    min_bedrooms: int | None = Field(default=None, ge=1, le=5, strict=True)
    max_monthly_cost_vnd: int = Field(gt=0, strict=True)
    max_rent_vnd: int | None = Field(default=None, gt=0, strict=True)
    # Cash on hand for moving in; with `loan` set, a shortfall may be borrowed.
    max_initial_cash_vnd: int | None = Field(default=None, ge=0, strict=True)
    monthly_income_vnd: int | None = Field(default=None, gt=0, strict=True)
    cost_split: Literal["none", "equal"] = "none"
    loan: LoanTerms | None = None
    must_amenities: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    scenario: Scenario
    destination: Destination | None = None
    soft_description: str | None = Field(default=None, max_length=1000)


class CostLine(Model):
    name: str
    period: Literal["monthly", "initial"]
    amount_vnd: int | None
    source: str
    included_in_rent: bool = False


AffordabilityBand = Literal["phu_hop", "can_nhac", "vuot", "chua_ro"]


class LoanEstimate(Model):
    principal_vnd: int
    installment_vnd: int
    total_interest_vnd: int
    term_months: int
    annual_rate: Decimal
    method: Literal["annuity"] = "annuity"
    exceeds_max_principal: bool = False


class Affordability(Model):
    shortfall_vnd: int | None
    loan: LoanEstimate | None
    # Household monthly total plus the loan instalment while the loan runs.
    burden_vnd: int | None
    # The renter's own share after an equal split between occupants.
    renter_burden_vnd: int | None
    # Withheld (null) in the manager projection so income cannot be back-computed.
    housing_ratio: Decimal | None
    band: AffordabilityBand
    thresholds: dict[str, Decimal]


class CostResult(Model):
    monthly_known_vnd: int
    monthly_total_vnd: int | None
    initial_known_vnd: int
    initial_total_vnd: int | None
    missing_monthly: list[str]
    missing_initial: list[str]
    lines: list[CostLine]
    assumptions: dict
    affordability: Affordability | None = None


class Candidate(Model):
    room_id: str
    room_revision: int
    title: str
    city: str
    area: str
    area_m2: float
    room_type: RoomType = "room"
    bedrooms: int | None = None
    landlord_id: str | None = None
    cost: CostResult
    score: float
    components: dict[str, float]
    reasons: list[str]
    tradeoffs: list[str]
    source: str
    synthetic: bool
    algorithm: str = "structured_baseline_v1"
    # Data-quality flags of the underlying listing; they never block eligibility,
    # they tell renter/manager which evidence still needs human verification.
    verification: list[str] = Field(default_factory=list)


class Extraction(Model):
    # Required nullable fields make the OpenAI output schema explicit.
    intent: Literal["find_room", "calculate_cost", "human_support", "unknown"]
    city: str | None
    area: str | None
    room_type: RoomType | None = None
    bedrooms: int | None = Field(default=None, ge=1, le=5)
    people: int | None = Field(ge=1, le=20)
    preferences: list[str]
    needs_destination: bool
    remove_preferences: list[str] = Field(default_factory=list)
    soft_description: str | None = Field(default=None, max_length=1000)


class Review(Model):
    decision: Literal["approve", "reject", "needs_revision"]
    expected_profile_version: int = Field(ge=1, strict=True)
    keep_room_ids: list[str] | None = None
    reason: str = Field(min_length=1, max_length=1000)
    # Required when the kept set or order differs from the agent's ranking (no favouring stock).
    override_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=100)


class ConfirmRequest(Model):
    expected_draft_revision: int = Field(ge=0, strict=True)
    profile: Profile


class AffordabilityInput(Model):
    available_cash_vnd: int | None = Field(default=None, ge=0, strict=True)
    monthly_income_vnd: int | None = Field(default=None, gt=0, strict=True)
    cost_split: Literal["none", "equal"] = "none"
    loan: LoanTerms | None = None


class CostRequest(Model):
    quote: Quote
    scenario: Scenario
    affordability: AffordabilityInput | None = None


class SimulationScenario(Model):
    """One what-if for a published room; omitted fields fall back to the confirmed profile."""
    label: str = Field(min_length=1, max_length=60)
    scenario: Scenario | None = None
    cost_split: Literal["none", "equal"] | None = None
    # Explicit null means "no loan"; leaving the field out keeps the profile's loan.
    loan: LoanTerms | None = None


class SimulationRequest(Model):
    room_id: str = Field(min_length=1, max_length=100)
    scenarios: list[SimulationScenario] = Field(min_length=1, max_length=3)


class DraftPatch(Model):
    expected_draft_revision: int = Field(ge=0, strict=True)
    set: dict = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)
    remove_preferences: list[str] = Field(default_factory=list)


class CatalogStatus(Model):
    expected_revision: int = Field(ge=1, strict=True)
    published: bool | None = None
    available: bool | None = None
    occupancy: Occupancy | None = None


class RoomInput(Model):
    """Landlord-editable listing fields; id, revision, landlord and source are server-set."""
    title: str = Field(min_length=3, max_length=300)
    city: str = Field(min_length=2, max_length=64)
    area: str = Field(min_length=2, max_length=64)
    room_type: RoomType = "room"
    bedrooms: int | None = Field(default=None, ge=1, le=5)
    capacity: int | None = Field(default=None, ge=1, le=20)
    area_m2: float = Field(gt=0, le=1000)
    published: bool = False
    available: bool | None = None
    occupancy: Occupancy | None = None
    amenities: dict[str, bool | None] = Field(default_factory=dict)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy: Literal["exact", "approximate", "area_only"] = "area_only"
    uncertainty_m: float | None = Field(default=None, ge=0)
    quote: Quote
    features_text: str | None = Field(default=None, max_length=500)
    house_rules: str | None = Field(default=None, max_length=2000)


class RoomUpdate(RoomInput):
    expected_revision: int = Field(ge=1, strict=True)


class OrganizationCreate(Model):
    name: str = Field(min_length=2, max_length=120)


class MembershipGrant(Model):
    user_id: str = Field(min_length=1, max_length=100)
    role: Literal["owner", "manager", "admin"]


class RegisterRequest(Model):
    # Registration always creates a renter account; staff roles are granted
    # through organization memberships by an admin, never chosen by the client.
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=10, max_length=200)
    email: str = Field(min_length=5, max_length=200)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class VerifyRequest(Model):
    username: str = Field(min_length=1, max_length=100)
    token: str = Field(min_length=10, max_length=200)


class PasswordResetRequest(Model):
    username: str = Field(min_length=1, max_length=100)


class PasswordResetConfirm(Model):
    username: str = Field(min_length=1, max_length=100)
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class ProfilePatch(Model):
    # role/organization are deliberately absent: a profile patch can never
    # change the actor's role or organization (extra="forbid" rejects them).
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=5, max_length=200)
    consents: dict[str, bool] | None = None
