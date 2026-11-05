import json
from types import SimpleNamespace

import pytest

from backend.app.database import Database
from backend.app.migrations import MIGRATIONS, SCHEMA_VERSION
from backend.app.models import DomainError
from backend.app.repository import Repository
from backend.app.service import HomeMatchService


def test_confirmation_commits_before_graph_and_snapshots_survive_restart(storage, renter, profile):
    service = HomeMatchService(storage)
    observer = Database(storage)
    try:
        sid = service.create_session(renter)["session_id"]
        graph = service.recommendation_graph

        def observe_then_generate(state, config):
            row = observer.execute("SELECT profile_version,active_run_id FROM hm_sessions WHERE id=?", (sid,)).fetchone()
            assert row["profile_version"] == 1 and row["active_run_id"] == state["run_id"]
            assert observer.execute("SELECT COUNT(*) AS count FROM hm_profile_snapshots WHERE session_id=?", (sid,)).fetchone()["count"] == 1
            return graph.invoke(state, config)

        service.recommendation_graph = SimpleNamespace(invoke=observe_then_generate)
        assert service.confirm(sid, renter, profile, 0)["status"] == "published"
        service.recommendation_graph = graph
        changed = profile.model_copy(update={"max_monthly_cost_vnd": 4_000_000})
        service.confirm(sid, renter, changed, 1)
        assert service.repo.db.execute("SELECT COUNT(*) AS count FROM hm_profile_snapshots WHERE session_id=?", (sid,)).fetchone()["count"] == 2
    finally:
        observer.close()
        service.close()
    second = HomeMatchService(storage)
    try:
        snapshots = second.repo.db.execute("SELECT profile_json FROM hm_profile_snapshots WHERE session_id=? ORDER BY profile_version", (sid,)).fetchall()
        assert [json.loads(row["profile_json"])["max_monthly_cost_vnd"] for row in snapshots] == [3_500_000, 4_000_000]
    finally:
        second.close()


def test_failed_run_is_rerunnable_by_its_renter_and_survives_restart(storage, renter, profile):
    first = HomeMatchService(storage)
    try:
        sid = first.create_session(renter)["session_id"]
        graph = first.recommendation_graph

        def fail_midway(state, config):
            raise RuntimeError("checkpoint unavailable mid-generation")

        first.recommendation_graph = SimpleNamespace(invoke=fail_midway)
        failed = first.confirm(sid, renter, profile, 0)
        assert failed["status"] == "generation_failed" and failed["results"] == []
        first.recommendation_graph = graph
        # Người thuê tự chạy lại vòng tìm lỗi của phiên mình (AG-00).
        rerun = first.rerun(sid, renter)
        assert rerun["status"] == "published" and rerun["results"]
        # Run cũ bị đánh dấu hết hiệu lực, run mới là active run.
        assert first.repo.run(failed["run_id"])["status"] == "invalidated"
    finally:
        first.close()
    second = HomeMatchService(storage)
    try:
        assert second.results(sid, renter)["status"] == "published"
    finally:
        second.close()


def test_generation_failure_before_saving_draft_is_retryable(service, renter, admin, profile):
    sid = service.create_session(renter)["session_id"]

    def fail_before_draft(run_id, items, diagnostics):
        raise RuntimeError("checkpoint unavailable before draft persisted")

    original = service.repo.set_draft
    service.repo.set_draft = fail_before_draft
    failed = service.confirm(sid, renter, profile, 0)
    assert failed["status"] == "generation_failed" and failed["results"] == []
    assert service.repo.run(failed["run_id"])["items"] == []
    service.repo.set_draft = original
    retried = service.retry(failed["run_id"], admin)
    assert retried["status"] == "published" and retried["items"]


def test_nested_transaction_rollback_does_not_commit_partial_import(service):
    db = service.repo.db
    with db:
        db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES('outer-user','renter','fixture-hash')")
        try:
            with db:
                db.execute("INSERT INTO hm_users(id,role,password_hash) VALUES('inner-user','renter','fixture-hash')")
                raise ValueError("abort inner transaction")
        except ValueError:
            pass
        assert db.execute("SELECT id FROM hm_users WHERE id='inner-user'").fetchone() is None
    assert db.execute("SELECT id FROM hm_users WHERE id='outer-user'").fetchone()


def test_legacy_schema_migration_preserves_profile_and_runs(storage, renter, profile):
    db = Database(storage)
    db.executescript(MIGRATIONS[0][2])
    db.execute("INSERT INTO hm_sessions VALUES(?,?,?,1,?,1,?,NULL)",
               ("legacy-session", renter.id, "manager-a", "{}", profile.model_dump_json()))
    db.execute("INSERT INTO hm_runs(id,session_id,profile_version,catalog_version,profile_json,status,created_at) VALUES(?,?,1,?,?,?,?)",
               ("legacy-run", "legacy-session", "legacy-catalog", profile.model_dump_json(), "pending_review", "2026-01-01T00:00:00+00:00"))
    db.close()
    for _ in range(2):
        repo = Repository(storage)
        try:
            assert repo.schema_version == SCHEMA_VERSION
            # Migration 16 (bỏ duyệt gợi ý): run cũ đang chờ duyệt chuyển hết hiệu lực.
            assert repo.run("legacy-run")["status"] == "invalidated"
            rows = repo.db.execute("SELECT * FROM hm_profile_snapshots").fetchall()
            assert len(rows) == 1 and rows[0]["profile_json"] == profile.model_dump_json()
            assert repo.db.execute("SELECT COUNT(*) AS count FROM hm_schema_migrations").fetchone()["count"] == len(MIGRATIONS)
        finally:
            repo.close()
