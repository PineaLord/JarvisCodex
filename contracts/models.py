"""Typed models mirroring the versioned JSON schemas in schemas/.

These are plain dataclasses, not ORM models: the SQLite ledger in storage/
is the transactional source of truth, and these types are how the rest of
the codebase (contracts, projections, future backends) talks about that
state without depending on storage internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    """An immutable fact appended to the ledger. See schemas/event.v1.json."""

    id: str
    schema_version: int
    occurred_at: str
    type: str
    source: str
    payload: dict
    parent_id: str | None = None
    correlation_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at,
            "type": self.type,
            "source": self.source,
            "parent_id": self.parent_id,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }

    @staticmethod
    def from_dict(data: dict) -> "Event":
        return Event(
            id=data["id"],
            schema_version=data["schema_version"],
            occurred_at=data["occurred_at"],
            type=data["type"],
            source=data["source"],
            payload=data.get("payload", {}),
            parent_id=data.get("parent_id"),
            correlation_id=data.get("correlation_id"),
        )


@dataclass(frozen=True)
class TaskState:
    """Materialized view of a task, folded from task.* events."""

    id: str
    title: str
    status: str
    created_from_event: str
    updated_from_event: str


@dataclass(frozen=True)
class ApprovalState:
    """Materialized view of an approval request, folded from approval.* events."""

    id: str
    level: str
    description: str
    status: str
    requested_from_event: str
    decided_from_event: str | None = None


@dataclass(frozen=True)
class MemoryCandidate:
    """A proposed memory awaiting review. See docs/02-state-and-memory.md."""

    id: str
    statement: str
    confidence: float
    source_event_ids: list[str]
    status: str
    reviewed_at: str | None = None
    retention_policy: str = "default"
