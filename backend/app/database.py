from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Small SQL boundary shared by the offline and PostgreSQL repositories."""

    def __init__(self, location: str | Path):
        self.postgres = str(location).startswith(("postgresql://", "postgres://"))
        self.depth = 0
        self.transactions = []
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            self.connection = psycopg.connect(str(location), autocommit=True, row_factory=dict_row)
        else:
            if str(location) != ":memory:":
                Path(location).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(location), check_same_thread=False, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys=ON")

    def execute(self, sql: str, params=()):
        return self.connection.execute(sql.replace("?", "%s") if self.postgres else sql, params)

    def executescript(self, sql: str):
        for statement in sql.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        if self.postgres:
            transaction = self.connection.transaction()
            transaction.__enter__()
            self.transactions.append(transaction)
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
