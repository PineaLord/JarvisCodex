"""Stable storage contracts.

Per docs/01-architecture.md, EventStore and MemoryStore are contracts that
must not break when a reasoning backend or plugin is swapped. Anything that
needs to read or write durable state should depend on these Protocols, not
on the SQLite implementation in storage/sqlite_store.py directly.
"""

from __future__ import annotations

from typing import Protocol

from contracts.models import Event, MemoryCandidate


class EventStore(Protocol):
    """Append-only ledger of immutable facts."""

    def append(self, event: Event) -> Event:
        """Validate and persist a new event. Never mutates or deletes."""
        ...

    def get(self, event_id: str) -> Event | None: ...

    def list_by_type(self, type_: str) -> list[Event]: ...

    def all(self) -> list[Event]:
        """All events in append order. Replaying this list must be able to
        reconstruct every projection from scratch."""
        ...


class MemoryStore(Protocol):
    """Candidate and approved memories, always traceable to source events."""

    def propose(self, candidate: MemoryCandidate) -> MemoryCandidate: ...

    def get(self, candidate_id: str) -> MemoryCandidate | None: ...

    def list(self, *, status: str | None = None) -> list[MemoryCandidate]: ...
