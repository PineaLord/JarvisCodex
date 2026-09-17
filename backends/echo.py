"""A local, free, deterministic ReasoningBackend.

No API key, no network call, no cost -- exists to prove that the ledger,
session events, retrieval and memory-candidate flow all work end to end
before any real provider is wired in. Swap this for backends/claude.py
(or Codex, or a local model) behind the same contracts.reasoning.ReasoningBackend
Protocol; nothing else in the codebase needs to change.
"""

from __future__ import annotations

from contracts.reasoning import MemoryCandidateProposal, ReasoningRequest, ReasoningResponse


class EchoBackend:
    """Reflects the input back, noting how much context it saw, and
    proposes the input itself as a memory candidate when it looks like a
    statement worth remembering (more than a few words)."""

    def respond(self, request: ReasoningRequest) -> ReasoningResponse:
        context_note = f" (context: {len(request.context)} item(s))" if request.context else ""
        text = f"Am notat: {request.input_text!r}{context_note}"

        proposed_memories = []
        if len(request.input_text.split()) >= 4:
            proposed_memories.append(MemoryCandidateProposal(
                statement=request.input_text,
                confidence=0.5,
                source_event_ids=[request.input_event_id],
            ))

        return ReasoningResponse(text=text, proposed_memories=proposed_memories)
