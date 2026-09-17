"""Stable reasoning contract. See docs/01-architecture.md.

The model is a replaceable backend, not the core: it receives minimal
context and proposes a response plus candidate memories. It never sees
secrets, and it never decides its own risk level (contracts/policy.py) or
executes anything -- that's the policy engine and executor's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ContextItem:
    """A piece of retrieved context, always traceable to the event it came from."""

    text: str
    source_event_id: str


@dataclass(frozen=True)
class ReasoningRequest:
    session_id: str
    input_text: str
    input_event_id: str
    context: list[ContextItem] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryCandidateProposal:
    statement: str
    confidence: float
    source_event_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReasoningResponse:
    text: str
    proposed_memories: list[MemoryCandidateProposal] = field(default_factory=list)


class ReasoningBackend(Protocol):
    def respond(self, request: ReasoningRequest) -> ReasoningResponse: ...
