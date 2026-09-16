"""Idempotent migration runner.

Per docs/02-state-and-memory.md: "Migrațiile sunt idempotente, testate pe o
copie și incluse în backup/restore." Each .sql file in storage/migrations/
runs at most once per database, tracked in schema_migrations, and running
migrate() again on an already-migrated database is a no-op.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    _ensure_migrations_table(conn)
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply any migration files not yet recorded. Returns filenames applied."""

    _ensure_migrations_table(conn)
    already = applied_migrations(conn)
    applied_now = []

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in already:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,)
        )
        applied_now.append(path.name)

    conn.commit()
    return applied_now
