"""A ReasoningBackend that shells out to the local `codex` CLI
(non-interactively, via `codex exec`), so JarvisCodex can reuse an
existing ChatGPT/Codex subscription instead of a metered API key.

Runs in a freshly created, empty scratch directory with
`--sandbox read-only` and `--skip-git-repo-check`, so it never sees the
user's real files or repositories and can't write or execute anything --
it's used purely as a text-in, text-out reasoning engine, same contract
as any other backend. No secret ever passes through this module: `codex`
manages its own ChatGPT auth in `~/.codex/auth.json`.

Memory proposals are parsed from a single trailing marker line (there is
no tool-use mechanism over this interface, unlike backends/claude.py),
stripped from the visible reply before it's returned.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from contracts.reasoning import MemoryCandidateProposal, ReasoningRequest, ReasoningResponse

DEFAULT_BINARY = "codex"
DEFAULT_TIMEOUT_SECONDS = 120

MEMORY_MARKER_RE = re.compile(r"^MEMORY:\s*(.+?)\s*\|\s*confidence=([0-9.]+)\s*$", re.MULTILINE)

PROMPT_PREAMBLE = (
    "Ești motorul de reasoning pentru JarvisCodex, un nucleu personal persistent. "
    "Primești doar contextul minim din acest mesaj -- nu ai memorie proprie între apeluri. "
    "Răspunde concis, ca text simplu, fără instrumente sau acțiuni pe fișiere. "
    "Dacă ceva merită reținut durabil despre utilizator, preferințele sau proiectele lui, "
    "adaugă pe ultimul rând, EXACT în acest format: MEMORY: <afirmație> | confidence=<0-1>. "
    "Altfel nu adăuga acel rând deloc."
)


class CodexCliBackendError(RuntimeError):
    pass


class CodexCliBackend:
    def __init__(self, binary: str = DEFAULT_BINARY, timeout: int = DEFAULT_TIMEOUT_SECONDS, model: str | None = None):
        if shutil.which(binary) is None:
            raise CodexCliBackendError(f"{binary!r} is not on PATH")
        self._binary = binary
        self._timeout = timeout
        self._model = model

    def respond(self, request: ReasoningRequest) -> ReasoningResponse:
        prompt = self._build_prompt(request)
        scratch_dir = tempfile.mkdtemp(prefix="jarviscodex-codexcli-")
        out_fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="jarviscodex-codexcli-out-")
        os.close(out_fd)

        try:
            cmd = [
                self._binary, "exec",
                "--skip-git-repo-check", "--ephemeral",
                "--sandbox", "read-only",
                "-C", scratch_dir,
                "-o", out_path,
            ]
            if self._model:
                cmd += ["-m", self._model]
            cmd.append(prompt)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout, stdin=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                raise CodexCliBackendError(
                    f"codex exec failed (exit {result.returncode}): {result.stderr.strip()[-2000:]}"
                )
            raw_reply = Path(out_path).read_text(encoding="utf-8").strip()
        except subprocess.TimeoutExpired as e:
            raise CodexCliBackendError(f"codex exec timed out after {self._timeout}s") from e
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)
            Path(out_path).unlink(missing_ok=True)

        return self._parse_reply(raw_reply)

    def _build_prompt(self, request: ReasoningRequest) -> str:
        parts = [PROMPT_PREAMBLE]
        if request.context:
            context_block = "\n".join(f"- {item.text}" for item in request.context)
            parts.append(f"Context relevant din conversații anterioare:\n{context_block}")
        parts.append(f"Mesaj nou: {request.input_text}")
        return "\n\n".join(parts)

    def _parse_reply(self, raw_reply: str) -> ReasoningResponse:
        match = MEMORY_MARKER_RE.search(raw_reply)
        if not match:
            return ReasoningResponse(text=raw_reply, proposed_memories=[])

        statement, confidence = match.group(1), match.group(2)
        text = MEMORY_MARKER_RE.sub("", raw_reply).strip()
        return ReasoningResponse(
            text=text,
            proposed_memories=[MemoryCandidateProposal(statement=statement, confidence=float(confidence))],
        )
