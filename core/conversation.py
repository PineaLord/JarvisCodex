"""Milestone 0.1: say an idea, get a durable record, relevant context, a
reply, and a sourced memory proposal recoverable in a later conversation.

This is channel-agnostic on purpose -- apps/cli/jarvis.py is the first
caller, a future Telegram adapter (docs/06-roadmap.md Faza B.1) is meant
to call the same handle_message() rather than duplicate this flow.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from contracts.models import Event
from contracts.reasoning import ContextItem, ReasoningBackend, ReasoningRequest
from storage.sqlite_store import SqliteEventStore

CONTEXT_WINDOW = 5


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def gather_context(
    store: SqliteEventStore, session_id: str, limit: int = CONTEXT_WINDOW, exclude_event_id: str | None = None
) -> list[ContextItem]:
    """Naive recency-based retrieval: the last few prior messages from this
    session, plus the last few memory candidates from any session. Not
    semantic search -- good enough for Milestone 0.1, and swappable later
    without changing handle_message's contract with callers."""

    items: list[ContextItem] = []

    session_events = [
        e for e in store.list_by_type("session.message")
        if e.payload.get("session_id") == session_id and e.id != exclude_event_id
    ]
    for event in session_events[-limit:]:
        items.append(ContextItem(text=event.payload["text"], source_event_id=event.id))

    for event in store.list_by_type("memory.candidate_proposed")[-limit:]:
        items.append(ContextItem(text=event.payload["statement"], source_event_id=event.id))

    return items


def handle_message(conn: sqlite3.Connection, backend: ReasoningBackend, session_id: str, text: str) -> str:
    """Record the user's input, retrieve context, ask the backend, record
    its reply, and durably propose any memory candidates it suggested.
    Returns the reply text."""

    store = SqliteEventStore(conn)

    input_event = store.append(Event(
        id=_new_id("session-msg"), schema_version=1, occurred_at=_iso_now(),
        type="session.message", source="cli",
        payload={"session_id": session_id, "role": "user", "text": text},
    ))

    context = gather_context(store, session_id, exclude_event_id=input_event.id)

    response = backend.respond(ReasoningRequest(
        session_id=session_id,
        input_text=text,
        input_event_id=input_event.id,
        context=context,
    ))

    store.append(Event(
        id=_new_id("session-msg"), schema_version=1, occurred_at=_iso_now(),
        type="session.message", source="cli",
        payload={"session_id": session_id, "role": "assistant", "text": response.text},
    ))

    for proposal in response.proposed_memories:
        store.append(Event(
            id=_new_id("memory-event"), schema_version=1, occurred_at=_iso_now(),
            type="memory.candidate_proposed", source="cli",
            payload={
                "candidate_id": _new_id("mem"),
                "statement": proposal.statement,
                "confidence": proposal.confidence,
                "source_event_ids": proposal.source_event_ids or [input_event.id],
            },
        ))

    return response.text
