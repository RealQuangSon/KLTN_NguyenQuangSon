import json
from types import SimpleNamespace

import pytest

from backend.app.database import Database
from backend.app.migrations import MIGRATIONS, SCHEMA_VERSION
from backend.app.models import DomainError, Review
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
        assert service.confirm(sid, renter, profile, 0)["status"] == "pending_review"
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


def test_review_resume_failure_keeps_committed_event_for_restart(storage, renter, landlord, profile):
    first = HomeMatchService(storage)
    observer = Database(storage)
    request = Review(decision="approve", expected_profile_version=1, reason="Đã kiểm tra", idempotency_key="resume-1")
    try:
        sid = first.create_session(renter)["session_id"]
        run_id = first.confirm(sid, renter, profile, 0)["run_id"]
        graph = first.recommendation_graph

        def fail_after_observing_commit(*args):
            row = observer.execute("SELECT status,decision_json FROM hm_runs WHERE id=?", (run_id,)).fetchone()
            assert row["status"] == "reviewed" and row["decision_json"]
            raise RuntimeError("private checkpoint failure")

        first.recommendation_graph = SimpleNamespace(get_state=graph.get_state, invoke=fail_after_observing_commit)
        with pytest.raises(DomainError) as error:
            first.review(run_id, landlord, request)
        assert error.value.code == "review_resume_failed" and error.value.http_status == 503
        event = first.repo.run(run_id)["decision"]
        landlord_event = first.repo.reviews(run_id)[landlord.id]
        assert first.results(sid, renter)["status"] == "reviewed"
        assert first.results(sid, renter)["results"] == []
    finally:
        observer.close()
        first.close()
    second = HomeMatchService(storage)
    try:
        recovered = second.retry(run_id, landlord)
        assert recovered["status"] == "published" and second.repo.run(run_id)["decision"] == event
        # Replaying the same landlord decision returns the recorded event, never a second one.
        assert recovered["decision"] == landlord_event
        assert second.review(run_id, landlord, request)["decision"] == landlord_event
        assert second.results(sid, renter)["results"]
    finally:
        second.close()


def test_generation_failure_after_saving_draft_is_retryable(service, renter, landlord, admin, profile):
    sid = service.create_session(renter)["session_id"]
    graph = service.recommendation_graph

    def fail_after_draft(state, config):
        graph.invoke(state, config)
        raise RuntimeError("checkpoint unavailable after draft persisted")

    service.recommendation_graph = SimpleNamespace(invoke=fail_after_draft)
    failed = service.confirm(sid, renter, profile, 0)
    assert failed["status"] == "generation_failed" and failed["results"] == []
    assert service.repo.run(failed["run_id"])["items"] == []
    service.recommendation_graph = graph
    retried = service.retry(failed["run_id"], admin)
    assert retried["status"] == "pending_review" and retried["decision"] is None


def test_missing_checkpoint_never_publishes_recorded_review(service, renter, landlord, profile):
    sid = service.create_session(renter)["session_id"]
    run_id = service.confirm(sid, renter, profile, 0)["run_id"]
    request = Review(decision="approve", expected_profile_version=1, reason="Kiểm tra", idempotency_key="missing-1")
    service.repo.review(run_id, landlord.id, request)
    service.recommendation_graph = SimpleNamespace(get_state=lambda config: SimpleNamespace(next=()))
    with pytest.raises(DomainError) as error:
        service.retry(run_id, landlord)
    assert error.value.code == "recovery_required"
    assert service.results(sid, renter)["results"] == []


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
            assert repo.run("legacy-run")["status"] == "pending_review"
            rows = repo.db.execute("SELECT * FROM hm_profile_snapshots").fetchall()
            assert len(rows) == 1 and rows[0]["profile_json"] == profile.model_dump_json()
            assert repo.db.execute("SELECT COUNT(*) AS count FROM hm_schema_migrations").fetchone()["count"] == len(MIGRATIONS)
        finally:
            repo.close()
