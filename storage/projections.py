"""Fold immutable events into materialized, queryable state.

Per docs/02-state-and-memory.md: SQLite is the transactional source for
events, tasks, approvals and memory candidates, but the projection tables
(tasks, approvals, memory_candidates) are never the source of truth --
they're always reproducible from `events` alone. rebuild_projections proves
that, and is what the restore test in tests/recovery relies on.
"""

from __future__ import annotations

import json
import sqlite3

from contracts.models import Event

_HANDLERS: dict[str, "callable"] = {}


def _handles(event_type: str):
    def decorator(fn):
        _HANDLERS[event_type] = fn
        return fn

    return decorator


@_handles("task.created")
def _on_task_created(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        INSERT INTO tasks (id, title, status, created_from_event, updated_from_event)
        VALUES (?, ?, 'open', ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (p["task_id"], p["title"], event.id, event.id),
    )


@_handles("approval.requested")
def _on_approval_requested(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        INSERT INTO approvals (id, level, description, status, requested_from_event, expires_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (p["approval_id"], p["level"], p["description"], event.id, p.get("expires_at")),
    )


@_handles("approval.decided")
def _on_approval_decided(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        UPDATE approvals
        SET status = ?, decided_from_event = ?
        WHERE id = ?
        """,
        (p["decision"], event.id, p["approval_id"]),
    )


@_handles("memory.candidate_proposed")
def _on_memory_candidate_proposed(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        INSERT INTO memory_candidates
            (id, statement, confidence, source_event_ids, status, retention_policy)
        VALUES (?, ?, ?, ?, 'proposed', 'default')
        ON CONFLICT(id) DO NOTHING
        """,
        (p["candidate_id"], p["statement"], p["confidence"], json.dumps(p["source_event_ids"])),
    )


@_handles("memory.candidate_confirmed")
def _on_memory_candidate_confirmed(conn: sqlite3.Connection, event: Event) -> None:
    conn.execute(
        "UPDATE memory_candidates SET status = 'confirmed' WHERE id = ?",
        (event.payload["candidate_id"],),
    )


@_handles("signal.detected")
def _on_signal_detected(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        INSERT INTO signals (id, kind, subject, description, detected_from_event)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (p["signal_id"], p["kind"], p["subject"], p["description"], event.id),
    )


@_handles("initiative.proposed")
def _on_initiative_proposed(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        INSERT INTO initiatives (id, signal_id, level, description, status, proposed_from_event)
        VALUES (?, ?, ?, ?, 'proposed', ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (p["initiative_id"], p["signal_id"], p["level"], p["description"], event.id),
    )


@_handles("initiative.decided")
def _on_initiative_decided(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        "UPDATE initiatives SET status = ? WHERE id = ?",
        (p["decision"], p["initiative_id"]),
    )


@_handles("goal.created")
def _on_goal_created(conn: sqlite3.Connection, event: Event) -> None:
    p = event.payload
    conn.execute(
        """
        INSERT INTO goals (id, initiative_id, description, status, created_from_event)
        VALUES (?, ?, ?, 'active', ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (p["goal_id"], p["initiative_id"], p["description"], event.id),
    )


def apply_event(conn: sqlite3.Connection, event: Event) -> None:
    """Fold a single event into the projection tables, if a handler exists.

    Unknown event types are stored in the ledger (see SqliteEventStore.append)
    but intentionally do not affect projections -- a new event type from a
    future plugin must not require a core code change just to be recorded.
    """

    handler = _HANDLERS.get(event.type)
    if handler is not None:
        handler(conn, event)


def rebuild_projections(conn: sqlite3.Connection) -> None:
    """Drop and replay all projections from the event log.

    This is the mechanical proof behind "creier recuperabil": if this
    function produces the same state as incremental folding did, the
    projections carry no information that isn't already in `events`.
    """

    conn.execute("DELETE FROM tasks")
    conn.execute("DELETE FROM approvals")
    conn.execute("DELETE FROM memory_candidates")

    rows = conn.execute("SELECT * FROM events ORDER BY rowid_order").fetchall()
    for row in rows:
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
        event = Event(
            id=id_,
            schema_version=schema_version,
            occurred_at=occurred_at,
            type=type_,
            source=source,
            payload=json.loads(payload),
            parent_id=parent_id,
            correlation_id=correlation_id,
        )
        apply_event(conn, event)

    conn.commit()
