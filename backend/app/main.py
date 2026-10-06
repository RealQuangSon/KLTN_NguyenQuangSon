from contextlib import asynccontextmanager
from datetime import datetime
import os
import logging
import threading
import time
from typing import Annotated, Callable, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from pydantic import Field

from .costs import estimate_cost
from .locations import AREA_ALIASES, CITY_ALIASES
from .listings import ListingQuery
from .models import (Actor, CatalogStatus, ConfirmRequest, CostRequest, CostResult, DomainError,
                     DraftPatch, MembershipGrant, Model, OrganizationCreate, ProfilePatch,
                     RegisterRequest, Review, RoomInput, RoomUpdate, SimulationRequest, VerifyRequest, PasswordResetRequest,
                     PasswordResetConfirm)
from . import memory, organizations, pms
from .auth import (SEED_USERS, DevDeliveryStub, SeedAuth, account_profile, confirm_password_reset,
                   list_sessions, register_account, request_password_reset, revoke_session,
                   update_account_profile, verify_account)
from .service import HomeMatchService
from .auth import SEED_USERS, DevDeliveryStub, SeedAuth
from .migrations import SCHEMA_VERSION, schema_version
from .schemas import (CatalogResult, CompareResult, DraftResult, ErrorResult, HealthResult,
                      ForgetResult, ListingSearchResult, LocationsResult, LoginResult, MemoryResult, LogoutResult, MembershipResult, MessageResult, MetricsResult,
                      OrganizationResult, PasswordResetConfirmResult, PasswordResetRequestResult,
                      ProfileResult, ReadyResult, RecommendationResult, RegisterResult,
                      ResultsResult, RoomResult, SessionEntry, SessionRevokeResult, SessionResult,
                      SimulationResult, SupportResult, VerifyResult, ViewingResult)

logger = logging.getLogger("homematch.api")

# Demo credentials, deliberately published for localhost Swagger walkthroughs.
# Explicit localhost demonstration mode; normal mode uses seeded opaque-token auth.
DEMO_TOKENS = {
    "demo-renter-a": Actor(id="renter-a", role="renter"),
    "demo-renter-b": Actor(id="renter-b", role="renter"),
    "demo-owner-a": Actor(id="owner-a", role="owner"),
    "demo-owner-b": Actor(id="owner-b", role="owner"),
    "demo-manager-a": Actor(id="manager-a", role="manager"),
    "demo-manager-b": Actor(id="manager-b", role="manager"),
    "demo-admin-a": Actor(id="admin-a", role="admin"),
}
bearer = HTTPBearer(auto_error=False)


def require_delivery_available(request: Request):
    """Verification delivery is a dev stub; in public mode it must not pretend."""
    if getattr(request.app.state, "public", False):
        raise DomainError("delivery_unavailable",
                          "Chưa tích hợp nhà cung cấp email; tính năng xác minh đang tắt.", 503)


class LoginRequest(Model):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class MessageRequest(Model):
    text: str = Field(min_length=1, max_length=2000)
    cost_input: CostRequest | None = None


class CompareRequest(Model):
    room_ids: list[str] = Field(min_length=2, max_length=3)


class ViewingRequest(Model):
    room_id: str
    requested_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=100)
    mode: Literal["offline", "online"] = "offline"


class ListingCompareRequest(Model):
    room_ids: list[str] = Field(min_length=2, max_length=3)
    people: int = Field(default=1, ge=1, le=20)
    budget: int | None = Field(default=None, ge=0)
    preferences: list[str] = Field(default_factory=list, max_length=9)


class ListingViewingRequest(Model):
    requested_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=100)
    mode: Literal["offline", "online"] = "offline"


class MarketingRequest(Model):
    channel: Literal["facebook", "zalo", "forum"]


class AssistantQuestion(Model):
    question: str = Field(min_length=1, max_length=1000)


class LeaseAcceptance(Model):
    expected_version: int = Field(ge=1)


class ConversationStart(Model):
    room_id: str = Field(min_length=1, max_length=100)
    session_id: str | None = Field(default=None, max_length=100)


class ConversationMessage(Model):
    body: str = Field(min_length=1, max_length=2000)


