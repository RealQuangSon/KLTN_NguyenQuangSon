from __future__ import annotations

import json
import hashlib
import os
import re
import sqlite3
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path
from threading import RLock
from typing import TypedDict
from pydantic import ValidationError

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .agent_budget import SessionTurnBudget
from .agent_capability import Resource, require, require_session_role
from .agent_guard import (PROVIDER_FALLBACK_CODES, mention_room_id, provider_fallback_reply,
                          quarantine_reply, redact, redact_tree, resolve_room_reference,
                          screen_injection, viewing_intent, viewing_prep_missing_room_reply)
from .agent_provenance import stamp
from .agent_loop import SUMMARY_SYSTEM_PROMPT, fast_path_reply, run_turn as run_agent_turn
from .agents import ToolBox
from . import advisor, auth, automation, conversations, copilot, handbook, listings, media, memory, notifications, pms, promotions
from .catalog import Catalog, StoredCatalog
from .catalog import distance_m as catalog_distance_m
from .costs import estimate_cost, estimate_with_affordability
from .interpreter import (DemoInterpreter, OpenAIInterpreter, Interpreter, budget_hint, fixed_intent,
                          make_interpreter, redact, relative_budget, rent_budget_hint)
from .locations import city_for_area, resolve_place
from .models import (DEFAULT_LANDLORD, Actor, CatalogStatus, CostRequest, Destination, DomainError, DraftPatch,
                     DraftProfile, Profile, RoomInput, RoomUpdate, Scenario, SimulationRequest)
from .repository import Repository
from .organizations import record_audit
from .operations import Metrics

AMENITIES = {"window", "quiet", "parking", "air_conditioning", "private_bathroom",
             "washing_machine", "balcony", "furniture", "pets_allowed"}


CHAT_RETENTION_DAYS = int(os.getenv("HOMEMATCH_CHAT_RETENTION_DAYS", "90"))

# Value written to the legacy hm_sessions.manager_id column (NOT NULL since v1,
# so the column stays). It backs no permission decision: sessions are authorized
# per record via owner_id (renter) and room ownership (landlord). Fixed value is
# a demo rule; production would use a trusted assignment table.
LEGACY_ASSIGNEE = "manager-a"

# Lifecycle of handoff support tickets (hm_support), mirroring the PMS
# TICKET_TRANSITIONS pattern. Reopening a resolved ticket is allowed.
SUPPORT_TRANSITIONS = {
    "requested": frozenset({"in_progress", "resolved"}),
    "in_progress": frozenset({"resolved"}),
    "resolved": frozenset({"in_progress"}),
}


class ChatState(TypedDict, total=False):
    session_id: str
    actor: Actor
    text: str
    intent: str | None
    extraction: dict
    budget_hint: int | None
    # AG-02: tiền tương đối parse từ câu GỐC (trước redact) — key phải khai
    # báo trong schema, LangGraph mới giữ lại khi invoke.
    relative_budget: dict | None
    cost_input: dict | None
    response: dict
    provenance: dict
    toolbox: ToolBox


class RecommendationState(TypedDict, total=False):
    run_id: str
    items: list[dict]
    diagnostics: dict


