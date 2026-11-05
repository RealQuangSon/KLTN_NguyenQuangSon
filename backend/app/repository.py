from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import DEFAULT_LANDLORD, DomainError, DraftProfile, Profile
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
                            "AND status IN ('generating','generation_failed','published')",
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
        # Quyết định 05/11/2026: có căn là công bố ngay (published), không chờ duyệt.
        status = "published" if items else ("needs_verification" if diagnostics["verification"] else "no_match")
        with self.db:
            self.db.execute("UPDATE hm_runs SET items_json=?,diagnostics_json=?,status=? "
                            "WHERE id=? AND status='generating'",
                            (json.dumps(items, ensure_ascii=False), json.dumps(diagnostics), status, run_id))

    def mark_published(self, run_id: str):
        with self.db:
            self.db.execute("UPDATE hm_runs SET published_at=? WHERE id=? "
                            "AND status='published' AND published_at IS NULL", (utc_now(), run_id))

    def invalidate(self, run_id: str):
        with self.db:
            self.db.execute("UPDATE hm_runs SET status='invalidated' WHERE id=?", (run_id,))

    def fail_generation(self, run_id: str):
        with self.db:
            self.db.execute("UPDATE hm_runs SET status='generation_failed',items_json='[]',"
                            "diagnostics_json=? WHERE id=? AND status IN ('generating','pending_review')",
                            (json.dumps({"error_code": "generation_failed"}), run_id))

    def reviews(self, run_id: str) -> dict[str, dict]:
        """Read-only view of legacy hm_run_reviews rows (data kept after AG-00; no new writes)."""
        rows = self.db.execute("SELECT landlord_id,event_json FROM hm_run_reviews WHERE run_id=?", (run_id,))
        return {row["landlord_id"]: json.loads(row["event_json"]) for row in rows}

    @staticmethod
    def landlords(run: dict) -> list[str]:
        return sorted({item.get("landlord_id") or DEFAULT_LANDLORD for item in run["items"]})

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

    # --- Danh sách cá nhân người thuê: căn đã lưu / căn đã xem ---

    def save_room(self, user_id: str, room_id: str):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO hm_room_saves(user_id,room_id,created_at) VALUES(?,?,?)",
                (user_id, room_id, utc_now()))

    def unsave_room(self, user_id: str, room_id: str):
        with self.db:
            self.db.execute("DELETE FROM hm_room_saves WHERE user_id=? AND room_id=?",
                            (user_id, room_id))

    def saved_room_ids(self, user_id: str) -> list[str]:
        rows = self.db.execute(
            "SELECT room_id FROM hm_room_saves WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)).fetchall()
        return [row["room_id"] for row in rows]

    def viewed_room_ids(self, user_id: str, limit: int = 24) -> list[str]:
        rows = self.db.execute(
            "SELECT room_id, MAX(viewed_at) AS last_viewed FROM hm_room_views "
            "WHERE user_id=? GROUP BY room_id ORDER BY last_viewed DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [row["room_id"] for row in rows]

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
            self.db.execute("INSERT INTO hm_support(id,session_id,manager_id,status,created_at) "
                            "VALUES(?,?,?,'requested',?)",
                            (ticket_id, session["id"], session["manager_id"], utc_now()))
        return dict(self.db.execute("SELECT * FROM hm_support WHERE id=?", (ticket_id,)).fetchone())

    def support_ticket(self, ticket_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM hm_support WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None

    def support_tickets(self, manager_id: str | None = None,
                        status: str | None = None) -> list[dict]:
        query, params = "SELECT * FROM hm_support WHERE 1=1", []
        if manager_id is not None:
            query += " AND manager_id=?"
            params.append(manager_id)
        if status is not None:
            query += " AND status=?"
            params.append(status)
        return [dict(row) for row in self.db.execute(query + " ORDER BY created_at", tuple(params))]

    def update_support(self, ticket_id: str, updates: dict) -> dict:
        """Apply a lifecycle transition (status/assignee/note/timestamps)."""
        if not updates:
            return self.support_ticket(ticket_id)
        with self.db:
            clause = ", ".join(f"{column}=?" for column in updates)
            self.db.execute(f"UPDATE hm_support SET {clause} WHERE id=?",
                            tuple(updates.values()) + (ticket_id,))
        return self.support_ticket(ticket_id)