class HandbookQuestion(Model):
    question: str = Field(min_length=1, max_length=1000)
    room_id: str | None = Field(default=None, max_length=100)


class ViewingResponse(Model):
    status: Literal["confirmed", "declined"]


def create_app(service_factory: Callable[[], HomeMatchService] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.auth_mode = os.getenv("HOMEMATCH_AUTH_MODE", "seed")
        if app.state.auth_mode not in {"seed", "demo"}:
            raise ValueError("HOMEMATCH_AUTH_MODE must be seed or demo")
        public_value = os.getenv("HOMEMATCH_PUBLIC", "false").lower()
        if public_value not in {"true", "false"}:
            raise ValueError("HOMEMATCH_PUBLIC must be true or false")
        public = public_value == "true"
        storage = os.getenv("HOMEMATCH_DATABASE_URL") or os.getenv("HOMEMATCH_DB_PATH", ".local/homematch.sqlite")
        if public:
            configured = all(len(os.getenv("HOMEMATCH_PASSWORD_" + username.upper().replace("-", "_"), "")) >= 16
                             and os.getenv("HOMEMATCH_PASSWORD_" + username.upper().replace("-", "_")) != f"local-{username}-password"
                             for username, _ in SEED_USERS)
            if app.state.auth_mode != "seed" or not storage.startswith(("postgresql://", "postgres://")) or not configured:
                raise ValueError("Public mode requires PostgreSQL, seed auth and explicit seed credentials")
            if "*" in os.getenv("HOMEMATCH_CORS_ORIGINS", ""):
                raise ValueError("Public mode requires explicit CORS origins")
        ttl = int(os.getenv("HOMEMATCH_TOKEN_TTL_SECONDS", "3600"))
        if not 60 <= ttl <= 86400:
            raise ValueError("Token TTL must be between 60 and 86400 seconds")
        app.state.service = (service_factory or (lambda: HomeMatchService(
            storage)))()
        try:
            app.state.public = public
            app.state.delivery = DevDeliveryStub()
            app.state.auth = SeedAuth(app.state.service.repo, app.state.service.lock,
                                      ttl, public=public)
            # Automation engine: reminders, lead re-engagement, retention purge. 0 disables the thread.
            interval = int(os.getenv("HOMEMATCH_JOBS_INTERVAL_SECONDS", "300"))
            stop = threading.Event()
            worker = None
            if interval > 0:
                def loop():
                    while not stop.wait(interval):
                        try:
                            app.state.service.run_jobs()
                        except Exception:
                            logger.exception("automation_jobs_failed")
                worker = threading.Thread(target=loop, name="homematch-jobs", daemon=True)
                worker.start()
            yield
        finally:
            if "stop" in locals():
                stop.set()
                if worker is not None:
                    worker.join(timeout=5)
            app.state.service.close()

    errors = {status: {"model": ErrorResult} for status in (401, 403, 404, 405, 409, 422, 500, 503)}
    app = FastAPI(title="HomeMatch phòng trọ – MVP prototype", version="0.4.0", lifespan=lifespan,
                  responses=errors)
    origins = os.getenv("HOMEMATCH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        local_peers = {"127.0.0.1", "::1"}
        if service_factory is not None:
            local_peers.add("testclient")  # In-process fixtures, never trusted from HTTP headers.
        peer = request.client.host if request.client else None
        if getattr(app.state, "auth_mode", None) == "demo" and (
            peer not in local_peers or request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}
        ):
            response = JSONResponse(status_code=403, content={"error": {"code": "demo_local_only", "message": "Demo token chỉ dùng localhost."},
                "request_id": request.state.request_id})
        else:
            try:
                response = await call_next(request)
            except Exception:
                response = await unexpected_error(request, None)
        elapsed = time.monotonic() - start
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Server-Timing"] = f"app;dur={elapsed * 1000:.1f}"
        route = getattr(request.scope.get("route"), "path", "<unmatched>")
        method = request.method if request.method in {"GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
        if hasattr(app.state, "service"):
            app.state.service.metrics.request(method, route, response.status_code, elapsed)
        logger.info("request_id=%s method=%s route=%s status=%d duration_ms=%.1f",
                    request.state.request_id, method, route, response.status_code, elapsed * 1000)
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.http_status, content={"error": {"code": exc.code, "message": str(exc)},
                            "request_id": getattr(request.state, "request_id", None)},
                            headers={"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code, message = {404: ("not_found", "Không tìm thấy tài nguyên."),
                         405: ("method_not_allowed", "Phương thức không được hỗ trợ.")}.get(
                             exc.status_code, ("http_error", "Không thể hoàn tất yêu cầu."))
        return JSONResponse(status_code=exc.status_code, headers=exc.headers,
                            content={"error": {"code": code, "message": message},
                                     "request_id": request.state.request_id})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Dữ liệu đầu vào chưa hợp lệ.",
            "fields": [{"loc": list(item["loc"]), "type": item["type"]} for item in exc.errors()]},
            "request_id": getattr(request.state, "request_id", None)})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Không thể hoàn tất yêu cầu."},
            "request_id": getattr(request.state, "request_id", None)})

    def current_actor(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Actor:
        if credentials is None:
            raise DomainError("unauthorized", "Cần đăng nhập để thực hiện thao tác này.", 401)
        if request.app.state.auth_mode == "demo":
            actor = DEMO_TOKENS.get(credentials.credentials)
            if actor is None:
                raise DomainError("unauthorized", "Token demo không hợp lệ.", 401)
            return actor
        return request.app.state.auth.actor(credentials.credentials)

    def service(request: Request) -> HomeMatchService:
        return request.app.state.service

    def optional_actor(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
                       ) -> Actor | None:
        # Public pages work anonymously; a valid token only attributes the view to the renter.
        if credentials is None:
            return None
        try:
            return current_actor(request, credentials)
        except DomainError:
            return None

    ActorDep = Annotated[Actor, Depends(current_actor)]
    OptionalActorDep = Annotated[Actor | None, Depends(optional_actor)]
    ServiceDep = Annotated[HomeMatchService, Depends(service)]

    @app.get("/health", response_model=HealthResult)
    def health():
        try:
            with app.state.service.lock:
                app.state.service.repo.db.execute("SELECT 1").fetchone()
        except Exception:
            raise DomainError("storage_unavailable", "Kho dữ liệu tạm thời không khả dụng.", 503) from None
        return {"status": "ok", "prototype": True, "storage": "postgresql" if app.state.service.repo.db.postgres else "sqlite",
                "auth_mode": app.state.auth_mode, "matching_method": app.state.service.matching_method, "workers": 1}

    @app.get("/ready", response_model=ReadyResult)
    def ready():
        agent = app.state.service
        try:
            with agent.lock:
                if schema_version(agent.repo.db) != SCHEMA_VERSION or not agent.catalog.version:
                    raise ValueError("Schema or catalog is not ready")
                agent.checkpoint_connection.execute("SELECT 1 FROM checkpoints LIMIT 1").fetchone()
        except Exception:
            raise DomainError("not_ready", "Backend chưa sẵn sàng; cần kiểm tra dữ liệu và checkpoint.", 503) from None
        return {"status": "ready", "storage": "postgresql" if agent.repo.db.postgres else "sqlite",
                "schema_version": SCHEMA_VERSION, "checks": {"ledger": "ok", "catalog": "ok", "checkpoints": "ok"}}

    @app.get("/admin/metrics", response_model=MetricsResult)
    def metrics(actor: ActorDep, agent: ServiceDep):
        agent._role(actor, "admin")
        return agent.metrics.snapshot()

    @app.post("/auth/login", response_model=LoginResult)
    def login(body: LoginRequest):
        return app.state.auth.login(body.username, body.password)

    @app.get("/auth/me", response_model=Actor)
    def me(actor: ActorDep):
        return actor

    @app.post("/auth/logout", response_model=LogoutResult)
    def logout(actor: ActorDep, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if credentials is not None:
            app.state.auth.logout(credentials.credentials)
        return {"status": "logged_out"}

    @app.post("/sessions", status_code=201, response_model=SessionResult)
    def create_session(actor: ActorDep, agent: ServiceDep):
        return agent.create_session(actor)

    @app.get("/sessions/{session_id}", response_model=SessionResult)
    def get_session(session_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.session(session_id, actor)

    @app.patch("/sessions/{session_id}/draft", response_model=DraftResult)
    def patch_draft(session_id: str, body: DraftPatch, actor: ActorDep, agent: ServiceDep):
        return agent.patch_draft(session_id, actor, body)

    @app.post("/sessions/{session_id}/messages", response_model=MessageResult, response_model_exclude_unset=True)
    def message(session_id: str, body: MessageRequest, actor: ActorDep, agent: ServiceDep):
        return agent.message(session_id, actor, body.text, body.cost_input)

    @app.post("/sessions/{session_id}/confirm", response_model=ResultsResult, response_model_exclude_unset=True)
    def confirm(session_id: str, body: ConfirmRequest, actor: ActorDep, agent: ServiceDep):
        return agent.confirm(session_id, actor, body.profile, body.expected_draft_revision)

    @app.get("/sessions/{session_id}/results", response_model=ResultsResult, response_model_exclude_unset=True)
    def results(session_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.results(session_id, actor)

    @app.post("/sessions/{session_id}/compare", response_model=CompareResult)
    def compare(session_id: str, body: CompareRequest, actor: ActorDep, agent: ServiceDep):
        return agent.compare(session_id, actor, body.room_ids)

    @app.post("/costs/estimate", response_model=CostResult)
    def cost(body: CostRequest, actor: ActorDep):
        return estimate_cost(body)

    @app.get("/locations", response_model=LocationsResult)
    def locations():
        return {"cities": [{"name": city, "aliases": list(CITY_ALIASES[city]),
                            "areas": [{"name": area, "aliases": list(aliases)}
                                      for area, aliases in AREA_ALIASES[city].items()]}
                           for city in CITY_ALIASES]}

    # --- Tenant portal: public filter search, listing detail/compare, direct viewing, handbook ---

    @app.get("/listings", response_model=ListingSearchResult)
    def search_listings(agent: ServiceDep, query: Annotated[ListingQuery, Query()]):
        return agent.search_listings(query)

    @app.get("/listings/{room_id}", response_model=dict)
    def listing_detail(room_id: str, agent: ServiceDep, actor: OptionalActorDep, people: int = 1):
        if not 1 <= people <= 20:
            raise DomainError("invalid_request", "Số người từ 1 đến 20.", 422)
        return agent.listing(room_id, actor, people)

    @app.post("/listings/compare", response_model=dict)
    def compare_listings(body: ListingCompareRequest, agent: ServiceDep):
        return agent.compare_listings(body.room_ids, body.people, body.budget, body.preferences)

    @app.post("/listings/{room_id}/viewings", status_code=201, response_model=ViewingResult)
    def listing_viewing(room_id: str, body: ListingViewingRequest, actor: ActorDep, agent: ServiceDep):
        return agent.request_listing_viewing(actor, room_id, body.requested_at, body.idempotency_key, body.mode)

    @app.get("/handbook", response_model=list[dict])
    def handbook_entries():
        from .handbook import entries
        return entries()

    @app.post("/handbook/ask", response_model=dict)
    def handbook_ask(body: HandbookQuestion, agent: ServiceDep):
        return agent.handbook_answer(body.question, body.room_id)

    @app.post("/sessions/{session_id}/simulate", response_model=SimulationResult)
    def simulate(session_id: str, body: SimulationRequest, actor: ActorDep, agent: ServiceDep):
        return agent.simulate(session_id, actor, body)

    # --- Landlord portal: per-landlord review of AI shortlists and own listings ---

    @app.get("/landlord/recommendations", response_model=list[RecommendationResult])
    def drafts(actor: ActorDep, agent: ServiceDep):
        return agent.drafts(actor)

    @app.get("/landlord/recommendations/{run_id}", response_model=RecommendationResult)
    def draft(run_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.draft(run_id, actor)

    @app.post("/landlord/recommendations/{run_id}/review", response_model=RecommendationResult)
    def review(run_id: str, body: Review, actor: ActorDep, agent: ServiceDep):
        return agent.review(run_id, actor, body)

    @app.post("/landlord/recommendations/{run_id}/retry", response_model=RecommendationResult)
    def retry(run_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.retry(run_id, actor)

    @app.get("/landlord/rooms", response_model=CatalogResult)
    def rooms(actor: ActorDep, agent: ServiceDep):
        return agent.rooms(actor)

    @app.post("/landlord/rooms", status_code=201, response_model=RoomResult)
    def create_room(body: RoomInput, actor: ActorDep, agent: ServiceDep):
        return agent.create_room(actor, body)

    @app.get("/landlord/rooms/{room_id}", response_model=RoomResult)
    def room(room_id: str, actor: ActorDep, agent: ServiceDep):
        catalog = agent.rooms(actor)
        found = next((room for room in catalog["rooms"] if room["id"] == room_id), None)
        if found is None:
            raise DomainError("not_found", "Không tìm thấy phòng.", 404)
        return {"room": found, "catalog_version": catalog["catalog_version"]}

    @app.put("/landlord/rooms/{room_id}", response_model=RoomResult)
    def update_room(room_id: str, body: RoomUpdate, actor: ActorDep, agent: ServiceDep):
        return agent.update_room(room_id, actor, body)

    @app.patch("/landlord/rooms/{room_id}/status", response_model=RoomResult)
    def room_status(room_id: str, body: CatalogStatus, actor: ActorDep, agent: ServiceDep):
        return agent.change_room_status(room_id, actor, body)

    @app.post("/landlord/viewings/{viewing_id}/respond", response_model=ViewingResult)
    def respond_viewing(viewing_id: str, body: ViewingResponse, actor: ActorDep, agent: ServiceDep):
        return agent.respond_viewing(viewing_id, actor, body.status)

    # --- Live chat and smart handover ---

    @app.post("/conversations", status_code=201, response_model=dict)
    def start_conversation(body: ConversationStart, actor: ActorDep, agent: ServiceDep):
        return agent.start_conversation(actor, body.room_id, body.session_id)

    @app.get("/conversations", response_model=list[dict])
    def list_conversations(actor: ActorDep, agent: ServiceDep):
        return agent.conversations(actor)

    @app.get("/conversations/{conversation_id}/messages", response_model=dict)
    def conversation_messages(conversation_id: str, actor: ActorDep, agent: ServiceDep, after: str | None = None):
        return agent.conversation_messages(actor, conversation_id, after)

    @app.post("/conversations/{conversation_id}/messages", status_code=201, response_model=dict)
    def send_message(conversation_id: str, body: ConversationMessage, actor: ActorDep, agent: ServiceDep):
        return agent.send_conversation_message(actor, conversation_id, body.body)

    # --- Landlord PMS & CRM (leases, billing, maintenance, leads, dashboard) ---

    @app.get("/landlord/dashboard", response_model=dict)
    def landlord_dashboard(actor: ActorDep, agent: ServiceDep):
        return agent.landlord_dashboard(actor)

    @app.get("/landlord/analytics", response_model=dict)
    def landlord_analytics(actor: ActorDep, agent: ServiceDep):
        return agent.landlord_analytics(actor)

    @app.post("/landlord/leases", status_code=201, response_model=dict)
    def create_lease(body: pms.LeaseInput, actor: ActorDep, agent: ServiceDep):
        return agent.create_lease(actor, body)

    @app.put("/landlord/leases/{lease_id}", response_model=dict)
    def update_lease(lease_id: str, body: pms.LeaseInput, actor: ActorDep, agent: ServiceDep):
        return agent.update_lease(actor, lease_id, body)

    @app.post("/landlord/leases/{lease_id}/send", response_model=dict)
    def send_lease(lease_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.send_lease(actor, lease_id)

    @app.post("/landlord/leases/{lease_id}/activate", response_model=dict)
    def activate_lease(lease_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.activate_lease(actor, lease_id)

    @app.post("/landlord/leases/{lease_id}/renew", status_code=201, response_model=dict)
    def renew_lease(lease_id: str, body: pms.LeaseRenewal, actor: ActorDep, agent: ServiceDep):
        return agent.renew_lease(actor, lease_id, body)

    @app.post("/landlord/leases/{lease_id}/terminate", response_model=dict)
    def terminate_lease(lease_id: str, body: pms.LeaseTermination, actor: ActorDep, agent: ServiceDep):
        return agent.terminate_lease(actor, lease_id, body)

    @app.post("/landlord/leases/{lease_id}/readings", status_code=201, response_model=dict)
    def record_reading(lease_id: str, body: pms.ReadingInput, actor: ActorDep, agent: ServiceDep):
        return agent.record_reading(actor, lease_id, body)

    @app.post("/landlord/leases/{lease_id}/invoices", status_code=201, response_model=dict)
    def issue_invoice(lease_id: str, body: pms.InvoiceInput, actor: ActorDep, agent: ServiceDep):
        return agent.issue_invoice(actor, lease_id, body)

    @app.get("/landlord/billing/summary", response_model=dict)
    def billing_summary(actor: ActorDep, agent: ServiceDep):
        return agent.billing_summary(actor)

    @app.post("/landlord/invoices/{invoice_id}/payments", status_code=201, response_model=dict)
    def record_payment(invoice_id: str, body: pms.PaymentInput, actor: ActorDep, agent: ServiceDep):
        return agent.record_payment(actor, invoice_id, body)

    @app.post("/landlord/payment-claims/{claim_id}/{decision}", response_model=dict)
    def decide_claim(claim_id: str, decision: Literal["confirm", "reject"], actor: ActorDep, agent: ServiceDep):
        return agent.decide_claim(actor, claim_id, decision == "confirm")

    @app.get("/landlord/leads", response_model=list[dict])
    def leads(actor: ActorDep, agent: ServiceDep):
        return agent.leads(actor)

    @app.patch("/landlord/leads/{lead_id}", response_model=dict)
    def update_lead(lead_id: str, body: pms.LeadUpdate, actor: ActorDep, agent: ServiceDep):
        return agent.update_lead(actor, lead_id, body)

    @app.post("/landlord/rooms/{room_id}/marketing", response_model=dict)
    def marketing_post(room_id: str, body: MarketingRequest, actor: ActorDep, agent: ServiceDep):
        return agent.marketing_post(actor, room_id, body.channel)

    @app.get("/landlord/rooms/{room_id}/price-advice", response_model=dict)
    def price_advice(room_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.price_advice(actor, room_id)

    @app.post("/landlord/assistant", response_model=dict)
    def landlord_assistant(body: AssistantQuestion, actor: ActorDep, agent: ServiceDep):
        return agent.landlord_assistant(actor, body.question)

    @app.get("/leases", response_model=list[dict])
    def list_leases(actor: ActorDep, agent: ServiceDep):
        return agent.leases(actor)

    @app.get("/leases/{lease_id}", response_model=dict)
    def get_lease(lease_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.lease(actor, lease_id)

    @app.get("/leases/{lease_id}/document", response_model=dict)
    def lease_document(lease_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.lease_document(actor, lease_id)

    @app.post("/leases/{lease_id}/accept", response_model=dict)
    def accept_lease(lease_id: str, body: LeaseAcceptance, actor: ActorDep, agent: ServiceDep):
        return agent.accept_lease(actor, lease_id, body.expected_version)

    @app.get("/invoices", response_model=list[dict])
    def list_invoices(actor: ActorDep, agent: ServiceDep):
        return agent.invoices(actor)

    @app.get("/invoices/{invoice_id}", response_model=dict)
    def get_invoice(invoice_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.invoice_detail(actor, invoice_id)

    @app.get("/invoices/{invoice_id}/document", response_model=dict)
    def invoice_document(invoice_id: str, actor: ActorDep, agent: ServiceDep, receipt_no: str | None = None):
        return agent.invoice_document(actor, invoice_id, receipt_no)

    @app.post("/invoices/{invoice_id}/claims", status_code=201, response_model=dict)
    def claim_payment(invoice_id: str, body: pms.ClaimInput, actor: ActorDep, agent: ServiceDep):
        return agent.claim_payment(actor, invoice_id, body)

    @app.get("/payment-claims", response_model=list[dict])
    def payment_claims(actor: ActorDep, agent: ServiceDep):
        return agent.payment_claims(actor)

    @app.get("/maintenance", response_model=list[dict])
    def maintenance(actor: ActorDep, agent: ServiceDep):
        return agent.tickets(actor)

    @app.post("/maintenance", status_code=201, response_model=dict)
    def create_ticket(body: pms.TicketInput, actor: ActorDep, agent: ServiceDep):
        return agent.create_ticket(actor, body)

    @app.patch("/maintenance/{ticket_id}", response_model=dict)
    def update_ticket(ticket_id: str, body: pms.TicketUpdate, actor: ActorDep, agent: ServiceDep):
        return agent.update_ticket(actor, ticket_id, body)

    # --- Notifications and automation ---

    @app.get("/notifications", response_model=dict)
    def notifications(actor: ActorDep, agent: ServiceDep):
        return agent.notifications(actor)

    @app.post("/notifications/read", response_model=dict)
    def read_all_notifications(actor: ActorDep, agent: ServiceDep):
        return agent.read_notifications(actor)

    @app.post("/notifications/{notification_id}/read", response_model=dict)
    def read_notification(notification_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.read_notifications(actor, notification_id)

    @app.post("/admin/jobs/run", response_model=dict)
    def run_jobs(actor: ActorDep, agent: ServiceDep):
        agent._role(actor, "admin")
        return agent.run_jobs()

    @app.get("/admin/jobs", response_model=list[dict])
    def job_runs(actor: ActorDep, agent: ServiceDep):
        return agent.job_runs(actor)

    # --- Admin console ---

    @app.get("/admin/transcripts", response_model=list[dict])
    def admin_transcripts(actor: ActorDep, agent: ServiceDep):
        return agent.admin_transcripts(actor)

    @app.get("/admin/transcripts/{session_id}", response_model=dict)
    def admin_transcript(session_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.admin_transcript(actor, session_id)

    @app.get("/admin/handovers", response_model=dict)
    def admin_handovers(actor: ActorDep, agent: ServiceDep):
        return agent.admin_handovers(actor)

    @app.get("/admin/users", response_model=list[dict])
    def admin_users(actor: ActorDep, agent: ServiceDep):
        return agent.admin_users(actor)

    @app.patch("/admin/rooms/{room_id}/status", response_model=RoomResult)
    def admin_room_status(room_id: str, body: CatalogStatus, actor: ActorDep, agent: ServiceDep):
        agent._role(actor, "admin")
        return agent.change_room_status(room_id, actor, body)

    @app.get("/admin/rooms", response_model=CatalogResult)
    def admin_rooms(actor: ActorDep, agent: ServiceDep):
        agent._role(actor, "admin")
        return agent.rooms(actor)

    @app.get("/admin/failed-runs", response_model=list[RecommendationResult])
    def failed_runs(actor: ActorDep, agent: ServiceDep):
        return agent.failed_runs(actor)

    @app.post("/sessions/{session_id}/viewings", status_code=201, response_model=ViewingResult)
    def request_viewing(session_id: str, body: ViewingRequest, actor: ActorDep, agent: ServiceDep):
        return agent.request_viewing(session_id, actor, body.room_id, body.requested_at, body.idempotency_key,
                                     body.mode)

    @app.get("/viewings", response_model=list[ViewingResult])
    def viewings(actor: ActorDep, agent: ServiceDep):
        return agent.viewings(actor)

    @app.get("/viewings/{viewing_id}", response_model=ViewingResult)
    def viewing(viewing_id: str, actor: ActorDep, agent: ServiceDep):
        return agent.viewing(viewing_id, actor)

    @app.get("/support-tickets", response_model=list[SupportResult])
    def support(actor: ActorDep, agent: ServiceDep):
        return agent.support_tickets(actor)

    # --- W-01/W-02: organizations, memberships (server-side roles only) ---

    @app.get("/organizations", response_model=list[OrganizationResult])
    def organization_list(actor: ActorDep, agent: ServiceDep):
        return organizations.list_organizations(agent.repo, actor)

    @app.post("/organizations", status_code=201, response_model=OrganizationResult)
    def organization_create(body: OrganizationCreate, actor: ActorDep, agent: ServiceDep):
        return organizations.create_organization(agent.repo, actor, body.name)

    @app.get("/organizations/{org_id}/memberships", response_model=list[MembershipResult])
    def membership_list(org_id: str, actor: ActorDep, agent: ServiceDep):
        return organizations.list_memberships(agent.repo, actor, org_id)

    @app.post("/organizations/{org_id}/memberships", status_code=201, response_model=MembershipResult)
    def membership_grant(org_id: str, body: MembershipGrant, actor: ActorDep, agent: ServiceDep):
        return organizations.grant_membership(agent.repo, actor, org_id, body.user_id, body.role)

    @app.delete("/organizations/{org_id}/memberships/{membership_id}", response_model=MembershipResult)
    def membership_revoke(org_id: str, membership_id: str, actor: ActorDep, agent: ServiceDep):
        return organizations.revoke_membership(agent.repo, actor, org_id, membership_id)

    # --- W-03: registration, verification, password reset (dev stub delivery) ---

    @app.post("/auth/register", status_code=201, response_model=RegisterResult)
    def register(body: RegisterRequest, request: Request, agent: ServiceDep):
        require_delivery_available(request)
        return register_account(agent.repo, body.username, body.password, body.email,
                                body.display_name, delivery=request.app.state.delivery)

    @app.post("/auth/verify", response_model=VerifyResult)
    def verify(body: VerifyRequest, agent: ServiceDep):
        return verify_account(agent.repo, body.username, body.token)

    @app.post("/auth/password-reset/request", response_model=PasswordResetRequestResult)
    def password_reset_request(body: PasswordResetRequest, request: Request, agent: ServiceDep):
        require_delivery_available(request)
        # Same response for known, unknown, seed and disabled accounts.
        return request_password_reset(agent.repo, body.username,
                                      delivery=request.app.state.delivery)

    @app.post("/auth/password-reset/confirm", response_model=PasswordResetConfirmResult)
    def password_reset_confirm(body: PasswordResetConfirm, agent: ServiceDep):
        return confirm_password_reset(agent.repo, body.username, body.token, body.new_password,
                                      delivery=None)

    # --- W-03: profile, consents and session management ---

    @app.get("/me/profile", response_model=ProfileResult)
    def my_profile(actor: ActorDep, agent: ServiceDep):
        return account_profile(agent.repo, actor.id)

    @app.patch("/me/profile", response_model=ProfileResult)
    def patch_my_profile(body: ProfilePatch, request: Request, actor: ActorDep, agent: ServiceDep):
        updates = body.model_dump(exclude_unset=True)
        if "email" in updates:
            require_delivery_available(request)
        result = update_account_profile(agent.repo, actor.id, updates,
                                        delivery=request.app.state.delivery)
        if (updates.get("consents") or {}).get("remember_sessions") is False:
            # Withdrawing the consent erases the stored memory, not just hides it.
            memory.forget(agent.repo, actor.id)
        return result

    @app.get("/me/memory", response_model=MemoryResult)
    def my_memory(actor: ActorDep, agent: ServiceDep):
        with agent.lock:
            remembered = memory.recall(agent.repo, actor.id)
            return {"consented": memory.consented(agent.repo, actor.id), "memory": remembered}

    @app.delete("/me/memory", response_model=ForgetResult)
    def forget_memory(actor: ActorDep, agent: ServiceDep):
        with agent.lock:
            return memory.forget(agent.repo, actor.id)

    @app.delete("/me/memory/{field}", response_model=ForgetResult)
    def forget_memory_field(field: str, actor: ActorDep, agent: ServiceDep):
        if field not in memory.REMEMBERED_FIELDS:
            raise DomainError("invalid_memory_field", "Trường ghi nhớ không được hỗ trợ.", 422)
        with agent.lock:
            return memory.forget(agent.repo, actor.id, field)

    @app.get("/me/sessions", response_model=list[SessionEntry])
    def my_sessions(actor: ActorDep, agent: ServiceDep):
        return list_sessions(agent.repo, actor.id)

    @app.delete("/me/sessions/{token_id}", response_model=SessionRevokeResult)
    def revoke_my_session(token_id: str, actor: ActorDep, agent: ServiceDep):
        return revoke_session(agent.repo, actor.id, token_id)

    return app


app = create_app()