class HomeMatchService:
    """Single-process MVP. API permissions live here, outside the LLM and graph."""

    def __init__(self, db_path: str | Path = ".local/homematch.sqlite",
                 catalog: Catalog | None = None, interpreter: Interpreter | None = None):
        self.lock = RLock()
        self.metrics = Metrics()
        self.repo = None
        self.checkpoint_connection = None
        self.matching_method = os.getenv("HOMEMATCH_MATCHING_METHOD", "B1")
        if self.matching_method not in {"B1", "P"}:
            raise ValueError("HOMEMATCH_MATCHING_METHOD must be B1 or P")
        try:
            self._initialize(db_path, catalog, interpreter)
        except Exception:
            self.close()
            raise

    def _initialize(self, db_path: str | Path, catalog: Catalog | None, interpreter: Interpreter | None):
        self.repo = Repository(db_path)
        if self.repo.db.postgres:
            from psycopg.rows import dict_row
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool
            # A checked pool, not one long-lived session: hosted PostgreSQL (Neon
            # scale-to-zero) drops idle sessions, and the pool replaces them on checkout.
            self.checkpoint_connection = ConnectionPool(
                str(db_path), min_size=1, max_size=2, open=True, check=ConnectionPool.check_connection,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0})
            self.checkpointer = PostgresSaver(self.checkpoint_connection)
        else:
            checkpoint_path = str(db_path) + ".checkpoints.sqlite" if str(db_path) != ":memory:" else ":memory:"
            self.checkpoint_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
            self.checkpointer = SqliteSaver(self.checkpoint_connection)
        self.checkpointer.setup()
        initial_path = os.getenv("HOMEMATCH_CATALOG_PATH")
        self.catalog = catalog or StoredCatalog(self.repo, Catalog(Path(initial_path)) if initial_path else None)
        embedding_mode = os.getenv("HOMEMATCH_EMBEDDING_MODE", "disabled")
        if embedding_mode not in {"disabled", "openai"}:
            raise ValueError("HOMEMATCH_EMBEDDING_MODE must be disabled or openai")
        if embedding_mode == "openai" and not self.repo.db.postgres:
            raise ValueError("Live embeddings require PostgreSQL/pgvector")
        if embedding_mode == "openai":
            from .semantic import OpenAIEmbeddings, PostgresSemantic
            self.catalog.semantic_scorer = PostgresSemantic(self.repo, self.catalog, OpenAIEmbeddings(
                dimensions=int(os.getenv("HOMEMATCH_EMBEDDING_DIMENSIONS", "1536")),
                on_usage=self.metrics.embedding_usage),
                on_lookup=self.metrics.semantic_query)
            self.catalog.alpha = float(os.getenv("HOMEMATCH_SEMANTIC_ALPHA", ".3"))
            if not 0 <= self.catalog.alpha <= 1:
                raise ValueError("HOMEMATCH_SEMANTIC_ALPHA must be in [0,1]")
        self.interpreter = interpreter or make_interpreter()
        # HN-06: ngân sách theo LƯỢT CHAT cần AI + trần chi phí USD của phiên.
        try:
            budget_limit = int(os.getenv("HOMEMATCH_SESSION_TURN_BUDGET", "60"))
        except ValueError:
            raise ValueError("HOMEMATCH_SESSION_TURN_BUDGET must be an integer") from None
        try:
            cost_cap = float(os.getenv("HOMEMATCH_SESSION_COST_CAP_USD", "0.05"))
        except ValueError:
            raise ValueError("HOMEMATCH_SESSION_COST_CAP_USD must be a number") from None
        self.budget = SessionTurnBudget(budget_limit, cost_cap)
        # In-memory diagnostics of the last chat turn / result read per session.
        # Redacted at write time; never persisted and never returned to the model.
        self._traces: dict[str, dict] = {}
        # WS-01: ngữ cảnh workspace hiện tại của từng phiên (ephemeral, một worker).
        self._workspace: dict[str, dict] = {}
        self.chat_graph = self._build_chat_graph()
        self.recommendation_graph = self._build_recommendation_graph()

    def close(self):
        if self.checkpoint_connection is not None:
            self.checkpoint_connection.close()
        if self.repo is not None:
            self.repo.close()

    def checkpoint_probe(self) -> None:
        """Readiness check on the checkpoint store (SQLite connection or PostgreSQL pool)."""
        query = "SELECT 1 FROM checkpoints LIMIT 1"
        if self.repo.db.postgres:
            with self.checkpoint_connection.connection() as connection:
                connection.execute(query).fetchone()
        else:
            self.checkpoint_connection.execute(query).fetchone()

    @staticmethod
    def _role(actor: Actor, role: str):
        if actor.role != role:
            raise DomainError("forbidden", "Vai trò không được phép thực hiện thao tác này.", 403)

    def _session_for(self, session_id: str, actor: Actor, role: str) -> dict:
        session = self.repo.session(session_id)
        require_session_role(session, actor, role)
        return session

    def _fresh(self, run: dict) -> bool:
        session = self.repo.session(run["session_id"])
        if (run["status"] == "invalidated" or session["profile_version"] != run["profile_version"]
                or session["active_run_id"] != run["id"] or self.catalog.version != run["catalog_version"]):
            self.repo.invalidate(run["id"])
            return False
        return True

    @staticmethod
    def _session_projection(session: dict) -> dict:
        return {"session_id": session["id"], "draft_revision": session["draft_revision"],
                "draft": json.loads(session["draft_json"]), "profile_version": session["profile_version"],
                "confirmed_profile": json.loads(session["profile_json"]) if session["profile_json"] else None,
                "active_run_id": session["active_run_id"]}

    def create_session(self, actor: Actor) -> dict:
        with self.lock:
            require("session:create", actor)
            # The needs agent may prefill from consented memory; fields stay `inferred`.
            toolbox = ToolBox()
            remembered = toolbox.call("needs", "read_memory", memory.recall, self.repo, actor.id)
            draft = memory.prefill(DraftProfile(), remembered) if remembered else None
            # Fixed assignment is a demo rule; production uses a trusted assignment table.
            return self._session_projection(self.repo.create_session(actor.id, LEGACY_ASSIGNEE, draft))

    def session(self, session_id: str, actor: Actor) -> dict:
        with self.lock:
            require("session:read", actor)
            return self._session_projection(self._session_for(session_id, actor, "renter"))

    def message(self, session_id: str, actor: Actor, text: str, cost_input: CostRequest | None = None,
                emit=None, workspace: dict | None = None, turn_id: str | None = None) -> dict:
        """Retry cùng khóa trả lại lượt đã hoàn tất; quyền luôn kiểm trước cache.

        Một transaction bao toàn bộ thay đổi nghiệp vụ và cache; checkpoint không
        phải nguồn quyết định quyền hay công bố. Chỉ một worker như CLAUDE.md.
        """
        turn_id = turn_id or str(uuid4())
        uuid_key = re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", turn_id)
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", turn_id)
                or (not uuid_key and redact(turn_id) != turn_id)):
            raise DomainError("invalid_turn_id", "Mã lượt không hợp lệ.", 422)
        request_hash = hashlib.sha256(json.dumps(
            {"text": text, "workspace": workspace,
             "cost_input": cost_input.model_dump(mode="json") if cost_input else None},
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            session = self._session_for(session_id, actor, "renter")
            require("chat:message", actor, Resource.for_session(session))
            with self.repo.guard():
                previous = self.repo.db.execute(
                    "SELECT * FROM hm_agent_requests WHERE session_id=? AND turn_id=?",
                    (session_id, turn_id)).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise DomainError("idempotency_conflict", "Mã lượt đã dùng cho nội dung khác.", 409)
                    if (previous["result_revision"] != session["draft_revision"]
                            or previous["catalog_version"] != self.catalog.version):
                        raise DomainError("stale_turn", "Nhu cầu hoặc kho đã đổi; hãy gửi một lượt mới.", 409)
                    return {**self.session(session_id, actor), **json.loads(previous["response_json"])}
                result = self._message_once(session_id, actor, text, cost_input, emit, workspace, turn_id)
                # Không nhân bản hồ sơ/thu nhập vào cache lượt; chỉ lưu phản hồi đã che PII.
                envelope = {key: value for key, value in result.items()
                            if key not in self._session_projection(session)}
                from .agent_tools import public_result
                envelope = public_result(envelope, for_renter=True)
                self.repo.db.execute("INSERT INTO hm_agent_requests VALUES(?,?,?,?,?,?,?)",
                    (session_id, turn_id, request_hash, json.dumps(envelope, ensure_ascii=False),
                     result["draft_revision"], self.catalog.version, conversations.utc_now()))
                projection = {**self.session(session_id, actor), **envelope}
            # HN-04: tóm tắt hội thoại cập nhật mỗi 4 lượt — chạy NGOÀI transaction
            # của lượt (không giữ khóa DB khi gọi LLM); best-effort, lỗi bỏ qua.
            self._refresh_conversation_summary(session_id)
            return projection

    def _message_once(self, session_id: str, actor: Actor, text: str, cost_input: CostRequest | None = None,
                      emit=None, workspace: dict | None = None, turn_id: str | None = None) -> dict:
        """Một lượt chat. `emit` (WS-02) nhận từng sự kiện bước ngay khi chạy:
        {"name", "kind": router|tool|guardrail|system, "detail"} — không PII."""
        with self.lock:
            session = self._session_for(session_id, actor, "renter")
            require("chat:message", actor, Resource.for_session(session))
            if not text.strip() or len(text) > 2000:
                raise DomainError("invalid_message", "Tin nhắn cần có 1–2000 ký tự.", 422)
            if workspace is not None:
                # WS-01: ngữ cảnh workspace FE gửi lên (view, căn chọn, ≤30 căn đang
                # hiện, ≤4 căn đang chú ý) — giữ trong bộ nhớ tiến trình để hiểu
                # "căn này"/"căn thứ 2"; không bao giờ vào DTO chủ nhà hay prompt thu nhập.
                self._workspace[session_id] = {
                    "view": workspace.get("view"),
                    "selected_room_id": workspace.get("selected_room_id"),
                    "visible_room_ids": list(workspace.get("visible_room_ids") or [])[:30],
                    "focus_room_ids": list(workspace.get("focus_room_ids") or [])[:4],
                }
            scan = screen_injection(text)
            explicit_route = fixed_intent(text)
            usage = {"logical_calls": 0, "tokens": None, "mode": self.interpreter.mode}
            provider_error = None
            try:
                if scan.flagged and explicit_route is None:
                    # Quarantined: the assistant path never sees this text and the
                    # draft is left untouched. Flagged text on an explicit
                    # deterministic route (cost/support) still runs the engine,
                    # which never reads the message body.
                    if emit is not None:
                        emit({"name": "guardrail", "kind": "guardrail",
                              "detail": "Tin nhắn có dấu hiệu chèn lệnh — cách ly khỏi trợ lý"})
                    response, provenance = quarantine_reply(scan), stamp("deterministic-engine", "injection_quarantine")
                elif explicit_route is None and viewing_intent(text):
                    response, provenance = self._prepare_viewing(session, actor, text)
                elif isinstance(self.interpreter, OpenAIInterpreter):
                    # HN-01 đường tắt tất định: ý định rõ đi graph luật ngay; câu
                    # luật hiểu đủ thì confirm không cần LLM; còn lại mới vào
                    # vòng lặp agent (AG-13). Mọi đường đều không chết giữa chừng.
                    fast = (self._explicit_fast_path(session, actor, text, explicit_route,
                                                     cost_input)
                            if explicit_route else
                            fast_path_reply(self, session, actor, text, emit=emit, turn_id=turn_id))
                    if fast is not None:
                        response, provenance = fast
                    else:
                        # AG-13: vòng lặp agent tự gọi tool; model lỗi/hết ngân sách
                        # phiên → rơi về graph cũ, không bao giờ chết giữa chừng.
                        try:
                            response, provenance = run_agent_turn(self, session, actor, text, emit=emit, turn_id=turn_id)
                        except DomainError as error:
                            if error.code not in PROVIDER_FALLBACK_CODES:
                                raise  # budget_exceeded đi thẳng 429 thân thiện (HN-06)
                            provider_error = error.code
                            try:
                                response, provenance = self._chat_graph_turn(session, actor, text,
                                                                             explicit_route, cost_input, spend=False)
                            except DomainError as inner:
                                if inner.code not in PROVIDER_FALLBACK_CODES:
                                    raise
                                # Graph cũ cũng lỗi provider → trả biểu mẫu có nhãn mã.
                                response = provider_fallback_reply(inner.code)
                                provenance = stamp("deterministic-engine", "provider_fallback")
                            response = {**response, "agent_mode": "graph_fallback"}
                else:
                    if emit is not None:
                        emit({"name": "route", "kind": "router",
                              "detail": "Định tuyến theo luật và agent chuyên trách"})
                    response, provenance = self._chat_turn(session, actor, text, explicit_route, cost_input)
                    if emit is not None:
                        emit({"name": str(response.get("intent") or "graph"), "kind": "system",
                              "detail": "Hệ thống tự bổ sung: trả lời theo nhánh tất định"})
            except DomainError as error:
                if error.code not in PROVIDER_FALLBACK_CODES:
                    raise
                # Provider failure/timeout: deterministic guided-form fallback with
                # the taxonomy code kept visible; never a fabricated extraction.
                provider_error = error.code
                response, provenance = provider_fallback_reply(error.code), stamp("deterministic-engine", "provider_fallback")
            finally:
                if explicit_route is None and self.interpreter.mode == "openai":
                    usage.update(self.interpreter.last_usage)
                self.metrics.provider_usage(usage)
            guard = {"injection_flagged": scan.flagged, "patterns": scan.patterns,
                     "provider_error": provider_error,
                     "budget": {"turns_used": self.budget.used(session_id),
                                "turn_limit": self.budget.turn_limit,
                                "spent_usd": self.budget.spent_usd(session_id)}}
            self._traces.setdefault(session_id, {})["chat"] = {
                "provenance": provenance, "guard": guard,
                "input_redacted": redact(text),
            }
            self._limit_clarification_response(session_id, response)
            self._store_transcript(session_id, actor.id, text, response, provenance, scan.flagged)
            return {**self.session(session_id, actor), **response, "turn_id": turn_id, "usage": usage,
                    "provenance": provenance, "guard": guard}

    def _explicit_fast_path(self, session: dict, actor: Actor, text: str,
                            explicit_route: str, cost_input: CostRequest | None):
        """HN-01: ý định rõ (chi phí/vay/handbook/handover/hỗ trợ) đi graph luật
        ngay, không vòng LLM — các nhánh này không cần trích xuất của model.
        Lỗi provider hiếm hoi của graph vẫn trả biểu mẫu có nhãn mã."""
        try:
            response, provenance = self._chat_graph_turn(session, actor, text,
                                                         explicit_route, cost_input, spend=False)
        except DomainError as error:
            if error.code not in PROVIDER_FALLBACK_CODES:
                raise
            response = provider_fallback_reply(error.code)
            provenance = stamp("deterministic-engine", "provider_fallback")
        return {**response, "agent_mode": "fast_path"}, provenance

    def _store_transcript(self, session_id: str, user_id: str, text: str, response: dict, provenance: dict,
                          flagged: bool):
        """PII-masked transcript for admin audit and handover; kept CHAT_RETENTION_DAYS days."""
        reply = (response.get("message") or " ".join(response.get("questions") or [])
                 or "; ".join(entry["title"] for entry in response.get("answers") or [])
                 or response.get("status", ""))
        now = conversations.utc_now()
        with self.repo.db:
            for speaker, value in (("user", text), ("assistant", reply)):
                self.repo.db.execute("INSERT INTO hm_chat_transcripts VALUES(?,?,?,?,?,?,?,?)",
                                     (str(uuid4()), session_id, user_id, speaker,
                                      conversations.mask_pii(value)[:2000], response.get("intent"),
                                      "quarantine" if flagged else provenance.get("agent"), now))

    def purge_transcripts(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=CHAT_RETENTION_DAYS)).isoformat()
        with self.repo.db:
            self.repo.db.execute("DELETE FROM hm_agent_requests WHERE created_at<?", (cutoff,))
            self.repo.db.execute("DELETE FROM hm_agent_tool_calls WHERE created_at<?", (cutoff,))
            return self.repo.db.execute("DELETE FROM hm_chat_transcripts WHERE created_at<?", (cutoff,)).rowcount

    def _chat_turn(self, session: dict, actor: Actor, text: str, explicit_route: str | None,
                   cost_input: CostRequest | None) -> tuple[dict, dict]:
        """Graph cũ (demo mode); agent loop đã chiếm nhánh openai ở message()."""
        return self._chat_graph_turn(session, actor, text, explicit_route, cost_input, spend=True)

    def _chat_graph_turn(self, session: dict, actor: Actor, text: str, explicit_route: str | None,
                         cost_input: CostRequest | None, spend: bool = True) -> tuple[dict, dict]:
        if explicit_route is None and spend:
            # One AI chat turn per extraction turn (HN-06); attempts count even
            # when the provider fails.
            self.budget.ensure_turn(session["id"])
        state = self.chat_graph.invoke({"session_id": session["id"], "actor": actor, "text": redact(text),
            "intent": explicit_route, "budget_hint": rent_budget_hint(text),
            # AG-02: parse tiền tương đối từ câu GỐC (trước redact — placeholder
            # đã tách số nên không đọc được trên state["text"]).
            "relative_budget": relative_budget(text), "toolbox": ToolBox(),
            "cost_input": cost_input.model_dump(mode="json") if cost_input else None})
        return dict(state["response"]), dict(state.get("provenance") or {})

    def _prepare_viewing(self, session: dict, actor: Actor, text: str) -> tuple[dict, dict]:
        """Chat-side preparation only: validates the room is approved/current for
        this session before anything is created. The viewing itself is still
        created by the explicit request_viewing form action with time + key."""
        require("viewing:prepare", actor, Resource.for_session(session))
        result = self.results(session["id"], actor)
        room_id = resolve_room_reference(text, result["results"])
        if room_id is None:
            if mention_room_id(text):
                raise DomainError("not_visible", "Phòng chưa thuộc kết quả hiện tại.", 403)
            return viewing_prep_missing_room_reply(), stamp("deterministic-engine", "viewing_prepare",
                                                            outcome="missing_room_reference")
        reply = {"intent": "find_room", "status": "needs_clarification",
                 "questions": [f"Phòng {room_id} đang trong bản gợi ý hiện tại (phiên bản hồ sơ "
                               f"{result['profile_version']}). Chọn thời gian xem có múi giờ trong tương lai "
                               "rồi gửi biểu mẫu yêu cầu lịch xem; chat không tự giữ phòng."],
                 "message": f"Đã kiểm tra phòng {room_id} đủ điều kiện đặt lịch; chưa tạo lịch xem."}
        return reply, stamp("deterministic-engine", "viewing_prepare", room_id=room_id,
                            run_id=result["run_id"], outcome="prepared")

    # --- AG-13: helpers cho vòng lặp agent ---

    def _draft(self, session_id: str) -> DraftProfile:
        return DraftProfile.model_validate_json(self.repo.session(session_id)["draft_json"])

    def _apply_agent_patch(self, session_id: str, patch: dict) -> list[str]:
        """Ghi nháp từ tool update_needs: chỉ trường nhu cầu được cấp, trạng thái
        `inferred` với evidence `agent:rN`. Tiền/quyền bị chặn ở lớp tool."""
        with self.repo.guard():
            session = self.repo.session(session_id)
            draft = DraftProfile.model_validate_json(session["draft_json"])
            allowed = {"city", "area", "people", "room_type", "bedrooms", "preferences",
                       "needs_destination", "accept_estimated_data", "soft_description", "destination"}
            touched = {key for key in set(patch) & allowed if getattr(draft, key) != patch[key]}
            if not touched:
                return []
            for key, value in patch.items():
                if key in touched:
                    setattr(draft, key, value)
            evidence = f"agent:r{session['draft_revision'] + 1}"
            for key in touched:
                draft.field_status[key] = "inferred"
                draft.evidence_ref[key] = evidence
            updated = DraftProfile.model_validate(draft.model_dump())
            self.repo.update_draft(session_id, updated, session["draft_revision"])
        return sorted(touched)

    def _apply_chat_budget_hint(self, session_id: str, hint: int, expected_revision: int):
        """Mức tiền trong câu khách (rent_budget_hint) ghi tất định vào nháp,
        trạng thái inferred — bất biến: chỉ là gợi ý, chưa phải trần."""
        with self.repo.guard():
            session = self.repo.session(session_id)
            draft = DraftProfile.model_validate_json(session["draft_json"])
            draft.budget_hint_vnd = hint
            draft.field_status["budget_hint"] = "inferred"
            draft.evidence_ref["budget_hint"] = f"agent:r{expected_revision + 1}"
            self.repo.update_draft(session_id, DraftProfile.model_validate(draft.model_dump()),
                                   expected_revision)

    def _confirmed_profile(self, session_id: str) -> Profile:
        session = self.repo.session(session_id)
        if not session["profile_json"]:
            raise DomainError("no_profile", "Chưa có hồ sơ đã xác nhận.", 409)
        return Profile.model_validate_json(session["profile_json"])

    def _profile_from_draft(self, session_id: str, session_row: dict | None = None) -> Profile | None:
        """Hồ sơ từ nháp (chưa ghi gì): lần đầu dùng mức tiền nháp làm trần như
        auto-confirm ở FE; sau khi đã xác nhận chỉ áp trường nháp có bằng chứng
        (chat/agent/form), KHÔNG đổi trần tiền — tiền chỉ là gợi ý tới khi khách
        xác nhận qua form. None khi chưa đủ dữ liệu tối thiểu. `session_row` cho
        phép clarify dựng hồ sơ tạm với biến thể nháp không ghi."""
        session = session_row or self.repo.session(session_id)
        draft = DraftProfile.model_validate_json(session["draft_json"])
        scenario = Scenario(people=draft.people or 1, vehicles=1, electricity_kwh="140",
                            water_m3="3", moving_vnd=300_000, setup_vnd=200_000)
        if not session["profile_json"]:
            if not draft.city or draft.budget_hint_vnd is None:
                return None
            # AG-11: budget_scope "rent" → hint là trần THUÊ (max_rent_vnd), trần
            # tổng tạm bằng hint (thận trọng, không bịa hệ số phí); total/None →
            # hint là trần tổng tháng (hành vi cũ).
            if draft.budget_scope == "rent":
                rent_cap, monthly_cap = draft.budget_hint_vnd, draft.budget_hint_vnd
            else:
                rent_cap, monthly_cap = None, draft.budget_hint_vnd
            return Profile(city=draft.city, area=draft.area, room_type=draft.room_type or "room",
                           min_bedrooms=draft.bedrooms if (draft.room_type == "apartment" and draft.bedrooms) else None,
                           max_monthly_cost_vnd=monthly_cap, max_rent_vnd=rent_cap, scenario=scenario,
                           preferences=list(draft.preferences), destination=draft.destination,
                           soft_description=draft.soft_description,
                           accept_estimated_data=draft.accept_estimated_data)
        base = Profile.model_validate_json(session["profile_json"])
        evidence = draft.evidence_ref
        updates: dict = {}
        if evidence.get("city") and draft.city:
            updates["city"] = draft.city
        if evidence.get("area"):
            updates["area"] = draft.area
        if evidence.get("room_type") and draft.room_type:
            updates["room_type"] = draft.room_type
            updates["min_bedrooms"] = draft.bedrooms if (
                draft.room_type == "apartment" and evidence.get("bedrooms")) else None
        scenario_update = {}
        if evidence.get("people") and draft.people:
            scenario_update["people"] = draft.people
        if evidence.get("preferences"):
            updates["preferences"] = [item for item in draft.preferences
                                      if item not in base.must_amenities]
        if evidence.get("destination"):
            updates["destination"] = draft.destination
        if evidence.get("accept_estimated_data") and draft.accept_estimated_data:
            updates["accept_estimated_data"] = True
        if evidence.get("soft_description"):
            updates["soft_description"] = draft.soft_description
        if scenario_update:
            updates["scenario"] = base.scenario.model_copy(update=scenario_update)
        # AG-11: chip đổi budget_scope trên hồ sơ đã xác nhận.
        if evidence.get("budget_scope") and draft.budget_scope == "rent" and draft.budget_hint_vnd:
            updates["max_rent_vnd"] = draft.budget_hint_vnd
        elif evidence.get("budget_scope") and draft.budget_scope == "total" and draft.budget_hint_vnd:
            updates["max_monthly_cost_vnd"] = draft.budget_hint_vnd
        return base.model_copy(update=updates) if updates else base

    def room_reference_in(self, ref: str, visible: dict) -> str | None:
        """AG-05: resolver đầy đủ trong agent_guard, bó trong danh sách đang có."""
        return resolve_room_reference(ref, [{"room_id": room_id} for room_id in visible])

    def _strip_money_for_decision(self, context: dict) -> dict:
        """Ngữ cảnh gửi Jev: không tiền tuyệt đối, không thu nhập (PLAN AG-11)."""
        from .decisions import decision_context
        return decision_context(context)

    def _apply_clarification_choice(self, session_id: str, best: dict):
        """Tự chấp nhận cách hiểu phổ biến nhất (p_max ≥ ngưỡng): áp vào nháp ở
        trạng thái inferred kèm nhãn clarify:auto — khách vẫn sửa được."""
        interpretation = best["interpretation"]
        session = self.repo.session(session_id)
        draft = self._draft(session_id)
        field = {"destination_radius": "destination", "budget_scope": "budget"}.get(
            interpretation["field"], interpretation["field"])
        key = "budget_scope" if field == "budget" else field
        value = (interpretation.get("radius_m") if field == "destination" else
                 interpretation.get("scope") if field == "budget" else interpretation.get("value"))
        current = (draft.destination.max_distance_m if field == "destination" and draft.destination
                   else getattr(draft, key, None))
        if draft.field_status.get(key) == "confirmed" and value != current:
            return None
        if session["profile_json"]:
            base = Profile.model_validate_json(session["profile_json"])
            if (field == "destination" and base.destination and value > base.destination.max_distance_m
                    or field in {"area", "room_type"} and getattr(base, field) and value != getattr(base, field)
                    or field == "people" and value < base.scenario.people
                    or field == "budget" and draft.budget_hint_vnd
                    and (draft.budget_hint_vnd > base.max_monthly_cost_vnd
                         or interpretation.get("scope") == "rent" and base.max_rent_vnd is not None
                         and draft.budget_hint_vnd > base.max_rent_vnd)):
                return None
        evidence = f"clarify:auto-r{session['draft_revision'] + 1}"
        if field == "destination" and draft.destination:
            draft.destination = draft.destination.model_copy(
                update={"max_distance_m": interpretation["radius_m"]})
            draft.field_status["destination"] = "inferred"
            draft.evidence_ref["destination"] = evidence
        elif field == "budget":
            draft.budget_scope = interpretation["scope"]
            draft.field_status["budget_scope"] = "inferred"
            draft.evidence_ref["budget_scope"] = evidence
        elif field in {"area", "room_type", "people"}:
            setattr(draft, field, value)
            draft.field_status[field] = "inferred"
            draft.evidence_ref[field] = evidence
        else:
            return None
        self.repo.update_draft(session_id, DraftProfile.model_validate(draft.model_dump()),
                               session["draft_revision"])
        return best["label"]

    def _clarification_payload(self, session_id: str, field: str | None = None,
                               decision_cache: dict | None = None) -> dict | None:
        """AG-11: dựng lựa chọn từ kho thật, Jev/luật quyết định hỏi hay tự chấp nhận."""
        from . import clarify as clarify_layer, decisions as decisions_layer
        clarification = clarify_layer.build_clarification(self, session_id, field=field)
        if clarification is None:
            return None
        context = self._strip_money_for_decision(self._agent_context(self.repo.session(session_id)))
        mode = "rules" if self.interpreter.mode != "openai" else None
        cache_key = hashlib.sha256(json.dumps([clarification, context], sort_keys=True,
                                              ensure_ascii=False).encode()).hexdigest()
        cached = decision_cache.get(cache_key) if decision_cache is not None else None
        if cached is None:
            decision, best, decided_by, error = decisions_layer.decide(clarification, context, mode=mode)
            if decision_cache is not None:
                decision_cache[cache_key] = (decision, best, decided_by, error, clarification)
        else:
            decision, best, decided_by, _, clarification = cached
        if decision == "accept" and best is not None:
            label = self._apply_clarification_choice(session_id, best)
            if label is not None:
                return {"assumed": clarify_layer.option_label(best), "field": clarification["field"],
                        "decided_by": decided_by}
        return clarify_layer.to_dto(clarification, decided_by)

    def _can_ask_clarification(self, session_id: str) -> bool:
        published = self.repo.db.execute(
            "SELECT 1 FROM hm_runs WHERE session_id=? AND published_at IS NOT NULL LIMIT 1",
            (session_id,)).fetchone()
        return bool(published or self.repo.session(session_id)["clarification_questions"] < 2)

    def _limit_clarification_response(self, session_id: str, response: dict) -> None:
        """Chỉ đếm câu hỏi đã gửi, trong transaction của lượt nên retry không tăng đôi."""
        dto = response.get("clarification") or {}
        questions = response.get("questions") or []
        message = response.get("message") or ""
        actual_questions = [question for question in questions if "?" in question]
        question = dto.get("question") or (actual_questions[0] if actual_questions else
                                            message if "?" in message else None)
        if not question:
            return
        if not self._can_ask_clarification(session_id):
            response.update(clarification=None, questions=None,
                message="Mình cần thêm thông tin để tìm chính xác. Bạn điền các mục còn thiếu trong “Nhu cầu của tôi” rồi xác nhận nhé.")
            return
        if dto.get("question"):
            if dto["question"].count("?") > 1:
                dto["question"] = dto["question"].split("?", 1)[0] + "?"
            response["questions"] = [dto["question"]]
            if "?" in message and not message.startswith(dto["question"]):
                response["message"] = dto["question"]
        elif actual_questions:
            # Các dòng lựa chọn/giải thích không phải câu hỏi vẫn được giữ.
            response["questions"] = [question.split("?", 1)[0] + "?" if question.count("?") > 1 else question] + [
                value for value in questions if "?" not in value]
            if "?" in message and not message.startswith(response["questions"][0]):
                response["message"] = response["questions"][0]
        if (response.get("message") or "").count("?") > 1:
            response["message"] = message.split("?", 1)[0] + "?"
        self.repo.db.execute(
            "UPDATE hm_sessions SET clarification_questions=clarification_questions+1 WHERE id=?", (session_id,))

    def _suggested_prompts(self, session_id: str) -> list[str]:
        """WS-01: gợi ý tiếp theo tất định theo trạng thái phiên (không LLM, không số lạ)."""
        try:
            owner = self.repo.session(session_id)["owner_id"]
            result = self.results(session_id, Actor(id=owner, role="renter"))
        except DomainError:
            return []
        if result["results"]:
            return ["Đặt lịch xem căn này", "Tính tổng chi phí căn đầu tiên", "Còn căn nào rẻ hơn khu này?"]
        if result["status"] == "no_match":
            return ["Nới khu vực lân cận", "Cho mình xem căn thiếu bảng phí"]
        return []

    def _criteria_projection(self, session_id: str) -> dict:
        """WS-01: tiêu chí server đang giữ — không thu nhập; số tiền là gợi ý nháp."""
        draft = self._draft(session_id)
        return {"city": draft.city, "area": draft.area, "room_type": draft.room_type,
                "budget_hint_vnd": draft.budget_hint_vnd,
                "destination": draft.destination.label if draft.destination else None}

    def _agent_context(self, session: dict) -> dict:
        """Ngữ cảnh lượt agent: nháp + hồ sơ đã xác nhận (bỏ thu nhập) + 6 lượt
        chat gần nhất đã PII-mask tại lúc ghi. Không bao gồm thu nhập."""
        draft = DraftProfile.model_validate_json(session["draft_json"])
        confirmed = json.loads(session["profile_json"]) if session["profile_json"] else None
        if confirmed:
            confirmed.pop("monthly_income_vnd", None)
        rows = self.repo.db.execute(
            "SELECT speaker,text FROM hm_chat_transcripts WHERE session_id=? "
            "ORDER BY created_at DESC LIMIT 6", (session["id"],)).fetchall()
        return {"draft": draft.model_dump(mode="json"),
                "confirmed_profile": confirmed,
                "recent_chat": [f"{row['speaker']}: {row['text']}" for row in reversed(rows)],
                "notes": "draft.budget_hint_vnd là mức tiền khách nêu (gợi ý trần tổng tháng); "
                         "destination chỉ đặt qua update_needs sau khi find_place tra được."}

    def _turn_context(self, session: dict, actor: Actor) -> dict:
        """HN-04: ngữ cảnh đầy đủ một lượt agent — nháp + hồ sơ (không thu nhập),
        workspace (view, căn chọn, ≤30 căn dạng gọn), top 5 kết quả hiện tại,
        bộ nhớ sở thích (chỉ khi khách đồng ý), tóm tắt hội thoại. Không tiền
        tuyệt đối ngoài trần khách nêu; không bao giờ có monthly_income_vnd."""
        context = self._agent_context(session)
        context["memory"] = memory.recall(self.repo, session["owner_id"])
        row = self.repo.db.execute("SELECT summary_json FROM hm_sessions WHERE id=?",
                                   (session["id"],)).fetchone()
        if row and row["summary_json"]:
            try:
                summary = json.loads(row["summary_json"])
                context["summary"] = summary.get("text")
            except (ValueError, TypeError):
                context["summary"] = None
        workspace = self._workspace.get(session["id"]) or {}
        draft = self._draft(session["id"])
        destination = draft.destination
        rooms_by_id = {room.id: room for room in self.catalog.rooms()}

        def _distance(room_id: str):
            if not destination:
                return None
            room = rooms_by_id.get(room_id)
            distance = catalog_distance_m(room, destination) if room else None
            return int(distance) if distance is not None else None

        entries: list[dict] = []
        results = self.results(session["id"], actor)["results"]
        by_id = {item["room_id"]: item for item in results}
        for room_id in (workspace.get("visible_room_ids") or [])[:30]:
            item = by_id.get(room_id)
            if item is not None:
                entry = {"room_id": item["room_id"], "title": item["title"],
                         "monthly_total_vnd": (item.get("cost") or {}).get("monthly_total_vnd")}
            else:
                room = rooms_by_id.get(room_id)
                if room is None or not room.published:
                    continue
                entry = {"room_id": room.id, "title": room.title.split(". ")[0],
                         "rent_vnd": room.quote.rent_vnd}
            entry["distance_m"] = _distance(room_id)
            entries.append(entry)
        context["workspace"] = {"view": workspace.get("view"),
                                "selected_room_id": workspace.get("selected_room_id"),
                                "rooms": entries}
        context["current_results"] = [
            {"room_id": item["room_id"], "title": item["title"],
             "monthly_total_vnd": (item.get("cost") or {}).get("monthly_total_vnd"),
             "distance_m": _distance(item["room_id"])}
            for item in results[:5]]
        return context

    def _refresh_conversation_summary(self, session_id: str) -> None:
        """HN-04: tóm tắt hội thoại (≤ ~600 token) cập nhật mỗi 4 lượt bằng một
        lần gọi LLM rẻ không tools, lưu `hm_sessions.summary_json`. Văn bản tóm
        tắt đi qua redact hai lần (vào và ra) — không tiền, SĐT, email, thu nhập.
        Best-effort: mọi lỗi chỉ bỏ qua, không bao giờ làm hỏng lượt đã xong."""
        if self.interpreter.mode != "openai":
            return
        try:
            count = self.repo.db.execute(
                "SELECT COUNT(*) AS c FROM hm_agent_requests WHERE session_id=?",
                (session_id,)).fetchone()["c"]
            if count == 0 or count % 4 != 0:
                return
            rows = self.repo.db.execute(
                "SELECT speaker,text FROM hm_chat_transcripts WHERE session_id=? "
                "ORDER BY created_at DESC LIMIT 12", (session_id,)).fetchall()
            transcript = redact("\n".join(f"{row['speaker']}: {row['text']}"
                                          for row in reversed(rows)))[:4000]
            completion = self.interpreter.client.chat.completions.create(
                model=self.interpreter.model,
                messages=[{"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                          {"role": "user", "content": transcript}],
                max_completion_tokens=300)
            text = redact((completion.choices[0].message.content or "").strip())[:1200]
            if text:
                with self.repo.db:
                    self.repo.db.execute("UPDATE hm_sessions SET summary_json=? WHERE id=?",
                        (json.dumps({"text": text, "turns": count}, ensure_ascii=False), session_id))
        except Exception:
            return  # tóm tắt là tối ưu; lỗi provider không được phá lượt chat

    def agent_trace(self, session_id: str, actor: Actor) -> dict:
        """Redacted diagnostics of the last chat turn and result read. Service-level
        only; no HTTP endpoint exposes it in this slice."""
        with self.lock:
            require("results:read", actor)
            session = self._session_for(session_id, actor, "renter")
            trace = self._traces.get(session["id"]) or {}
            return {"chat": trace.get("chat"), "results": trace.get("results")}

    def confirm(self, session_id: str, actor: Actor, profile: Profile, expected_revision: int) -> dict:
        with self.lock:
            with self.repo.guard():
                session = self._session_for(session_id, actor, "renter")
                require("profile:confirm", actor, Resource.for_session(session))
                unknown = set(profile.must_amenities + profile.preferences) - AMENITIES
                if unknown:
                    raise DomainError("invalid_amenity", "Chọn tiện ích trong từ điển được hỗ trợ.", 422)
                if len(profile.preferences) != len(set(profile.preferences)) or len(profile.must_amenities) != len(set(profile.must_amenities)):
                    raise DomainError("invalid_amenity", "Tiện ích không được lặp lại.", 422)
                session = self.repo.confirm_profile(session_id, expected_revision, profile)
                run = self.repo.create_run(session, self.catalog.version)
            # Remember non-financial preferences only when the renter consented.
            memory.remember(self.repo, actor.id, session_id, profile)
            # The ledger must commit before the independently persisted graph starts.
            self._generate(run["id"])
            return self.results(session_id, actor)

    def _generate(self, run_id: str):
        start = time.monotonic()
        try:
            self.recommendation_graph.invoke({"run_id": run_id}, self._config(run_id))
        except Exception:
            with self.repo.guard():
                self.repo.fail_generation(run_id)
        finally:
            run = self.repo.run(run_id)
            self.metrics.generation(run["status"], run["diagnostics"].get("algorithm", "unavailable"),
                                    time.monotonic() - start)

    def patch_draft(self, session_id: str, actor: Actor, patch: DraftPatch) -> dict:
        with self.lock, self.repo.guard():
            session = self._session_for(session_id, actor, "renter")
            require("draft:patch", actor, Resource.for_session(session))
            fields = {"city", "area", "people", "preferences", "room_type", "bedrooms",
                      "needs_destination", "accept_estimated_data", "soft_description", "destination",
                      "budget_scope", "destination_radius_m"}
            if set(patch.set) - fields or set(patch.clear_fields) - fields:
                raise DomainError("invalid_patch", "Chỉ sửa trường nhu cầu nháp được hỗ trợ.", 422)
            if "budget_scope" in patch.set and patch.set["budget_scope"] not in {"rent", "total"}:
                raise DomainError("invalid_patch", "budget_scope chỉ là rent hoặc total.", 422)
            # AG-11: chip bán kính điểm đến — key ảo dịch thành max_distance_m của
            # destination hiện có (không tạo destination khi chưa có).
            radius = patch.set.pop("destination_radius_m", None)
            values = json.loads(session["draft_json"])
            if radius is not None:
                if not values.get("destination"):
                    raise DomainError("invalid_patch", "Chưa có điểm đến để đổi bán kính.", 422)
                if not isinstance(radius, int) or not 500 <= radius <= 20000:
                    raise DomainError("invalid_patch", "Bán kính cần 500–20000 m.", 422)
                values["destination"]["max_distance_m"] = radius
                touched_radius = True
            else:
                touched_radius = False
            values.update(patch.set)
            for field in patch.clear_fields:
                values[field] = ([] if field == "preferences"
                                 else False if field in {"needs_destination", "accept_estimated_data"} else None)
            if not isinstance(values["preferences"], list) or not all(isinstance(item, str) for item in values["preferences"]):
                raise DomainError("invalid_patch", "preferences cần là danh sách tiện ích.", 422)
            try:
                draft = DraftProfile.model_validate(values)
            except ValidationError:
                raise DomainError("invalid_patch", "Trường nhu cầu chưa hợp lệ.", 422) from None
            if set(draft.preferences + patch.remove_preferences) - AMENITIES:
                raise DomainError("invalid_amenity", "Chọn tiện ích trong từ điển được hỗ trợ.", 422)
            draft.preferences = [item for item in draft.preferences if item not in patch.remove_preferences]
            touched = set(patch.set) | ({"preferences"} if patch.remove_preferences else set())
            # AG-11: chip làm rõ gửi evidence `clarify:rN` và trạng thái confirmed;
            # FE thấy tiền tố clarify: là lượt vừa chọn cách hiểu → tự chạy vòng tìm.
            source_prefix = "clarify" if getattr(patch, "source", "form") == "clarify" else "form"
            evidence = f"{source_prefix}:r{patch.expected_draft_revision + 1}"
            if touched_radius:
                draft.field_status["destination"] = "confirmed"
                draft.evidence_ref["destination"] = evidence
            for field in patch.clear_fields:
                draft.field_status[field] = "unknown"
                draft.evidence_ref.pop(field, None)
            for field in touched:
                # Explicit form input is confirmed; an emptied value goes back to unknown.
                if field in {"needs_destination", "accept_estimated_data"} or getattr(draft, field):
                    draft.field_status[field] = "confirmed"
                    draft.evidence_ref[field] = evidence
                else:
                    draft.field_status[field] = "unknown"
                    draft.evidence_ref.pop(field, None)
            draft = DraftProfile.model_validate(draft.model_dump())
            self.repo.update_draft(session_id, draft, patch.expected_draft_revision)
            return {**self.session(session_id, actor), "status": "needs_clarification", "questions": self._questions(session_id)}

    def _questions(self, session_id: str, has_changes: bool = True) -> list[str]:
        session = self.repo.session(session_id)
        draft = DraftProfile.model_validate_json(session["draft_json"])
        confirmed = json.loads(session["profile_json"]) if session["profile_json"] else {}
        questions = []
        # Kiểu tham chiếu: không thẩm vấn. Số người/xe mặc định 1/1, mức tiền
        # nhắc được hiểu là trần TỔNG THÁNG; điểm đến chưa rõ thì tạm xếp theo
        # khu vực (không chặn vòng tìm). Chỉ hỏi khi chưa biết tìm ở đâu.
        if not draft.city and not draft.area:
            questions.append("Bạn muốn thuê tại thành phố nào?")
        if not questions:
            notes = []
            if draft.needs_destination:
                notes.append("chưa rõ điểm đến nên tạm xếp theo khu vực — nhắn rõ tên trường/cơ sở để xếp gần hơn")
            if draft.budget_hint_vnd:
                notes.append("mức tiền nhắc được hiểu là trần TỔNG THÁNG, mặc định 1 người 1 xe")
            tail = ("; ".join(notes) + " — sai thì sửa trong \"Nhu cầu của tôi\"") if notes else "bạn có thể nhắn thêm tiện ích muốn ưu tiên"
            # AG-03: chỉ hứa run mới khi lượt vừa ĐỔI nhu cầu; nhu cầu không đổi
            # thì nói thật là danh sách hiện tại vẫn đúng.
            outcome = ("Kết quả sẽ tự hiện ở khung bên phải trong chốc lát." if has_changes
                       else "Danh sách hiện tại vẫn đúng với nhu cầu của bạn.")
            questions.append(f"Mình chạy tìm theo nhu cầu đã nắm ({tail}). {outcome}")
        # AG-03: run hiện tại bị giữ vì thiếu sức chứa/bảng phí → hỏi rõ kèm số
        # tin, đề nghị "chấp nhận dữ liệu ước tính" (khách bấm mới bật, không
        # bao giờ bật ngầm).
        if draft.city or draft.area:
            if session["active_run_id"] and not draft.accept_estimated_data:
                try:
                    run = self.repo.run(session["active_run_id"])
                except Exception:
                    run = None
                if run and run["status"] == "needs_verification":
                    verification = (run.get("diagnostics") or {}).get("verification") or {}
                    held = sum(count for key, count in verification.items()
                               if key in {"availability_or_capacity", "monthly_fees", "initial_fees"})
                    if held:
                        questions.append(f"Có {held} tin thiếu sức chứa/bảng phí trong kho. "
                                         "Nhắn “chấp nhận dữ liệu ước tính” để xem kèm nhãn ước tính?")
        return questions[:2]

    def results(self, session_id: str, actor: Actor) -> dict:
        with self.lock, self.repo.guard():
            session = self._session_for(session_id, actor, "renter")
            require("results:read", actor, Resource.for_session(session))
            if session["active_run_id"] is None:
                return {"session_id": session_id, "status": "awaiting_confirmation", "results": []}
            run = self.repo.run(session["active_run_id"])
            if not self._fresh(run):
                run = self.repo.run(run["id"])
            # Deliberately construct a small DTO: never return raw state/draft.
            visible = list(run["items"]) if run["status"] == "published" else []
            provenance = stamp("deterministic-engine", "rank", catalog_version=self.catalog.version,
                               matching_method=self.matching_method, run_status=run["status"])
            self._traces.setdefault(session_id, {})["results"] = {
                "provenance": provenance,
                "run_id": run["id"], "status": run["status"],
                "visible_room_ids": [item["room_id"] for item in visible]}
            return {"session_id": session_id, "run_id": run["id"], "status": run["status"],
                    "profile_version": run["profile_version"], "results": visible,
                    "provenance": provenance,
                    **self._transparency(run, visible),
                    **({"suggestions": self._relaxation_suggestions(run)}
                       if run["status"] in ("no_match", "needs_verification") else {})}

    def _transparency(self, run: dict, visible: list) -> dict:
        """Số liệu tổng hợp và các bước pipeline đã chạy thật của run — minh bạch
        quy trình kiểu workspace tham chiếu. Chỉ aggregate: không lộ danh tính
        phòng nào chưa được công bố."""
        diagnostics = run.get("diagnostics") or {}
        rejected = {key: value for key, value in (diagnostics.get("rejected") or {}).items() if value}
        verification = {key: value for key, value in (diagnostics.get("verification") or {}).items() if value}
        kept = len(visible) if run["status"] == "published" else len(run.get("items") or [])
        scanned = kept + sum(rejected.values()) + sum(verification.values())
        summary = {"scanned": scanned, "kept": kept, "rejected": rejected, "verification": verification}
        filter_line = f"Lọc điều kiện cứng — loại {sum(rejected.values())} tin"
        if verification:
            filter_line += f"; giữ {sum(verification.values())} tin chờ xác minh số liệu"
        status_tail = {
            "generating": "Đang xếp hạng theo nhu cầu đã xác nhận",
            "published": "Đã xếp hạng xong và công bố kết quả cho bạn",
            "no_match": "Không còn căn nào khớp — bạn có thể nới một tiêu chí để tìm lại",
            "needs_verification": "Giữ danh sách vì còn dữ liệu chưa xác minh",
            "invalidated": "Danh sách hết hiệu lực — xác nhận hồ sơ để chạy vòng mới",
            "generation_failed": "Tạo gợi ý bị gián đoạn — có thể chạy lại",
        }.get(run["status"], "")
        steps = [f"Quét {scanned} tin đã công bố trong kho", filter_line,
                 f"Xếp hạng theo phương pháp {self.matching_method} của engine deterministic"]
        if status_tail:
            steps.append(status_tail)
        return {"diagnostics_summary": summary, "steps": steps}

    @staticmethod
    def _relaxation_suggestions(run: dict) -> list[str]:
        """Soft, renter-driven next steps on empty results; never auto-relaxes hard constraints."""
        suggestions: list[str] = []
        profile = Profile.model_validate_json(run["profile_json"]) if run.get("profile_json") else None
        diagnostics = run.get("diagnostics") or {}
        rejected, verification = diagnostics.get("rejected", {}), diagnostics.get("verification", {})
        if profile:
            if profile.area and (rejected.get("area") or rejected.get("city")):
                suggestions.append("Mở rộng khu vực: bỏ giới hạn quận hoặc xem quận lân cận trong cùng thành phố.")
            if rejected.get("required_amenity"):
                suggestions.append("Xem lại tiện ích bắt buộc: chuyển tiện ích ít quan trọng xuống mức 'ưu tiên' để không loại phòng.")
            if profile.destination and (rejected.get("distance") or verification.get("distance_boundary")
                                        or verification.get("location")):
                suggestions.append("Tăng bán kính tối đa quanh điểm đến, hoặc tạm bỏ yêu cầu gần điểm đến.")
            if sum(rejected.get(key, 0) for key in ("rent_budget", "monthly_budget", "initial_budget",
                                                     "loan_principal", "loan_burden")):
                suggestions.append("Có phòng bị loại vì vượt trần đã xác nhận; chỉ bạn được nâng trần tổng tháng/tiền vào ở, hệ thống không tự nới.")
        if verification.get("monthly_fees") or verification.get("initial_fees") or verification.get("availability_or_capacity"):
            suggestions.append("Nhiều phòng thiếu bảng phí hoặc sức chứa: nhắn \"chấp nhận dữ liệu ước tính\" để xem các phòng đó với dữ liệu giả định chuẩn (được gắn nhãn ước tính, cần xác minh khi xem).")
        if any(verification.values()):
            suggestions.append("Có phòng đang bị giữ lại chờ xác minh số liệu; quản lý có thể kiểm tra và cập nhật kho.")
        return suggestions[:4]

    def rerun(self, session_id: str, actor: Actor) -> dict:
        """Người thuê chạy lại vòng tìm của phiên mình khi run hiện tại bị gián
        đoạn. Run mới không kế thừa gì từ run cũ ngoài hồ sơ đã xác nhận."""
        with self.lock:
            with self.repo.guard():
                session = self._session_for(session_id, actor, "renter")
                require("results:rerun", actor, Resource.for_session(session))
                if session["active_run_id"] is None:
                    raise DomainError("no_run", "Chưa có vòng tìm nào; hãy xác nhận hồ sơ trước.", 409)
                run = self.repo.run(session["active_run_id"])
                if run["status"] not in {"generating", "generation_failed"}:
                    raise DomainError("retry_conflict", "Chỉ chạy lại vòng tìm đang lỗi hoặc bị treo.", 409)
                if session["profile_version"] != run["profile_version"]:
                    raise DomainError("stale_profile", "Hãy xác nhận nhu cầu mới trước khi chạy lại.")
                self.repo.invalidate(run["id"])
                new = self.repo.create_run(session, self.catalog.version)
            self._generate(new["id"])
            return self.results(session_id, actor)

    def retry(self, run_id: str, actor: Actor) -> dict:
        """Admin-only recovery: regenerate the current failed run of a session."""
        with self.lock:
            with self.repo.guard():
                require("run:retry", actor)
                self._role(actor, "admin")
                run = self.repo.run(run_id)
                session = self.repo.session(run["session_id"])
                if run["status"] not in {"generating", "generation_failed"} or session["active_run_id"] != run_id:
                    raise DomainError("retry_conflict", "Chỉ tạo lại bản hiện tại đang lỗi generation.")
                if session["profile_version"] != run["profile_version"]:
                    raise DomainError("stale_profile", "Hãy xác nhận nhu cầu mới trước khi tạo lại.")
                self.repo.invalidate(run_id)
                new = self.repo.create_run(session, self.catalog.version)
            self._generate(new["id"])
            return self._admin_projection(self.repo.run(new["id"]))

    def _admin_projection(self, run: dict) -> dict:
        """Admin/ops view of a whole run: income and the exact affordability ratio stay hidden."""
        items = [
            {**item, "cost": {**item["cost"], "affordability": {**item["cost"]["affordability"], "housing_ratio": None}}}
            if (item.get("cost") or {}).get("affordability") else item for item in run["items"]]
        return {"run_id": run["id"], "session_id": run["session_id"], "status": run["status"],
                "profile_version": run["profile_version"], "catalog_version": run["catalog_version"],
                "items": items, "diagnostics": run["diagnostics"]}

    def failed_runs(self, actor: Actor) -> list[dict]:
        with self.lock, self.repo.guard():
            require("run:retry", actor)
            self._role(actor, "admin")
            rows = self.repo.db.execute("SELECT id FROM hm_runs WHERE status IN ('generating','generation_failed')")
            return [self._admin_projection(self.repo.run(row["id"])) for row in rows]

    def rooms(self, actor: Actor) -> dict:
        with self.lock, self.repo.guard():
            require("catalog:read", actor)
            rooms = self.catalog.rooms()
            if actor.role == "owner":
                rooms = [room for room in rooms if room.landlord == actor.id]
            data = [room.model_dump(mode="json") for room in rooms]
            photos, promos = media.photos_by_owner(self.repo, "room"), promotions.active_by_room(self.repo)
            for item in data:
                item["photos"] = photos.get(item["id"], [])
                item["promotion"] = promos.get(item["id"])
            return {"rooms": data, "catalog_version": self.catalog.version,
                    "shared_catalog": actor.role == "admin"}

    def _writable_catalog(self) -> StoredCatalog:
        if not isinstance(self.catalog, StoredCatalog):
            raise DomainError("catalog_readonly", "Catalog JSON thử nghiệm chỉ đọc.", 409)
        return self.catalog

    def _require_landlord_approved(self, actor: Actor, publishing: bool):
        """BE-03: a pending/rejected landlord may draft and edit listings but
        never publish one until an admin approves the account."""
        if publishing and actor.role == "owner" and \
                auth.landlord_status(self.repo, actor.id, actor.role) != "approved":
            raise DomainError("landlord_not_approved",
                              "Tài khoản chủ nhà đang chờ quản trị viên duyệt; chưa công khai tin được.", 403)

    def change_room_status(self, room_id: str, actor: Actor, request: CatalogStatus) -> dict:
        with self.lock:
            require("catalog:write", actor)
            self._require_landlord_approved(actor, request.published is True)
            landlord = actor.id if actor.role == "owner" else None
            result = self._writable_catalog().change_status(room_id, request, landlord)
            self._sync_room_change(result["previous"], result["room"])
            return {"room": result["room"], "catalog_version": result["catalog_version"]}

    def create_room(self, actor: Actor, data: RoomInput) -> dict:
        with self.lock:
            require("catalog:write", actor)
            self._role(actor, "owner")
            # RoomInput.published defaults to False: an unapproved landlord who
            # omits the field still creates a draft listing; only an explicit
            # publish request is rejected (decision recorded in BE-03 report).
            self._require_landlord_approved(actor, data.published)
            return self._writable_catalog().create_room(actor.id, data)

    def update_room(self, room_id: str, actor: Actor, data: RoomUpdate) -> dict:
        with self.lock:
            require("catalog:write", actor)
            self._role(actor, "owner")
            # RoomUpdate replaces the full payload, so data.published is the
            # resulting publication state of the listing.
            self._require_landlord_approved(actor, data.published)
            result = self._writable_catalog().update_room(room_id, actor.id, data)
            self._sync_room_change(result["previous"], result["room"])
            return {"room": result["room"], "catalog_version": result["catalog_version"]}

    # --- Admin: landlord account review (BE-03) ---

    def landlord_applications(self, actor: Actor, status: str = "pending") -> list[dict]:
        with self.lock:
            require("account:review_landlord", actor)
            return auth.landlord_applications(self.repo, status)

    def approve_landlord(self, actor: Actor, user_id: str) -> dict:
        with self.lock:
            require("account:review_landlord", actor)
            return auth.review_landlord(self.repo, actor, user_id, "approved")

    def reject_landlord(self, actor: Actor, user_id: str, reason: str) -> dict:
        with self.lock:
            require("account:review_landlord", actor)
            return auth.review_landlord(self.repo, actor, user_id, "rejected", reason)

    def _sync_room_change(self, previous: dict, current: dict):
        """Real-time status sync: tell renters who engaged with a room about status or price changes."""
        changes = []
        if previous.get("occupancy") != current.get("occupancy") or previous.get("available") != current.get("available"):
            state = current.get("occupancy") or ("vacant" if current.get("available") else "unavailable")
            changes.append({"vacant": "đã trống trở lại", "deposited": "đã có người cọc", "rented": "đã cho thuê",
                            "unavailable": "tạm không cho thuê"}.get(state, "đổi tình trạng"))
        if previous.get("published") and not current.get("published"):
            changes.append("đã ẩn tin")
        if previous["quote"]["rent_vnd"] != current["quote"]["rent_vnd"]:
            changes.append(f"đổi giá thuê từ {previous['quote']['rent_vnd']:,} thành {current['quote']['rent_vnd']:,} đ"
                           .replace(",", "."))
        elif previous["quote"] != current["quote"]:
            changes.append("cập nhật bảng phí/chính sách")
        if not changes:
            return
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        users = {row["user_id"] for row in self.repo.db.execute(
            "SELECT DISTINCT user_id FROM hm_room_views WHERE room_id=? AND user_id IS NOT NULL AND viewed_at>=?",
            (current["id"], since))}
        users |= {row["owner_id"] for row in self.repo.db.execute(
            "SELECT DISTINCT owner_id FROM hm_viewings WHERE room_id=?", (current["id"],))}
        users |= {row["renter_id"] for row in self.repo.db.execute(
            "SELECT DISTINCT renter_id FROM hm_conversations WHERE room_id=?", (current["id"],))}
        title = current["title"].split(". ")[0]
        for user in sorted(users):
            notifications.notify(self.repo, user, "room_changed", "Phòng bạn quan tâm có thay đổi",
                                 f"{title}: " + "; ".join(changes) + ".",
                                 f"room-change:{current['id']}:{current['revision']}:{user}", "/tim-kiem")

    # --- Notifications and automation ---

    def notifications(self, actor: Actor) -> dict:
        with self.lock:
            return notifications.list_for(self.repo, actor.id)

    def read_notifications(self, actor: Actor, notification_id: str | None = None) -> dict:
        with self.lock:
            notifications.mark_read(self.repo, actor.id, notification_id)
            return notifications.list_for(self.repo, actor.id)

    def run_jobs(self, now: datetime | None = None) -> dict:
        with self.lock:
            return automation.run_due(self, now)

    def job_runs(self, actor: Actor) -> list[dict]:
        with self.lock:
            self._role(actor, "admin")
            rows = self.repo.db.execute("SELECT * FROM hm_job_runs ORDER BY started_at DESC LIMIT 20")
            return [{**dict(row), "summary": json.loads(row["summary_json"]) if row["summary_json"] else None}
                    for row in rows]

    def compare(self, session_id: str, actor: Actor, room_ids: list[str]) -> dict:
        with self.lock, self.repo.guard():
            require("compare:run", actor)
            if not 2 <= len(room_ids) <= 3 or len(room_ids) != len(set(room_ids)):
                raise DomainError("invalid_comparison", "Chọn 2–3 phòng khác nhau.", 422)
            visible = self.results(session_id, actor)
            by_id = {item["room_id"]: item for item in visible["results"]}
            if not set(room_ids).issubset(by_id):
                raise DomainError("not_visible", "Chỉ so sánh các phòng trong kết quả hiện tại.", 403)
            items = [by_id[key] for key in room_ids]
            profile = Profile.model_validate_json(self.repo.session(session_id)["profile_json"])
            amenities = {room.id: room.amenities for room in self.catalog.rooms() if room.id in room_ids}
            advice = advisor.advise([{**item, "amenities": amenities.get(item["room_id"])} for item in items],
                                    budget=profile.max_monthly_cost_vnd, preferences=profile.preferences)
            return {"run_id": visible["run_id"], "items": items, "advice": advice}

    # --- Tenant portal: filter search, listing detail, listing compare, direct viewing, handbook ---

    def search_listings(self, query: "listings.ListingQuery") -> dict:
        with self.lock:
            result = listings.search(self.catalog.rooms(), query)
            photos, promos = media.photos_by_owner(self.repo, "room"), promotions.active_by_room(self.repo)
            for item in result["items"]:
                item["photos"] = photos.get(item["id"], [])
                item["promotion"] = promos.get(item["id"])
            return result

    def _published_room(self, room_id: str):
        room = next((room for room in self.catalog.rooms() if room.id == room_id), None)
        if room is None or not room.published:
            raise DomainError("not_found", "Không tìm thấy tin.", 404)
        return room

    def listing(self, room_id: str, actor: Actor | None = None, people: int = 1) -> dict:
        with self.lock:
            room = self._published_room(room_id)
            # Views feed landlord analytics and lead follow-up; anonymous views carry no user.
            self.repo.record_view(room.id, actor.id if actor and actor.role == "renter" else None)
            if actor and actor.role == "renter":
                pms.touch_lead(self.repo, room.landlord, actor.id, room.id, "view")
            return {**listings.listing_card(room, people), "house_rules": room.house_rules,
                    "landlord_id": room.landlord, "photos": media.photos(self.repo, "room", room.id),
                    "promotion": promotions.active(self.repo, room.id),
                    "contact": self._listing_contact(room, actor)}

    def _listing_contact(self, room, actor: Actor | None) -> dict:
        """How a renter reaches the poster. Crawled listings point to the original
        post: their landlord_id is a demo account, so its phone must not be shown
        as the real poster's. Own listings show the landlord-entered phone to
        signed-in users only, so the public page cannot be scraped for it."""
        if room.source.startswith(listings.CRAWLED_SOURCE_PREFIXES):
            url = room.source if room.source.startswith("https://") else None
            return {"kind": "external", "original_url": url, "phone": None, "phone_requires_login": False}
        phone = auth.landlord_phone(self.repo, room.landlord) if room.landlord else None
        return {"kind": "landlord", "original_url": None, "phone": phone if actor else None,
                "phone_requires_login": bool(phone) and actor is None}

    # --- Danh sách cá nhân của người thuê: căn đã lưu / căn đã xem ---

    def _personal_cards(self, actor: Actor, room_ids: list[str]) -> list[dict]:
        cards = []
        for room_id in room_ids:
            try:
                room = self._published_room(room_id)
            except DomainError:
                # Tin đã bị ẩn/gỡ: bỏ khỏi danh sách hiển thị, không xoá mẫu lưu.
                continue
            cards.append({**listings.listing_card(room, 1), "room_id": room.id})
        return cards

    def saved_rooms(self, actor: Actor) -> list[dict]:
        with self.lock, self.repo.guard():
            require("saved:read", actor)
            return self._personal_cards(actor, self.repo.saved_room_ids(actor.id))

    def viewed_rooms(self, actor: Actor) -> list[dict]:
        with self.lock, self.repo.guard():
            require("viewed:read", actor)
            return self._personal_cards(actor, self.repo.viewed_room_ids(actor.id))

    def set_room_saved(self, actor: Actor, room_id: str, saved: bool) -> dict:
        with self.lock, self.repo.guard():
            require("saved:write", actor)
            room = self._published_room(room_id)
            if saved:
                self.repo.save_room(actor.id, room.id)
            else:
                self.repo.unsave_room(actor.id, room.id)
            return {"room_id": room.id, "saved": saved}

    def compare_listings(self, room_ids: list[str], people: int = 1, budget: int | None = None,
                         preferences: list[str] | None = None) -> dict:
        with self.lock:
            if not 2 <= len(room_ids) <= 3 or len(room_ids) != len(set(room_ids)):
                raise DomainError("invalid_comparison", "Chọn 2–3 phòng khác nhau.", 422)
            rooms = [self._published_room(room_id) for room_id in room_ids]
            items = [listings.listing_card(room, people) for room in rooms]
            return {"items": items, "advice": advisor.advise(items, budget=budget, preferences=preferences)}

    def request_listing_viewing(self, actor: Actor, room_id: str, requested_at: datetime,
                                idempotency_key: str, mode: str = "offline") -> dict:
        """Book straight from a published listing (filter search), without an AI shortlist."""
        with self.lock, self.repo.guard():
            require("viewing:request", actor)
            if not 1 <= len(idempotency_key) <= 100:
                raise DomainError("invalid_key", "Mã yêu cầu cần có 1–100 ký tự.", 422)
            if mode not in {"offline", "online"}:
                raise DomainError("invalid_mode", "Hình thức xem là offline hoặc online.", 422)
            if requested_at.tzinfo is None or requested_at <= datetime.now(timezone.utc):
                raise DomainError("invalid_time", "Chọn thời điểm tương lai có múi giờ.", 422)
            room = self._published_room(room_id)
            if room.available is False:
                raise DomainError("not_available", "Phòng đã cọc hoặc đã thuê.", 409)
            viewing = self.repo.create_direct_viewing(actor.id, room.id, room.landlord,
                                                      requested_at.astimezone(timezone.utc).isoformat(),
                                                      idempotency_key, mode)
            self._notify_viewing_requested(viewing)
            return self._viewing_projection(viewing)

    def handbook_answer(self, question: str, room_id: str | None = None) -> dict:
        with self.lock:
            if not question.strip() or len(question) > 1000:
                raise DomainError("invalid_message", "Câu hỏi cần có 1–1000 ký tự.", 422)
            rules = self._published_room(room_id).house_rules if room_id else None
            return handbook.answer(redact(question), rules)

    def _simulate_item(self, room, profile: Profile, *, scenario, cost_split: str, loan) -> dict:
        """One what-if cost for a room — the single calculation shared by
        HomeMatchService.simulate and the chat finance agent (AG-02). The loan
        principal stays the deterministic shortfall; no default rate is invented."""
        cost = estimate_with_affordability(
            room.quote, scenario, available_cash_vnd=profile.max_initial_cash_vnd,
            monthly_income_vnd=profile.monthly_income_vnd, cost_split=cost_split, loan=loan)
        return cost.model_dump(mode="json")

    def simulate(self, session_id: str, actor: Actor, request: SimulationRequest) -> dict:
        """What-if finance for one approved room; never changes the confirmed profile or the run."""
        with self.lock, self.repo.guard():
            require("compare:run", actor)
            visible = self.results(session_id, actor)
            if request.room_id not in {item["room_id"] for item in visible["results"]}:
                raise DomainError("not_visible", "Chỉ mô phỏng phòng trong kết quả hiện tại.", 403)
            session = self.repo.session(session_id)
            profile = Profile.model_validate_json(session["profile_json"])
            room = next(room for room in self.catalog.rooms() if room.id == request.room_id)
            items = []
            for option in request.scenarios:
                scenario = option.scenario or profile.scenario
                loan = option.loan if "loan" in option.model_fields_set else profile.loan
                items.append({"label": option.label,
                              "cost": self._simulate_item(room, profile, scenario=scenario,
                                                          cost_split=option.cost_split or profile.cost_split,
                                                          loan=loan)})
            return {"run_id": visible["run_id"], "room_id": room.id, "room_revision": room.revision,
                    "items": items}

    def request_viewing(self, session_id: str, actor: Actor, room_id: str,
                        requested_at: datetime, idempotency_key: str, mode: str = "offline") -> dict:
        with self.lock, self.repo.guard():
            session = self._session_for(session_id, actor, "renter")
            require("viewing:request", actor, Resource.for_session(session))
            if not 1 <= len(idempotency_key) <= 100:
                raise DomainError("invalid_key", "Mã yêu cầu cần có 1–100 ký tự.", 422)
            if requested_at.tzinfo is None or requested_at <= datetime.now(timezone.utc):
                raise DomainError("invalid_time", "Chọn thời điểm tương lai có múi giờ.", 422)
            if mode not in {"offline", "online"}:
                raise DomainError("invalid_mode", "Hình thức xem là offline hoặc online.", 422)
            result = self.results(session_id, actor)
            visible = {item["room_id"]: item for item in result["results"]}
            if room_id not in visible:
                raise DomainError("not_visible", "Phòng chưa thuộc bản gợi ý hiện tại.", 403)
            landlord = visible[room_id].get("landlord_id") or DEFAULT_LANDLORD
            viewing = self.repo.create_viewing(session, result["run_id"], room_id,
                                               requested_at.astimezone(timezone.utc).isoformat(), idempotency_key,
                                               landlord, mode)
            self._notify_viewing_requested(viewing)
            return self._viewing_projection(viewing)

    def respond_viewing(self, viewing_id: str, actor: Actor, status: str) -> dict:
        with self.lock, self.repo.guard():
            require("viewing:respond", actor)
            viewing = self.repo.viewing(viewing_id)
            # Only the landlord of the viewed room answers the request.
            if viewing["landlord_id"] != actor.id:
                raise DomainError("forbidden", "Bạn không có quyền xem phiên này.", 403)
            if status not in {"confirmed", "declined"}:
                raise DomainError("invalid_status", "Phản hồi phải là confirmed hoặc declined.", 422)
            if status == "confirmed":
                if viewing["run_id"] and not self._fresh(self.repo.run(viewing["run_id"])):
                    raise DomainError("stale_viewing", "Kho phòng hoặc nhu cầu đã đổi; cần kiểm tra lại trước khi hẹn.")
                if not viewing["run_id"]:
                    room = next((room for room in self.catalog.rooms() if room.id == viewing["room_id"]), None)
                    if room is None or not room.published or room.available is False:
                        raise DomainError("stale_viewing", "Tin đã ẩn hoặc phòng không còn trống.")
            updated = self.repo.respond_viewing(viewing_id, status)
            notifications.notify(self.repo, updated["owner_id"], "viewing_" + status,
                                 "Lịch xem đã được xác nhận" if status == "confirmed" else "Chủ nhà chưa nhận lịch xem",
                                 f"Phòng {updated['room_id']}: "
                                 + ("chủ nhà đã xác nhận lịch xem." if status == "confirmed"
                                    else "chủ nhà chưa nhận thời gian này, bạn có thể chọn giờ khác."),
                                 f"viewing:{viewing_id}:{status}", "/nguoi-thue/lich-xem", email=True)
            return self._viewing_projection(updated)

    def viewings(self, actor: Actor) -> list[dict]:
        with self.lock:
            require("viewing:read", actor)
            return [self._viewing_projection(item) for item in self.repo.viewings(actor.id, actor.role)]

    def viewing(self, viewing_id: str, actor: Actor) -> dict:
        with self.lock:
            item = self.repo.viewing(viewing_id)
            require("viewing:read", actor)
            if actor.role == "owner":
                if item["landlord_id"] != actor.id:
                    raise DomainError("forbidden", "Bạn không có quyền xem phiên này.", 403)
            elif actor.role != "renter" or item["owner_id"] != actor.id:
                raise DomainError("forbidden", "Bạn không có quyền xem phiên này.", 403)
            return self._viewing_projection(item)

    def _notify_viewing_requested(self, viewing: dict):
        pms.touch_lead(self.repo, viewing["landlord_id"], viewing["owner_id"], viewing["room_id"], "viewing", "viewing")
        notifications.notify(self.repo, viewing["landlord_id"], "viewing_requested", "Yêu cầu xem phòng mới",
                             f"Khách muốn xem phòng {viewing['room_id']} "
                             + ("trực tuyến." if viewing["mode"] == "online" else "trực tiếp."),
                             f"viewing:{viewing['id']}:requested", "/chu-nha/lich-xem", email=True)

    @staticmethod
    def _viewing_projection(viewing: dict) -> dict:
        return {key: viewing.get(key) for key in ("id", "session_id", "run_id", "room_id", "requested_at", "status",
                                                 "landlord_id", "mode", "meeting_url")}

    @staticmethod
    def _support_projection(ticket: dict) -> dict:
        return {key: ticket.get(key) for key in ("id", "session_id", "manager_id", "status", "assignee",
                                                 "note", "created_at", "updated_at", "resolved_at")}

    def support_tickets(self, actor: Actor, status: str | None = None) -> list[dict]:
        with self.lock:
            require("support:list", actor)
            # Platform-level handoff tickets; landlord conversations replace them for room questions.
            return [self._support_projection(ticket) for ticket in
                    self.repo.support_tickets(None if actor.role == "admin" else actor.id, status)]

    def update_support_ticket(self, actor: Actor, ticket_id: str, update) -> dict:
        """BE-04: admin lifecycle transition for one handoff support ticket."""
        with self.lock:
            require("support:manage", actor)
            ticket = self.repo.support_ticket(ticket_id)
            if ticket is None:
                raise DomainError("not_found", "Không tìm thấy ticket hỗ trợ.", 404)
            target = update.status
            if target == ticket["status"]:
                # Replaying the current status is idempotent: no write, no notification.
                return self._support_projection(ticket)
            if target not in SUPPORT_TRANSITIONS[ticket["status"]]:
                raise DomainError("ticket_state",
                                  f"Không chuyển được ticket từ {ticket['status']} sang {target}.", 409)
            note = update.note.strip() if update.note else None
            if target == "resolved" and not note:
                raise DomainError("note_required",
                                  "Cần ghi chú xử lý khi đánh dấu ticket đã giải quyết.", 422)
            now = datetime.now(timezone.utc).isoformat()
            updates = {"status": target, "updated_at": now}
            if target == "in_progress":
                updates["assignee"] = actor.id
                updates["resolved_at"] = None
            if note:
                updates["note"] = note
            if target == "resolved":
                updates["resolved_at"] = now
            ticket = self.repo.update_support(ticket_id, updates)
            # The renter who owns the session is notified once per status (dedup key).
            session = self.repo.session(ticket["session_id"])
            notifications.notify(self.repo, session["owner_id"], "support_update",
                                 "Cập nhật yêu cầu gặp nhân viên",
                                 "Nhân viên đã tiếp nhận yêu cầu của bạn và sẽ liên hệ sớm."
                                 if target == "in_progress" else
                                 "Yêu cầu gặp nhân viên của bạn đã được xử lý xong.",
                                 f"support:{ticket_id}:{target}", "/tro-ly-ai")
            return self._support_projection(ticket)

    # --- Live chat with landlords and smart handover ---

    def start_conversation(self, actor: Actor, room_id: str, session_id: str | None = None) -> dict:
        with self.lock:
            self._role(actor, "renter")
            room = self._published_room(room_id)
            context = {"room": {"id": room.id, "title": room.title.split(". ")[0], "area": room.area,
                                "city": room.city, "rent_vnd": room.quote.rent_vnd}}
            if session_id:
                session = self._session_for(session_id, actor, "renter")
                profile = json.loads(session["profile_json"]) if session["profile_json"] else None
                context["needs"] = conversations.needs_summary(profile)
                if session["active_run_id"]:
                    run = self.repo.run(session["active_run_id"])
                    item = next((item for item in run["items"] if item["room_id"] == room.id), None)
                    affordability = ((item or {}).get("cost") or {}).get("affordability") or {}
                    # The landlord gets the band only, like in review: never income or the exact ratio.
                    context["affordability_band"] = affordability.get("band")
                rows = self.repo.db.execute("SELECT speaker,text FROM hm_chat_transcripts WHERE session_id=? "
                                            "ORDER BY created_at DESC LIMIT 6", (session_id,)).fetchall()
                context["recent_ai_chat"] = [dict(row) for row in reversed(rows)]
            conversation = conversations.start(self.repo, actor.id, room.landlord, room.id, session_id, context)
            pms.touch_lead(self.repo, room.landlord, actor.id, room.id, "chat", "contacted")
            notifications.notify(self.repo, room.landlord, "conversation_started", "Khách muốn trao đổi",
                                 f"Khách hỏi về {context['room']['title']}; ngữ cảnh từ trợ lý đã được chuyển kèm.",
                                 f"conversation:{conversation['id']}", "/chu-nha/hop-thu")
            return conversations.projection(self.repo, conversation, "renter")

    def conversations(self, actor: Actor) -> list[dict]:
        with self.lock:
            column, side = {"renter": ("renter_id", "renter"), "owner": ("landlord_id", "landlord")}.get(
                actor.role, (None, None))
            if column is None:
                raise DomainError("forbidden", "Vai trò không được phép thực hiện thao tác này.", 403)
            rows = self.repo.db.execute(f"SELECT * FROM hm_conversations WHERE {column}=? "
                                        "ORDER BY last_message_at DESC", (actor.id,))
            return [conversations.projection(self.repo, dict(row), side) for row in rows]

    def conversation_messages(self, actor: Actor, conversation_id: str, after: str | None = None) -> dict:
        with self.lock:
            conversation = conversations.get(self.repo, conversation_id)
            side = conversations.authorize(conversation, actor)
            items = conversations.messages(self.repo, conversation_id, after)
            conversations.mark_read(self.repo, conversation_id, side)
            return {"conversation": conversations.projection(self.repo, conversations.get(self.repo, conversation_id),
                                                             side), "messages": items}

    def send_conversation_message(self, actor: Actor, conversation_id: str, body: str) -> dict:
        with self.lock:
            conversation = conversations.get(self.repo, conversation_id)
            side = conversations.authorize(conversation, actor)
            message = conversations.send(self.repo, conversation, actor, side, body)
            recipient = conversation["landlord_id"] if side == "renter" else conversation["renter_id"]
            notifications.notify(self.repo, recipient, "message", "Tin nhắn mới",
                                 conversations.mask_pii(message["body"])[:140], f"message:{message['id']}",
                                 "/chu-nha/hop-thu" if side == "renter" else "/tin-nhan")
            return message

    # --- Landlord PMS: leases, billing, maintenance, CRM, dashboard ---

    def _owner(self, actor: Actor):
        self._role(actor, "owner")

    def _set_occupancy(self, room_id: str, occupancy: str):
        catalog = self._writable_catalog()
        room = catalog.room(room_id)
        if room.occupancy != occupancy:
            result = catalog.change_status(room_id, CatalogStatus(expected_revision=room.revision,
                                                                  occupancy=occupancy))
            self._sync_room_change(result["previous"], result["room"])

    def leases(self, actor: Actor) -> list[dict]:
        with self.lock:
            return pms.leases(self.repo, actor)

    def lease(self, actor: Actor, lease_id: str) -> dict:
        with self.lock:
            return pms.lease_for(self.repo, lease_id, actor)

    def create_lease(self, actor: Actor, data: "pms.LeaseInput") -> dict:
        with self.lock:
            self._owner(actor)
            room = self._writable_catalog().room(data.room_id)
            item = pms.create_lease(self.repo, room, actor.id, data)
            pms.touch_lead(self.repo, actor.id, data.renter_id, room.id, "lease", "negotiating")
            return item

    def update_lease(self, actor: Actor, lease_id: str, data: "pms.LeaseInput") -> dict:
        with self.lock:
            self._owner(actor)
            return pms.update_lease(self.repo, pms.lease_for(self.repo, lease_id, actor), data)

    def send_lease(self, actor: Actor, lease_id: str) -> dict:
        with self.lock:
            self._owner(actor)
            item = pms.set_lease_status(self.repo, pms.lease_for(self.repo, lease_id, actor), "sent", ("draft",))
            notifications.notify(self.repo, item["renter_id"], "lease_sent", "Chủ nhà gửi hợp đồng thuê",
                                 f"Hợp đồng phòng {item['room_id']} (phiên bản {item['version']}) chờ bạn xem và chấp thuận.",
                                 f"lease:{item['id']}:v{item['version']}:sent", "/nguoi-thue/hop-dong", email=True)
            return item

    def accept_lease(self, actor: Actor, lease_id: str, expected_version: int) -> dict:
        with self.lock:
            self._role(actor, "renter")
            item = pms.lease_for(self.repo, lease_id, actor)
            if item["version"] != expected_version:
                raise DomainError("lease_version", "Hợp đồng đã được sửa; hãy đọc lại phiên bản mới.", 409)
            item = pms.set_lease_status(self.repo, item, "accepted", ("sent",),
                                        renter_accepted_version=expected_version)
            notifications.notify(self.repo, item["landlord_id"], "lease_accepted", "Khách đã chấp thuận hợp đồng",
                                 f"Hợp đồng phòng {item['room_id']} đã được chấp thuận, có thể kích hoạt.",
                                 f"lease:{item['id']}:v{item['version']}:accepted", "/chu-nha/hop-dong")
            return item

    def activate_lease(self, actor: Actor, lease_id: str) -> dict:
        with self.lock:
            self._owner(actor)
            item = pms.lease_for(self.repo, lease_id, actor)
            if item["renter_accepted_version"] != item["version"]:
                raise DomainError("lease_not_accepted", "Khách chưa chấp thuận đúng phiên bản hiện tại.", 409)
            item = pms.set_lease_status(self.repo, item, "active", ("accepted",))
            if item["renewal_of"]:
                previous = pms.lease(self.repo, item["renewal_of"])
                if previous["status"] == "active":
                    pms.set_lease_status(self.repo, previous, "ended", ("active",), ended_at=pms.utc_now())
            self._set_occupancy(item["room_id"], "rented")
            pms.touch_lead(self.repo, actor.id, item["renter_id"], item["room_id"], "lease", "won")
            notifications.notify(self.repo, item["renter_id"], "lease_active", "Hợp đồng đã có hiệu lực",
                                 f"Hợp đồng phòng {item['room_id']} có hiệu lực từ {item['start_date']}.",
                                 f"lease:{item['id']}:active", "/nguoi-thue/hop-dong", email=True)
            return item

    def renew_lease(self, actor: Actor, lease_id: str, data: "pms.LeaseRenewal") -> dict:
        with self.lock:
            self._owner(actor)
            item = pms.lease_for(self.repo, lease_id, actor)
            if item["status"] != "active":
                raise DomainError("lease_state", "Chỉ gia hạn hợp đồng đang hiệu lực.", 409)
            room = self._writable_catalog().room(item["room_id"])
            renewal = pms.LeaseInput(renter_id=item["renter_id"], room_id=item["room_id"],
                                     start_date=item["end_date"], end_date=data.end_date,
                                     rent_vnd=data.rent_vnd or item["rent_vnd"], deposit_vnd=item["deposit_vnd"],
                                     payment_day=item["payment_day"], occupants=item["occupants"],
                                     vehicles=item["vehicles"], terms=item["terms"])
            return pms.create_lease(self.repo, room, actor.id, renewal, renewal_of=item["id"])

    def terminate_lease(self, actor: Actor, lease_id: str, data: "pms.LeaseTermination") -> dict:
        with self.lock:
            self._owner(actor)
            item = pms.lease_for(self.repo, lease_id, actor)
            item = pms.set_lease_status(self.repo, item, "terminated", ("active", "accepted", "sent", "draft"),
                                        end_date=data.end_date.isoformat(), ended_at=pms.utc_now(),
                                        settlement_note=data.settlement_note)
            active = self.repo.db.execute("SELECT 1 FROM hm_leases WHERE room_id=? AND status='active'",
                                          (item["room_id"],)).fetchone()
            if not active:
                self._set_occupancy(item["room_id"], "vacant")
            notifications.notify(self.repo, item["renter_id"], "lease_terminated", "Hợp đồng đã thanh lý",
                                 f"Hợp đồng phòng {item['room_id']} kết thúc ngày {item['end_date']}. "
                                 f"Ghi chú quyết toán: {item['settlement_note']}",
                                 f"lease:{item['id']}:terminated", "/nguoi-thue/hop-dong", email=True)
            return item

    def lease_document(self, actor: Actor, lease_id: str) -> dict:
        with self.lock:
            item = pms.lease_for(self.repo, lease_id, actor)
            title = self.catalog.room(item["room_id"]).title.split(". ")[0] \
                if isinstance(self.catalog, StoredCatalog) else item["room_id"]
            return {"html": pms.lease_document(item, title)}

    def record_reading(self, actor: Actor, lease_id: str, data: "pms.ReadingInput") -> dict:
        with self.lock:
            self._owner(actor)
            return pms.record_reading(self.repo, pms.lease_for(self.repo, lease_id, actor), data, actor.id)

    def issue_invoice(self, actor: Actor, lease_id: str, data: "pms.InvoiceInput") -> dict:
        with self.lock:
            self._owner(actor)
            item = pms.issue_invoice(self.repo, pms.lease_for(self.repo, lease_id, actor), data)
            notifications.notify(self.repo, item["renter_id"], "invoice_issued", f"Hóa đơn kỳ {item['period']}",
                                 f"Tổng {pms.money(item['total_vnd'])}, hạn thanh toán {item['due_date']}.",
                                 f"invoice:{item['id']}:issued", "/nguoi-thue/hoa-don", email=True)
            return item

    def invoices(self, actor: Actor) -> list[dict]:
        with self.lock:
            return pms.invoices(self.repo, actor)

    def invoice_detail(self, actor: Actor, invoice_id: str) -> dict:
        with self.lock:
            item = pms.invoice_for(self.repo, invoice_id, actor)
            return {**item, "payments": pms.payments(self.repo, invoice_id)}

    def invoice_document(self, actor: Actor, invoice_id: str, receipt_no: str | None = None) -> dict:
        with self.lock:
            item = pms.invoice_for(self.repo, invoice_id, actor)
            if receipt_no:
                payment = next((p for p in pms.payments(self.repo, invoice_id) if p["receipt_no"] == receipt_no), None)
                if payment is None:
                    raise DomainError("not_found", "Không tìm thấy biên lai.", 404)
                return {"html": pms.receipt_document(item, payment)}
            title = self.catalog.room(item["room_id"]).title.split(". ")[0] \
                if isinstance(self.catalog, StoredCatalog) else item["room_id"]
            return {"html": pms.invoice_document(item, title)}

    def record_payment(self, actor: Actor, invoice_id: str, data: "pms.PaymentInput") -> dict:
        with self.lock:
            self._owner(actor)
            item = pms.invoice_for(self.repo, invoice_id, actor)
            payment = pms.record_payment(self.repo, item, data, actor.id)
            self._notify_receipt(item, payment)
            return payment

    def _notify_receipt(self, item: dict, payment: dict):
        notifications.notify(self.repo, item["renter_id"], "payment_received", "Chủ nhà đã xác nhận nhận tiền",
                             f"Biên lai {payment['receipt_no']}: {pms.money(payment['amount_vnd'])} cho kỳ {item['period']}.",
                             f"payment:{payment['id']}", "/nguoi-thue/hoa-don", email=True)

    def claim_payment(self, actor: Actor, invoice_id: str, data: "pms.ClaimInput") -> dict:
        with self.lock:
            self._role(actor, "renter")
            item = pms.invoice_for(self.repo, invoice_id, actor)
            claim = pms.claim_payment(self.repo, item, actor.id, data)
            notifications.notify(self.repo, item["landlord_id"], "payment_claimed", "Khách báo đã chuyển tiền",
                                 f"Kỳ {item['period']}: {pms.money(data.amount_vnd)}. Kiểm tra tài khoản rồi xác nhận.",
                                 f"claim:{claim['id']}", "/chu-nha/hoa-don")
            return claim

    def payment_claims(self, actor: Actor) -> list[dict]:
        with self.lock:
            return pms.claims(self.repo, actor)

    def decide_claim(self, actor: Actor, claim_id: str, confirm: bool) -> dict:
        """Reconciliation: a renter's 'đã chuyển' becomes a payment only when the landlord confirms receipt."""
        with self.lock:
            self._owner(actor)
            claim = next((c for c in pms.claims(self.repo, actor) if c["id"] == claim_id), None)
            if claim is None:
                raise DomainError("not_found", "Không tìm thấy báo chuyển tiền.", 404)
            if claim["status"] != "pending":
                raise DomainError("claim_decided", "Báo chuyển tiền đã được xử lý.", 409)
            item = pms.invoice_for(self.repo, claim["invoice_id"], actor)
            payment = None
            if confirm:
                payment = pms.record_payment(self.repo, item, pms.PaymentInput(
                    amount_vnd=min(claim["amount_vnd"], item["balance_vnd"]), method="transfer",
                    reference=claim["reference"]), actor.id, claim_id)
                self._notify_receipt(item, payment)
            else:
                notifications.notify(self.repo, claim["renter_id"], "payment_claim_rejected",
                                     "Chủ nhà chưa nhận được khoản chuyển",
                                     f"Kỳ {item['period']}: chủ nhà chưa thấy khoản {pms.money(claim['amount_vnd'])}; "
                                     "vui lòng kiểm tra lại.", f"claim:{claim_id}:rejected", "/nguoi-thue/hoa-don")
            with self.repo.db:
                self.repo.db.execute("UPDATE hm_payment_claims SET status=?,decided_at=? WHERE id=?",
                                     ("confirmed" if confirm else "rejected", pms.utc_now(), claim_id))
            return {"claim_id": claim_id, "status": "confirmed" if confirm else "rejected", "payment": payment}

    def billing_summary(self, actor: Actor) -> dict:
        with self.lock:
            self._owner(actor)
            return pms.billing_summary(self.repo, actor.id)

    def tickets(self, actor: Actor) -> list[dict]:
        with self.lock:
            items = pms.tickets(self.repo, actor)
            for item in items:
                item["photos"] = media.photos(self.repo, "maintenance", item["id"])
            return items

    def create_ticket(self, actor: Actor, data: "pms.TicketInput") -> dict:
        with self.lock:
            self._role(actor, "renter")
            room = self._writable_catalog().room(data.room_id)
            item = pms.create_ticket(self.repo, room, actor.id, data)
            notifications.notify(self.repo, item["landlord_id"],
                                 "maintenance_urgent" if item["priority"] == "urgent" else "maintenance",
                                 ("KHẨN: " if item["priority"] == "urgent" else "") + "Yêu cầu sửa chữa mới",
                                 f"Phòng {item['room_id']}: {item['title']}", f"ticket:{item['id']}:submitted",
                                 "/chu-nha/sua-chua", email=item["priority"] == "urgent")
            return item

    def update_ticket(self, actor: Actor, ticket_id: str, data: "pms.TicketUpdate") -> dict:
        with self.lock:
            item = pms.ticket(self.repo, ticket_id)
            if not ((actor.role == "owner" and item["landlord_id"] == actor.id)
                    or (actor.role == "renter" and item["renter_id"] == actor.id)):
                raise DomainError("not_found", "Không tìm thấy yêu cầu sửa chữa.", 404)
            updated = pms.update_ticket(self.repo, item, actor, data)
            recipient = updated["renter_id"] if actor.role == "owner" else updated["landlord_id"]
            notifications.notify(self.repo, recipient, "maintenance_update", "Cập nhật yêu cầu sửa chữa",
                                 f"{updated['title']}: {updated['status']}"
                                 + (f" · {data.note}" if data.note else ""),
                                 f"ticket:{ticket_id}:{len(updated['timeline'])}",
                                 "/nguoi-thue/sua-chua" if actor.role == "owner" else "/chu-nha/sua-chua")
            return updated

    def leads(self, actor: Actor) -> list[dict]:
        with self.lock:
            self._owner(actor)
            return pms.leads(self.repo, actor.id)

    def update_lead(self, actor: Actor, lead_id: str, data: "pms.LeadUpdate") -> dict:
        with self.lock:
            self._owner(actor)
            return pms.update_lead(self.repo, actor.id, lead_id, data)

    def landlord_dashboard(self, actor: Actor) -> dict:
        with self.lock:
            self._owner(actor)
            return pms.dashboard(self.repo, self.catalog.rooms(), actor.id)

    def landlord_analytics(self, actor: Actor) -> dict:
        with self.lock:
            self._owner(actor)
            return pms.analytics(self.repo, self.catalog.rooms(), actor.id)

    # --- Landlord AI co-pilot ---

    def _own_room(self, actor: Actor, room_id: str):
        self._owner(actor)
        room = self._writable_catalog().room(room_id)
        if room.landlord != actor.id:
            raise DomainError("not_found", "Không tìm thấy phòng.", 404)
        return room

    def marketing_post(self, actor: Actor, room_id: str, channel: str) -> dict:
        with self.lock:
            room = self._own_room(actor, room_id)
            base = os.getenv("HOMEMATCH_PUBLIC_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
            return copilot.marketing_post(self.catalog.rooms(), room, channel, f"{base}/tin/{room.id}")

    def price_advice(self, actor: Actor, room_id: str) -> dict:
        with self.lock:
            return copilot.price_advice(self.catalog.rooms(), self._own_room(actor, room_id))

    def landlord_assistant(self, actor: Actor, question: str) -> dict:
        with self.lock:
            self._owner(actor)
            if not question.strip() or len(question) > 1000:
                raise DomainError("invalid_message", "Câu hỏi cần có 1–1000 ký tự.", 422)
            rooms = self.catalog.rooms()
            return copilot.assistant(self.repo, rooms, actor.id, redact(question),
                                     pms.dashboard(self.repo, rooms, actor.id))

    # --- Listing and maintenance media (BE-06) ---

    def upload_room_media(self, actor: Actor, room_id: str, upload) -> tuple[dict, bool]:
        with self.lock:
            room = self._own_room(actor, room_id)
            return media.store(self.repo, "room", room.id, actor.id, upload.file)

    def delete_room_media(self, actor: Actor, room_id: str, media_id: str) -> None:
        with self.lock:
            self._own_room(actor, room_id)
            record = media.get(self.repo, media_id)
            if record["owner_kind"] != "room" or record["owner_id"] != room_id:
                raise DomainError("not_found", "Không tìm thấy ảnh.", 404)
            media.delete(self.repo, media_id)

    def reorder_room_media(self, actor: Actor, room_id: str, media_ids: list[str]) -> list[dict]:
        with self.lock:
            room = self._own_room(actor, room_id)
            return media.reorder(self.repo, "room", room.id, media_ids)

    def upload_maintenance_media(self, actor: Actor, ticket_id: str, upload) -> tuple[dict, bool]:
        """Photos of a maintenance ticket: the renter of the active lease or the room's landlord."""
        with self.lock:
            row = self.repo.db.execute("SELECT * FROM hm_maintenance WHERE id=?", (ticket_id,)).fetchone()
            if row is None:
                raise DomainError("not_found", "Không tìm thấy yêu cầu sửa chữa.", 404)
            ticket = dict(row)
            renter_allowed = (
                actor.role == "renter" and ticket["renter_id"] == actor.id
                and self.repo.db.execute("SELECT 1 FROM hm_leases WHERE room_id=? AND renter_id=? AND status='active'",
                                         (ticket["room_id"], actor.id)).fetchone() is not None)
            if ticket["landlord_id"] != actor.id and not renter_allowed:
                raise DomainError("not_found", "Không tìm thấy yêu cầu sửa chữa.", 404)
            return media.store(self.repo, "maintenance", ticket["id"], actor.id, upload.file)

    def media_file(self, media_id: str, actor: Actor | None) -> tuple[dict, str]:
        """Visibility of one media file: public listing photos need no token,
        non-public listing photos stay landlord-only, maintenance photos stay
        between the two parties; everyone else gets the same 404 as a missing file.
        Returns (record, cache_scope) with cache_scope "public" or "private"."""
        with self.lock:
            record = media.get(self.repo, media_id)
            if record["owner_kind"] == "room":
                room = next((room for room in self.catalog.rooms() if room.id == record["owner_id"]), None)
                if room is None:
                    raise DomainError("not_found", "Không tìm thấy ảnh.", 404)
                if room.published:
                    return record, "public"
                if actor is None or actor.role != "owner" or room.landlord != actor.id:
                    raise DomainError("not_found", "Không tìm thấy ảnh.", 404)
                return record, "private"
            ticket = pms.ticket(self.repo, record["owner_id"])  # 404 for a missing ticket
            if actor is None or actor.id not in (ticket["renter_id"], ticket["landlord_id"]):
                raise DomainError("not_found", "Không tìm thấy ảnh.", 404)
            return record, "private"

    # --- Landlord promotion per listing (BE-07) ---

    def set_promotion(self, actor: Actor, room_id: str, data) -> dict:
        with self.lock:
            room = self._own_room(actor, room_id)
            return promotions.set_promotion(self.repo, room.id, actor.id, data.text, data.valid_until)

    def delete_promotion(self, actor: Actor, room_id: str) -> None:
        with self.lock:
            room = self._own_room(actor, room_id)
            promotions.delete_promotion(self.repo, room.id)

    # --- Admin console ---

    def admin_transcripts(self, actor: Actor, limit: int = 50) -> list[dict]:
        with self.lock:
            self._role(actor, "admin")
            self.purge_transcripts()
            rows = self.repo.db.execute("SELECT session_id,user_id,COUNT(*) AS turns,MIN(created_at) AS started_at,"
                                        "MAX(created_at) AS last_at,SUM(CASE WHEN agent='quarantine' THEN 1 ELSE 0 END) "
                                        "AS flagged FROM hm_chat_transcripts GROUP BY session_id,user_id "
                                        "ORDER BY last_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in rows]

    def admin_transcript(self, actor: Actor, session_id: str) -> dict:
        with self.lock:
            self._role(actor, "admin")
            rows = [dict(row) for row in self.repo.db.execute(
                "SELECT speaker,text,intent,agent,created_at FROM hm_chat_transcripts WHERE session_id=? "
                "ORDER BY created_at,speaker DESC", (session_id,))]
            if not rows:
                raise DomainError("not_found", "Không có hội thoại cho phiên này.", 404)
            # Every admin read of a transcript is itself audited.
            with self.repo.db:
                record_audit(self.repo, actor, "transcript.viewed", "session", session_id)
            return {"session_id": session_id, "retention_days": CHAT_RETENTION_DAYS, "turns": rows}

    def admin_handovers(self, actor: Actor) -> dict:
        with self.lock:
            self._role(actor, "admin")
            return conversations.handover_report(self.repo)

    def admin_users(self, actor: Actor) -> list[dict]:
        with self.lock:
            self._role(actor, "admin")
            rows = self.repo.db.execute("SELECT u.id,u.role,p.status,p.display_name,p.email_verified "
                                        "FROM hm_users u LEFT JOIN hm_account_profiles p ON p.user_id=u.id ORDER BY u.id")
            return [{**dict(row), "status": row["status"] or "active"} for row in rows]

    @staticmethod
    def _config(run_id: str) -> dict:
        return {"configurable": {"thread_id": f"recommendation:{run_id}"}}

    def _build_chat_graph(self):
        # Graph-only imports (AG-02): loan parsing stays with the interpreter and
        # the finance room-id pattern with the guard, outside other service code.
        from .interpreter import merge_loan_terms, parse_loan_terms

        def route(state: ChatState):
            # Supervisor: explicit cost/support intents route without any model call;
            # otherwise the needs agent's extraction decides the intent.
            if state.get("intent"):
                return {}
            if isinstance(self.interpreter, (DemoInterpreter, OpenAIInterpreter)):
                draft = json.loads(self.repo.session(state["session_id"])["draft_json"])
                extracted = state["toolbox"].call("needs", "extract_needs", self.interpreter.extract,
                                                  state["text"], draft)
            else:
                extracted = state["toolbox"].call("needs", "extract_needs", self.interpreter.extract, state["text"])
            # Model output is data: redacted before it enters graph state and
            # stripped of any privilege semantics (Extraction schema has none).
            return {"intent": extracted.intent, "provenance": stamp(
                        "interpreter", "route", interpreter_mode=self.interpreter.mode),
                    "extraction": redact_tree(extracted.model_dump(mode="json"))}

        def interview(state: ChatState):
            session = self.repo.session(state["session_id"])
            require("chat:message", state["actor"], Resource.for_session(session))
            draft = DraftProfile.model_validate_json(session["draft_json"])
            extracted = state.get("extraction", {})
            touched = set()
            for key in ("city", "area", "people", "room_type", "bedrooms"):
                if extracted.get(key) is not None:
                    setattr(draft, key, extracted[key])
                    touched.add(key)
            if not draft.city and draft.area:
                # A named district pins its single city deterministically; this is
                # alias resolution, never a default when nothing was named.
                pinned = city_for_area(draft.area)
                if pinned:
                    draft.city = pinned
                    touched.add("city")
            added = set(extracted.get("preferences", [])) & AMENITIES
            removed = set(extracted.get("remove_preferences", [])) & AMENITIES
            if added or removed:
                draft.preferences = sorted((set(draft.preferences) | added) - removed)
                touched.add("preferences")
            if extracted.get("soft_description"):
                # Free text never carries contacts or money into the draft.
                draft.soft_description = redact(extracted["soft_description"])
                touched.add("soft_description")
            if extracted.get("destination_text"):
                # AG-01: tra danh mục điểm mốc tĩnh (không gọi API trả phí) → điểm
                # đến có tọa độ, xếp hạng theo khoảng cách ở vòng tìm tiếp theo.
                place = resolve_place(extracted["destination_text"], draft.city)
                if place:
                    draft.destination = Destination(
                        label=place["label"], latitude=place["latitude"], longitude=place["longitude"],
                        uncertainty_m=place["uncertainty_m"], max_distance_m=3000)
                    draft.needs_destination = False
                    touched.add("destination")
            if extracted.get("needs_destination"):
                draft.needs_destination = True
                touched.add("needs_destination")
            if extracted.get("accept_estimated_data"):
                draft.accept_estimated_data = True
                touched.add("accept_estimated_data")
            # Cờ chỉ True khi lượt này THỰC SỰ áp được một mức tiền (tuyệt đối
            # hoặc tương đối đã tính) — FE chỉ được đưa hint vào trần khi thấy cờ.
            budget_explicit = False
            needs_budget_baseline = False
            # AG-02: tiền TƯƠNG ĐỐI ưu tiên trước số tuyệt đối trong cùng câu —
            # "nới thêm 1 triệu" KHÔNG được đọc thành trần 1 triệu. Parse từ câu
            # GỐC (state["relative_budget"], state["text"] đã redact mất số);
            # cộng/trừ vào mức cũ đã nêu, chưa có mức cũ thì hỏi lại, không đoán.
            change = state.get("relative_budget")
            if change:
                # Câu nới/giảm: chỉ áp khi có mức cũ hoặc là mức mới rõ ("xuống N");
                # chưa có mức cũ thì hỏi lại — tuyệt đối không dùng số trong câu
                # làm trần (chính là bug "nới thêm 1 triệu" đọc thành trần 1 triệu).
                if change["direction"] == "set" or draft.budget_hint_vnd:
                    if change["direction"] == "set":
                        draft.budget_hint_vnd = change["amount_vnd"]
                    else:
                        delta = change["amount_vnd"] * (1 if change["direction"] == "up" else -1)
                        draft.budget_hint_vnd = max(1, draft.budget_hint_vnd + delta)
                    touched.add("budget_hint")
                    budget_explicit = True
                else:
                    needs_budget_baseline = True
            elif state.get("budget_hint"):
                draft.budget_hint_vnd = state["budget_hint"]
                touched.add("budget_hint")
                budget_explicit = True
            # Revalidate model output before saving. A hint never becomes a confirmed budget.
            draft = DraftProfile.model_validate(draft.model_dump())
            evidence = f"chat:r{session['draft_revision'] + 1}"
            for field in touched:
                draft.field_status[field] = "inferred"
                draft.evidence_ref[field] = evidence
            state["toolbox"].call("needs", "update_draft", self.repo.update_draft,
                                  session["id"], draft, session["draft_revision"])
            questions = self._questions(session["id"], has_changes=bool(touched))
            if needs_budget_baseline:
                # Không có mức cũ để nới/giảm: hỏi rõ, không đoán (AG-02).
                questions = ["Mình chưa nắm mức tổng tháng hiện tại của bạn; cho mình biết mức muốn áp "
                             "(ví dụ “tổng tháng 4,5 triệu”) rồi mình nới/giảm theo."]
            # AG-11: tối đa 1 câu làm rõ/lượt; tự chấp nhận khi p_max đủ cao thì
            # nói rõ giả định thay vì hỏi.
            clarification = None
            if not needs_budget_baseline:
                payload = self._clarification_payload(session["id"])
                if payload and payload.get("assumed"):
                    questions.append(f"Mình đang hiểu: {payload['assumed']} — sai thì bấm sửa.")
                    questions = questions[-2:]
                elif payload:
                    # Chip làm rõ render TRÊN ĐẦU câu trả lời ở FE; câu hỏi thường
                    # vẫn giữ nguyên bên dưới (không thay thế).
                    clarification = payload
            return {"response": {"intent": "find_room", "status": "needs_clarification",
                    "interpreter_mode": self.interpreter.mode, "questions": questions,
                    "clarification": clarification,
                    "budget_explicit": budget_explicit or None},
                    "provenance": stamp("interpreter", "interview", interpreter_mode=self.interpreter.mode,
                                        **state["toolbox"].summary("needs"))}

        SIMULATION_LABEL = "Mô phỏng vay qua chat"
        LOAN_BAND_VI = {"phu_hop": "trong mức khuyến nghị", "can_nhac": "cần cân nhắc",
                        "vuot": "vượt mức khuyến nghị", "chua_ro": "chưa rõ"}

        def simulate_finance(state: ChatState):
            """Loan what-if from chat (AG-02). Every number in the reply comes from
            the deterministic finance tool; a missing rate is asked for, never
            defaulted. The reply is templated Vietnamese, so no LLM call happens
            on this path and the confirmed profile/run stay untouched."""
            session = self.repo.session(state["session_id"])
            visible = self.results(session["id"], state["actor"])

            def reply(**payload):
                return {"response": {"intent": "simulate_finance", **payload},
                        "provenance": stamp("deterministic-engine", "finance",
                                            **state["toolbox"].summary("finance"))}

            if not visible["results"]:
                return reply(status="needs_results",
                             message="Bạn cần có danh sách phòng trong kết quả hiện tại trước khi mô phỏng vay.")
            parsed = parse_loan_terms(state["text"])
            profile = Profile.model_validate_json(session["profile_json"])
            if parsed["term_months"] is not None and parsed["term_months"] > 36:
                return reply(status="needs_clarification",
                             questions=[f"Hiện mô phỏng được khoản vay từ 1 đến 36 tháng; bạn chọn lại kỳ hạn "
                                        f"(câu vừa nêu {parsed['term_months']} tháng)."])
            loan = merge_loan_terms(profile.loan, parsed)
            if loan is None:
                # No confirmed loan and the text lacks a number: ask, never default a rate.
                if parsed["annual_rate"] is None:
                    return reply(status="needs_clarification",
                                 questions=["Bạn muốn vay với lãi suất bao nhiêu %/năm? Ví dụ: "
                                            "“nếu vay 12 tháng lãi 12% thì sao”."],
                                 message="Cần mức lãi suất để mô phỏng khoản vay.")
                return reply(status="needs_clarification",
                             questions=["Bạn muốn vay trong bao nhiêu tháng (1–36 tháng)?"])
            visible_by_id = {item["room_id"]: item for item in visible["results"]}
            mentioned = resolve_room_reference(state["text"], visible["results"])
            if mentioned is None and mention_room_id(state["text"]):
                raise DomainError("not_visible", "Chỉ mô phỏng phòng trong kết quả hiện tại.", 403)
            item = visible_by_id.get(mentioned) or visible["results"][0]
            room = next(room for room in self.catalog.rooms() if room.id == item["room_id"])
            cost = state["toolbox"].call("finance", "simulate_scenarios", self._simulate_item, room, profile,
                                         scenario=profile.scenario, cost_split=profile.cost_split, loan=loan)
            affordability = cost.get("affordability") or {}
            estimate = affordability.get("loan")
            if estimate is not None:
                rate_percent = float(loan.annual_rate * 100)
                burden = affordability.get("burden_vnd")
                burden_text = (f"Tổng chi phí tháng có trả góp: {copilot._money(burden)}" if burden is not None
                               else "Tổng chi phí tháng chưa đủ dữ liệu vì còn thiếu phí")
                message = (f"Mô phỏng cho {item['title']} ({item['room_id']}): cần vay "
                           f"{copilot._money(estimate['principal_vnd'])} trong {estimate['term_months']} tháng, "
                           f"lãi {rate_percent:g}%/năm, trả góp {copilot._money(estimate['installment_vnd'])}/tháng "
                           f"(tổng lãi {copilot._money(estimate['total_interest_vnd'])}). {burden_text} "
                           f"({LOAN_BAND_VI[affordability['band']]}).")
            else:
                monthly = cost.get("monthly_total_vnd")
                message = (f"Mô phỏng cho {item['title']} ({item['room_id']}): với số tiền mặt bạn có, không phát "
                           "sinh khoản vay"
                           + (f"; tổng chi phí tháng {copilot._money(monthly)}." if monthly is not None
                              else "; chưa đủ dữ liệu phí để tính tổng tháng."))
            return reply(status="simulation", message=message,
                         simulation={"room_id": item["room_id"], "room_title": item["title"],
                                     "scenario": {"annual_rate": float(loan.annual_rate * 100),
                                                  "term_months": loan.term_months,
                                                  "principal_vnd": estimate["principal_vnd"] if estimate else None},
                                     "result": {"label": SIMULATION_LABEL, "cost": cost}})

        def finance(state: ChatState):
            require("chat:message", state["actor"])
            if state.get("intent") == "simulate_finance":
                return simulate_finance(state)
            if state.get("cost_input") is None:
                return {"response": {"intent": "calculate_cost", "status": "needs_clarification",
                        "questions": ["Cần bảng giá/phí, tiền cọc, số tháng trả trước và kịch bản sử dụng để tính chi phí."]},
                        "provenance": stamp("deterministic-engine", "finance", **state["toolbox"].summary("finance"))}
            request = CostRequest.model_validate(state["cost_input"])
            tool = "assess_affordability" if request.affordability else "calculate_cost"
            cost = state["toolbox"].call("finance", tool, estimate_cost, request)
            return {"response": {"intent": "calculate_cost", "status": "cost_estimate",
                                 "cost": cost.model_dump(mode="json")},
                    "provenance": stamp("deterministic-engine", "finance", **state["toolbox"].summary("finance"))}

        def support(state: ChatState):
            session = self.repo.session(state["session_id"])
            # Handoff is a deterministic preparation on the assigned session; it
            # never claims a manager is connected and never contacts anyone.
            require("support:handoff", state["actor"], Resource.for_session(session))
            ticket = state["toolbox"].call("support", "request_support", self.repo.request_support, session)
            return {"response": {"intent": "human_support", "status": "support_requested",
                    "ticket_id": ticket["id"],
                    "message": "Đã lưu yêu cầu hỗ trợ, đang chờ quản trị viên tiếp nhận. Muốn hỏi chủ nhà về một "
                               "phòng, bấm “Chat với chủ nhà” ở phòng đó để chuyển kèm ngữ cảnh."},
                    "provenance": stamp("deterministic-engine", "support", **state["toolbox"].summary("support"))}

        def handover(state: ChatState):
            """AG-09: handover sang chủ nhà của một căn trong kết quả hiện tại.
            Ngữ cảnh chuyển kèm chỉ gồm band tài chính, không bao giờ thu nhập;
            không rõ căn → hỏi lại kèm danh sách căn đang hiển thị."""
            session = self.repo.session(state["session_id"])
            require("support:handoff", state["actor"], Resource.for_session(session))
            visible = self.results(state["session_id"], state["actor"])["results"]
            room_id = resolve_room_reference(state["text"], visible)
            if room_id is None:
                if mention_room_id(state["text"]):
                    raise DomainError("not_visible", "Chỉ mở hội thoại cho căn trong kết quả hiện tại.", 403)
                options = [f"Căn {index + 1}: {item['title'].split('. ')[0]} ({item['room_id']})"
                           for index, item in enumerate(visible[:5])]
                return {"response": {"intent": "landlord_handover", "status": "needs_clarification",
                                     "questions": (["Bạn muốn chat với chủ nhà của căn nào?"] + options) or None},
                        "provenance": stamp("deterministic-engine", "handover",
                                            outcome="missing_room_reference")}
            conversation = state["toolbox"].call("support", "open_conversation", self.start_conversation,
                                                 state["actor"], room_id, state["session_id"])
            return {"response": {"intent": "landlord_handover", "status": "handover",
                                 "conversation_id": conversation["id"],
                                 "message": f"Đã mở hội thoại với chủ nhà căn {room_id}; "
                                            "ngữ cảnh đã được chuyển kèm (chỉ băng tài chính, không thu nhập)."},
                    "provenance": stamp("deterministic-engine", "handover", room_id=room_id)}

        def handbook_node(state: ChatState):
            # Retrieval only: platform entries and, when a listing is named, that landlord's house rules.
            visible = self.results(state["session_id"], state["actor"])["results"]
            room_id = resolve_room_reference(state["text"], visible)
            room = next((room for room in self.catalog.rooms() if room.id == room_id), None) if room_id else None
            found = state["toolbox"].call("handbook", "search_handbook", handbook.answer, state["text"],
                                          room.house_rules if room else None)
            return {"response": {"intent": "handbook", "status": "handbook_answer",
                                 "answers": found["answers"], "house_rules": found["house_rules"],
                                 "disclaimer": found["disclaimer"],
                                 "message": None if found["found"] else
                                 "Chưa tìm thấy mục phù hợp trong cẩm nang; bạn có thể hỏi chủ nhà qua live chat."},
                    "provenance": stamp("deterministic-engine", "handbook", **state["toolbox"].summary("handbook"))}

        graph = StateGraph(ChatState)
        graph.add_node("route", route)
        graph.add_node("handbook", handbook_node)
        graph.add_node("interview", interview)
        graph.add_node("finance", finance)
        graph.add_node("support", support)
        graph.add_node("handover", handover)
        graph.add_edge(START, "route")
        graph.add_conditional_edges("route", lambda state: state["intent"],
            {"find_room": "interview", "unknown": "interview", "calculate_cost": "finance",
             "simulate_finance": "finance", "human_support": "support",
             "landlord_handover": "handover", "handbook": "handbook"})
        for node in ("interview", "finance", "support", "handover", "handbook"):
            graph.add_edge(node, END)
        # Raw chat history is not checkpointed in this scaffold.
        return graph.compile()

    def _build_recommendation_graph(self):
        def rank(state: RecommendationState):
            with self.repo.guard():
                return rank_current(state)

        def rank_current(state: RecommendationState):
            run = self.repo.run(state["run_id"])
            if not self._fresh(run):
                return {"items": [], "diagnostics": {"rejected": {}, "verification": {}}}
            profile = Profile.model_validate_json(run["profile_json"])
            toolbox = ToolBox()
            try:
                items, diagnostics = toolbox.call("ranking", "match_catalog", self.catalog.match,
                                                  profile, self.matching_method)
            except DomainError as error:
                if error.code != "semantic_unavailable":
                    raise
                items, diagnostics = toolbox.call("ranking", "match_catalog", self.catalog.match, profile, "B1")
                diagnostics["algorithm"] = "B1_fallback"
                diagnostics["semantic_status"] = "unavailable"
            diagnostics["agent"] = toolbox.summary("ranking")
            diagnostics["catalog_version"] = run["catalog_version"]
            diagnostics["requested_method"] = self.matching_method
            # Diagnostics bound for the ledger/checkpoint never carry chat PII.
            return {"items": [item.model_dump(mode="json") for item in items],
                    "diagnostics": redact_tree(diagnostics)}

        def save_draft(state: RecommendationState):
            with self.repo.guard():
                run = self.repo.run(state["run_id"])
                if self._fresh(run):
                    self.repo.set_draft(run["id"], state["items"], state["diagnostics"])
            return {}

        def publish(state: RecommendationState):
            # Quyết định 05/11/2026: kết quả tới khách ngay khi xếp hạng xong.
            # Chủ nhà vẫn được báo nhu cầu qua lead khi căn của họ lọt top 5
            # (source="recommended"), không thu nhập nào đi kèm lead.
            with self.repo.guard():
                run = self.repo.run(state["run_id"])
                if not self._fresh(run) or run["status"] != "published":
                    return {}
                self.repo.mark_published(run["id"])
                session = self.repo.session(run["session_id"])
                notifications.notify(self.repo, session["owner_id"], "rooms_ready",
                                     "Danh sách phòng phù hợp đã sẵn sàng",
                                     f"{len(run['items'])} căn khớp nhu cầu đã hiện trong trợ lý AI của bạn.",
                                     f"run:{run['id']}:ready", "/tro-ly-ai")
                for item in run["items"][:5]:
                    pms.touch_lead(self.repo, item.get("landlord_id") or DEFAULT_LANDLORD,
                                   session["owner_id"], item["room_id"], "recommended")
            return {}

        graph = StateGraph(RecommendationState)
        graph.add_node("rank", rank)
        graph.add_node("save_draft", save_draft)
        graph.add_node("publish", publish)
        graph.add_edge(START, "rank")
        graph.add_edge("rank", "save_draft")
        graph.add_edge("save_draft", "publish")
        graph.add_edge("publish", END)
        return graph.compile(checkpointer=self.checkpointer)
