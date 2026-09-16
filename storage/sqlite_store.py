"""SQLite implementation of the EventStore and MemoryStore contracts.

This is the transactional source of truth described in
docs/02-state-and-memory.md. Anything that needs durable state should
depend on contracts.storage.EventStore / MemoryStore, not on this module,
so a future backend swap never requires touching callers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from contracts.models import Event, MemoryCandidate
from contracts.schema_validation import validate_event, validate_payload
from storage.migrate import migrate
from storage.projections import apply_event


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a database, applying any pending migrations."""

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


class SqliteEventStore:
    """Append-only event ledger backed by SQLite. See contracts/storage.py."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def append(self, event: Event) -> Event:
        event_dict = event.to_dict()
        validate_event(event_dict)
        validate_payload(event.type, event.payload)

        self._conn.execute(
            """
            INSERT INTO events
                (id, schema_version, occurred_at, type, source, parent_id, correlation_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.schema_version,
                event.occurred_at,
                event.type,
                event.source,
                event.parent_id,
                event.correlation_id,
                json.dumps(event.payload),
            ),
        )
        apply_event(self._conn, event)
        self._conn.commit()
        return event

    def get(self, event_id: str) -> Event | None:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return self._row_to_event(row) if row else None

    def list_by_type(self, type_: str) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE type = ? ORDER BY rowid_order", (type_,)
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def all(self) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events ORDER BY rowid_order"
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> Event:
        (
            _rowid_order,
            id_,
            schema_version,
            occurred_at,
            type_,
            source,
            parent_id,
            correlation_id,
            payload,
        ) = row
        return Event(
            id=id_,
            schema_version=schema_version,
            occurred_at=occurred_at,
            type=type_,
            source=source,
            payload=json.loads(payload),
            parent_id=parent_id,
            correlation_id=correlation_id,
        )


class SqliteMemoryStore:
    """Candidate memories, materialized from memory.* events. See contracts/storage.py."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def propose(self, candidate: MemoryCandidate) -> MemoryCandidate:
        raise NotImplementedError(
            "MemoryCandidates are proposed via memory.candidate_proposed events "
            "through EventStore.append, not written directly -- projections.py "
            "is the only writer of the memory_candidates table."
        )

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        row = self._conn.execute(
            "SELECT * FROM memory_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        return self._row_to_candidate(row) if row else None

    def list(self, *, status: str | None = None) -> list[MemoryCandidate]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM memory_candidates").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memory_candidates WHERE status = ?", (status,)
            ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def _row_to_candidate(self, row) -> MemoryCandidate:
        (id_, statement, confidence, source_event_ids, status, reviewed_at, retention_policy) = row
        return MemoryCandidate(
            id=id_,
            statement=statement,
            confidence=confidence,
            source_event_ids=json.loads(source_event_ids),
            status=status,
            reviewed_at=reviewed_at,
            retention_policy=retention_policy,
        )
