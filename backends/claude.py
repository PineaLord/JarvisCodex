"""A real ReasoningBackend backed by the Anthropic Messages API.

Stdlib-only (urllib), consistent with the rest of the project. The API
key is read from ANTHROPIC_API_KEY and used only in the outgoing request
header -- never logged, never put in the ledger, never included in an
error message. Memory proposals come from an explicit tool call
(propose_memory) rather than parsing free text, so "worth remembering"
is a decision the model makes on purpose, not a regex guess.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from contracts.reasoning import MemoryCandidateProposal, ReasoningRequest, ReasoningResponse

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = (
    "Ești motorul de reasoning pentru JarvisCodex, un nucleu personal persistent și "
    "recuperabil. Primești doar contextul minim din acest mesaj -- nu ai memorie proprie "
    "între apeluri. Dacă ceva din conversație merită reținut durabil despre utilizator, "
    "preferințele sau proiectele lui, cheamă tool-ul propose_memory cu o afirmație clară, "
    "de sine stătătoare. Nu inventa fapte despre utilizator. Răspunde concis."
)

PROPOSE_MEMORY_TOOL = {
    "name": "propose_memory",
    "description": (
        "Propose a durable memory worth keeping about the user, their preferences, or "
        "their projects. Only call this for something genuinely worth remembering across "
        "conversations -- not for small talk or one-off questions."
    ),
    "input_schema": {
        "type": "object",
        "required": ["statement", "confidence"],
        "properties": {
            "statement": {"type": "string", "description": "A single, self-contained factual statement."},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
}


class ClaudeBackendError(RuntimeError):
    pass


class ClaudeBackend:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ClaudeBackendError("ANTHROPIC_API_KEY is not set")
        self._model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    def respond(self, request: ReasoningRequest) -> ReasoningResponse:
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": self._build_user_content(request)}],
            "tools": [PROPOSE_MEMORY_TOOL],
        }
        result = self._call(payload)
        return self._parse_response(result)

    def _build_user_content(self, request: ReasoningRequest) -> str:
        if not request.context:
            return request.input_text
        context_block = "\n".join(f"- {item.text}" for item in request.context)
        return f"Context relevant din conversații anterioare:\n{context_block}\n\nMesaj nou: {request.input_text}"

    def _call(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API_URL, data=data, method="POST",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ClaudeBackendError(f"Anthropic API returned HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise ClaudeBackendError(f"Anthropic API call failed: {e}") from e

    def _parse_response(self, result: dict) -> ReasoningResponse:
        text_parts = []
        proposals = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name") == "propose_memory":
                tool_input = block.get("input", {})
                if "statement" in tool_input and "confidence" in tool_input:
                    proposals.append(MemoryCandidateProposal(
                        statement=tool_input["statement"],
                        confidence=float(tool_input["confidence"]),
                    ))
        return ReasoningResponse(text="\n".join(text_parts).strip(), proposed_memories=proposals)
