from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Small SQL boundary shared by the offline and PostgreSQL repositories."""

    def __init__(self, location: str | Path):
        self.postgres = str(location).startswith(("postgresql://", "postgres://"))
        self.location = str(location)
        self.closed = False
        self.depth = 0
        self.transactions = []
        if self.postgres:
            self.connection = self._connect_postgres()
        else:
            if str(location) != ":memory:":
                Path(location).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(location), check_same_thread=False, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys=ON")

    def _connect_postgres(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.location, autocommit=True, row_factory=dict_row)

    def _retry_dead_connection(self, action):
        """Hosted PostgreSQL (Neon scale-to-zero, restarts) closes idle sessions. Outside a
        transaction a dead session is replaced once and the statement re-sent: the old
        socket was already gone, so the statement never reached the server. Inside a
        transaction the error propagates and the caller's unit of work fails as before."""
        import psycopg
        try:
            return action()
        except psycopg.OperationalError:
            # Never reopen a session this process closed on purpose (shutdown, failed health).
            if self.closed or self.depth or not (self.connection.closed or self.connection.broken):
                raise
            self.connection = self._connect_postgres()
            return action()

    def execute(self, sql: str, params=()):
        if not self.postgres:
            return self.connection.execute(sql, params)
        sql = sql.replace("?", "%s")
        return self._retry_dead_connection(lambda: self.connection.execute(sql, params))

    def executescript(self, sql: str):
        for statement in sql.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.closed = True
        self.connection.close()

    def __enter__(self):
        if self.postgres:
            def begin():
                transaction = self.connection.transaction()
                transaction.__enter__()
                return transaction
            # BEGIN is the first statement of the unit of work, so it is safe to retry.
            self.transactions.append(self._retry_dead_connection(begin) if self.depth == 0 else begin())
        elif self.depth == 0:
            self.connection.execute("BEGIN IMMEDIATE")
        else:
            self.connection.execute(f"SAVEPOINT hm_nested_{self.depth}")
        self.depth += 1
        return self

    def __exit__(self, kind, error, traceback):
        self.depth -= 1
        if self.postgres:
            return self.transactions.pop().__exit__(kind, error, traceback)
        if self.depth == 0:
            self.connection.rollback() if kind else self.connection.commit()
        else:
            name = f"hm_nested_{self.depth}"
            if kind:
                self.connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
            self.connection.execute(f"RELEASE SAVEPOINT {name}")
        return False
