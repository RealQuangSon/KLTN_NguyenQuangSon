"""Hosted PostgreSQL (Neon scale-to-zero) terminates idle sessions; the app must recover."""
import psycopg
import pytest

from backend.app.database import Database
from backend.app.service import HomeMatchService


def _terminate(dsn: str, pid: int) -> None:
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))


def test_dead_session_is_replaced_outside_transaction(postgres_storage):
    db = Database(postgres_storage)
    try:
        pid = db.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        _terminate(postgres_storage, pid)
        assert db.execute("SELECT 1 AS one").fetchone()["one"] == 1
        # A dead session found at BEGIN is replaced too, then the unit of work runs.
        _terminate(postgres_storage, db.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])
        with db:
            assert db.execute("SELECT 2 AS two").fetchone()["two"] == 2
    finally:
        db.close()


def test_dead_session_inside_transaction_still_fails(postgres_storage):
    db = Database(postgres_storage)
    try:
        with pytest.raises(psycopg.OperationalError):
            with db:
                _terminate(postgres_storage, db.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])
                db.execute("SELECT 1")
        # The next unit of work gets a fresh session.
        assert db.execute("SELECT 1 AS one").fetchone()["one"] == 1
    finally:
        db.close()


def test_service_recovers_after_sessions_are_terminated(postgres_storage):
    service = HomeMatchService(postgres_storage)
    try:
        with service.checkpoint_connection.connection() as connection:
            checkpoint_pid = connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        _terminate(postgres_storage, checkpoint_pid)
        _terminate(postgres_storage, service.repo.db.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])
        service.checkpoint_probe()
        assert service.repo.db.execute("SELECT 1 AS one").fetchone()["one"] == 1
    finally:
        service.close()
