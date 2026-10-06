from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import DEFAULT_LANDLORD, DomainError, DraftProfile, Profile, Review
from .database import Database
from .migrations import migrate
from .organizations import ensure_bootstrap


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """Versioned business ledger shared by SQLite and PostgreSQL."""

    def __init__(self, path: str | Path):
        self.db = Database(path)
        try:
            self.schema_version = migrate(self.db)
            # Idempotent W-01/W-02 bootstrap: default organization, seed-staff
            # memberships and ownership mappings for unmapped catalog rooms.
            ensure_bootstrap(self)
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def guard(self):
        with self.db:
            suffix = " FOR UPDATE" if self.db.postgres else ""
            self.db.execute("SELECT version FROM hm_catalog_meta WHERE id='catalog'" + suffix).fetchone()
            yield

    def session(self, session_id: str) -> dict:
        row = self.db.execute("SELECT * FROM hm_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Không tìm thấy phiên.", 404)
        return dict(row)

    def create_session(self, owner_id: str, manager_id: str, draft: DraftProfile | None = None) -> dict:
        session_id = str(uuid4())
        with self.db:
            self.db.execute("INSERT INTO hm_sessions(id,owner_id,manager_id,draft_json) VALUES(?,?,?,?)",
                            (session_id, owner_id, manager_id, (draft or DraftProfile()).model_dump_json()))
        return self.session(session_id)

    def update_draft(self, session_id: str, draft: DraftProfile, expected_revision: int | None = None):
        with self.db:
            clause = " AND draft_revision=?" if expected_revision is not None else ""
            params = (draft.model_dump_json(), session_id) + ((expected_revision,) if expected_revision is not None else ())
            changed = self.db.execute("UPDATE hm_sessions SET draft_json=?,draft_revision=draft_revision+1 WHERE id=?" + clause, params).rowcount
            if changed != 1:
                raise DomainError("stale_profile", "Nhu cầu đã đổi; hãy tải lại bản mới.")

    def confirm_profile(self, session_id: str, expected_revision: int, profile: Profile) -> dict:
        with self.db:
            changed = self.db.execute(
                "UPDATE hm_sessions SET profile_json=?,profile_version=profile_version+1,active_run_id=NULL "
                "WHERE id=? AND draft_revision=?",
                (profile.model_dump_json(), session_id, expected_revision),
            ).rowcount
            if changed != 1:
                raise DomainError("stale_profile", "Nhu cầu đã đổi; hãy xác nhận bản mới.")
            # Confirmation creates a new draft revision too, so retry cannot create another run.
            self.db.execute("UPDATE hm_sessions SET draft_revision=draft_revision+1 WHERE id=?", (session_id,))
            session = self.session(session_id)
            self.db.execute("INSERT INTO hm_profile_snapshots VALUES(?,?,?,?)",
                            (session_id, session["profile_version"], session["profile_json"], utc_now()))
            self.db.execute("UPDATE hm_runs SET status='invalidated' WHERE session_id=? "
                            "AND status IN ('generating','pending_review','partially_published','reviewed','published')",
                            (session_id,))
        return self.session(session_id)

    def create_run(self, session: dict, catalog_version: str) -> dict:
        run_id = str(uuid4())
        with self.db:
            self.db.execute("INSERT INTO hm_runs(id,session_id,profile_version,catalog_version,profile_json,status,created_at) "
                            "VALUES(?,?,?,?,?,'generating',?)",
                            (run_id, session["id"], session["profile_version"], catalog_version,
                             session["profile_json"], utc_now()))
            self.db.execute("UPDATE hm_sessions SET active_run_id=? WHERE id=?", (run_id, session["id"]))
        return self.run(run_id)

    def run(self, run_id: str) -> dict:
        row = self.db.execute("SELECT * FROM hm_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Không tìm thấy bản gợi ý.", 404)
        result = dict(row)
        for name in ("items", "diagnostics", "decision"):
            raw = result.pop(f"{name}_json")
            result[name] = json.loads(raw) if raw is not None else None
        return result

    def set_draft(self, run_id: str, items: list[dict], diagnostics: dict):
        status = "pending_review" if items else ("needs_verification" if diagnostics["verification"] else "no_match")
        with self.db:
            self.db.execute("UPDATE hm_runs SET items_json=?,diagnostics_json=?,status=? "
                            "WHERE id=? AND status='generating'",
                            (json.dumps(items, ensure_ascii=False), json.dumps(diagnostics), status, run_id))

    def invalidate(self, run_id: str):
        with self.db:
            self.db.execute("UPDATE hm_runs SET status='invalidated' WHERE id=?", (run_id,))

    def fail_generation(self, run_id: str):
        with self.db:
            self.db.execute("UPDATE hm_runs SET status='generation_failed',items_json='[]',"
                            "diagnostics_json=? WHERE id=? AND status IN ('generating','pending_review')",
                            (json.dumps({"error_code": "generation_failed"}), run_id))

    def reviews(self, run_id: str) -> dict[str, dict]:
        rows = self.db.execute("SELECT landlord_id,event_json FROM hm_run_reviews WHERE run_id=?", (run_id,))
        return {row["landlord_id"]: json.loads(row["event_json"]) for row in rows}

    @staticmethod
    def landlords(run: dict) -> list[str]:
        return sorted({item.get("landlord_id") or DEFAULT_LANDLORD for item in run["items"]})

    @staticmethod
    def visible_items(run: dict, reviews: dict[str, dict]) -> list[dict]:
        """Approved rooms in the agent's order; each landlord's own reordering fills that
        landlord's slots, so no landlord can move a room ahead of another landlord's room."""
        kept = {landlord: list(event["keep_room_ids"]) for landlord, event in reviews.items()
                if event["payload"]["decision"] == "approve"}
        chosen = {room_id for ids in kept.values() for room_id in ids}
        by_id = {item["room_id"]: item for item in run["items"]}
        result = []
        for item in run["items"]:
            # A kept room marks one slot of its landlord; the slot takes that landlord's next choice.
            if item["room_id"] in chosen:
                result.append(by_id[kept[item.get("landlord_id") or DEFAULT_LANDLORD].pop(0)])
        return result

    def review(self, run_id: str, actor_id: str, review: Review) -> dict:
        """Record one landlord's decision on their own rooms; finalize when every landlord decided."""
        run = self.run(run_id)
        own = [item["room_id"] for item in run["items"] if (item.get("landlord_id") or DEFAULT_LANDLORD) == actor_id]
        if not own:
            raise DomainError("forbidden", "Bạn không có quyền xem phiên này.", 403)
        payload = review.model_dump(mode="json")
        old = self.reviews(run_id).get(actor_id)
        if old is not None:
            if old["payload"] == payload:
                return old
            raise DomainError("review_conflict", "Bạn đã có quyết định khác cho bản này.")
        if run["status"] not in ("pending_review", "partially_published") \
                or review.expected_profile_version != run["profile_version"]:
            raise DomainError("stale_review", "Bản gợi ý không còn ở phiên bản đang chờ duyệt.")
        keep = review.keep_room_ids if review.keep_room_ids is not None else own
        if len(keep) != len(set(keep)) or not set(keep).issubset(own):
            raise DomainError("invalid_selection", "Chỉ được chọn phòng của bạn thuộc bản nháp đủ điều kiện.", 422)
        if review.decision == "approve" and not keep:
            raise DomainError("invalid_selection", "Duyệt cần ít nhất một phòng.", 422)
        # Dropping or reordering the agent's ranking must be justified so stock cannot be favoured silently.
        overridden = review.decision == "approve" and keep != own
        if overridden and not review.override_reason:
            raise DomainError("override_reason_required",
                              "Cần ghi lý do khi bỏ phòng hoặc đổi thứ tự so với đề xuất của trợ lý.", 422)
        event = {"event_id": str(uuid4()), "actor_id": actor_id, "payload": payload,
                 "keep_room_ids": keep if review.decision == "approve" else [], "agent_order": own,
                 "overridden": overridden, "recorded_at": utc_now()}
        with self.db:
            try:
                self.db.execute("INSERT INTO hm_run_reviews(run_id,landlord_id,event_json,created_at) VALUES(?,?,?,?)",
                                (run_id, actor_id, json.dumps(event, ensure_ascii=False), event["recorded_at"]))
            except Exception:
                raise DomainError("review_conflict", "Quyết định đã thay đổi; cần tải lại.") from None
            reviews = {**self.reviews(run_id), actor_id: event}
            if set(reviews) >= set(self.landlords(run)):
                # Every landlord decided: the ledger event the graph resumes with.
                final = {"event_id": str(uuid4()), "landlords": sorted(reviews), "recorded_at": utc_now()}
                changed = self.db.execute("UPDATE hm_runs SET decision_json=?,status='reviewed' WHERE id=? "
                                          "AND status IN ('pending_review','partially_published') AND decision_json IS NULL",
                                          (json.dumps(final), run_id)).rowcount
            else:
                approved = any(item["payload"]["decision"] == "approve" for item in reviews.values())
                changed = self.db.execute("UPDATE hm_runs SET status=? WHERE id=? "
                                          "AND status IN ('pending_review','partially_published')",
                                          ("partially_published" if approved else "pending_review", run_id)).rowcount
            if changed != 1:
                raise DomainError("review_conflict", "Quyết định đã thay đổi; cần tải lại.")
        return event

    def finish_review(self, run_id: str):
        decisions = [event["payload"]["decision"] for event in self.reviews(run_id).values()]
        status = ("published" if "approve" in decisions else
                  "needs_revision" if "needs_revision" in decisions else "rejected")
        with self.db:
            self.db.execute("UPDATE hm_runs SET status=?,published_at=? WHERE id=? AND status='reviewed'",
                            (status, utc_now() if status == "published" else None, run_id))

    def pending_runs(self, landlord_id: str) -> list[dict]:
        rows = self.db.execute("SELECT id FROM hm_runs WHERE status IN "
                               "('pending_review','partially_published','reviewed') ORDER BY created_at")
        runs = [self.run(row["id"]) for row in rows]
        return [run for run in runs if landlord_id in self.landlords(run)]

    def create_viewing(self, session: dict, run_id: str, room_id: str, requested_at: str, key: str,
                       landlord_id: str, mode: str = "offline") -> dict:
        payload = {"run_id": run_id, "room_id": room_id, "requested_at": requested_at, "mode": mode}
        existing = self.db.execute("SELECT * FROM hm_viewings WHERE owner_id=? AND idempotency_key=?",
                                   (session["owner_id"], key)).fetchone()
        if existing:
            if json.loads(existing["payload_json"]) != payload:
                raise DomainError("idempotency_conflict", "Mã yêu cầu đã dùng cho nội dung khác.")
            return dict(existing)
        viewing_id = str(uuid4())
        # Online viewings get a meeting room link; Jitsi rooms need no account or API key.
        meeting_url = f"https://meet.jit.si/homematch-{viewing_id}" if mode == "online" else None
        with self.db:
            self.db.execute("INSERT INTO hm_viewings(id,session_id,run_id,owner_id,manager_id,room_id,requested_at,"
                            "status,idempotency_key,payload_json,landlord_id,mode,meeting_url) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (viewing_id, session["id"], run_id, session["owner_id"], landlord_id,
                             room_id, requested_at, "requested", key, json.dumps(payload), landlord_id,
                             mode, meeting_url))
        return self.viewing(viewing_id)

    def create_direct_viewing(self, renter_id: str, room_id: str, landlord_id: str, requested_at: str,
                              key: str, mode: str) -> dict:
        payload = {"room_id": room_id, "requested_at": requested_at, "mode": mode, "source": "listing"}
        existing = self.db.execute("SELECT * FROM hm_viewings WHERE owner_id=? AND idempotency_key=?",
                                   (renter_id, key)).fetchone()
        if existing:
            if json.loads(existing["payload_json"]) != payload:
                raise DomainError("idempotency_conflict", "Mã yêu cầu đã dùng cho nội dung khác.")
            return dict(existing)
        viewing_id = str(uuid4())
        meeting_url = f"https://meet.jit.si/homematch-{viewing_id}" if mode == "online" else None
        with self.db:
            self.db.execute("INSERT INTO hm_viewings(id,session_id,run_id,owner_id,manager_id,room_id,requested_at,"
                            "status,idempotency_key,payload_json,landlord_id,mode,meeting_url) "
                            "VALUES(?,NULL,NULL,?,?,?,?,?,?,?,?,?,?)",
                            (viewing_id, renter_id, landlord_id, room_id, requested_at, "requested", key,
                             json.dumps(payload), landlord_id, mode, meeting_url))
        return self.viewing(viewing_id)

    def record_view(self, room_id: str, user_id: str | None):
        with self.db:
            self.db.execute("INSERT INTO hm_room_views(id,room_id,user_id,viewed_at) VALUES(?,?,?,?)",
                            (str(uuid4()), room_id, user_id, utc_now()))

    def viewing(self, viewing_id: str) -> dict:
        row = self.db.execute("SELECT * FROM hm_viewings WHERE id=?", (viewing_id,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Không tìm thấy yêu cầu xem.", 404)
        return dict(row)

    def respond_viewing(self, viewing_id: str, status: str) -> dict:
        previous = self.viewing(viewing_id)
        if previous["status"] not in {"requested", status}:
            raise DomainError("viewing_conflict", "Yêu cầu đã có phản hồi khác.")
        with self.db:
            self.db.execute("UPDATE hm_viewings SET status=? WHERE id=? AND status='requested'", (status, viewing_id))
        return self.viewing(viewing_id)

    def viewings(self, actor_id: str, role: str) -> list[dict]:
        column = "owner_id" if role == "renter" else "landlord_id"
        return [dict(row) for row in self.db.execute(f"SELECT * FROM hm_viewings WHERE {column}=?", (actor_id,))]

    def request_support(self, session: dict) -> dict:
        row = self.db.execute("SELECT * FROM hm_support WHERE session_id=? AND status='requested'",
                              (session["id"],)).fetchone()
        if row:
            return dict(row)
        ticket_id = str(uuid4())
        with self.db:
            self.db.execute("INSERT INTO hm_support VALUES(?,?,?,'requested',?)",
                            (ticket_id, session["id"], session["manager_id"], utc_now()))
        return dict(self.db.execute("SELECT * FROM hm_support WHERE id=?", (ticket_id,)).fetchone())

    def support_tickets(self, manager_id: str | None = None) -> list[dict]:
        if manager_id is None:
            return [dict(row) for row in self.db.execute("SELECT * FROM hm_support ORDER BY created_at")]
        return [dict(row) for row in self.db.execute("SELECT * FROM hm_support WHERE manager_id=?", (manager_id,))]
