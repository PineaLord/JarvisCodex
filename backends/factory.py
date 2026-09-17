"""Picks a ReasoningBackend from JARVIS_CODEX_BACKEND (default: echo).

Kept in one place so the CLI and Telegram adapters can't drift apart on
which backend they use. Defaults to the free local backend: switching to
a paid provider must be an explicit opt-in, never a side effect of
reading a config file.
"""

from __future__ import annotations

import os

from contracts.reasoning import ReasoningBackend


def get_backend() -> ReasoningBackend:
    name = os.environ.get("JARVIS_CODEX_BACKEND", "echo").strip().lower()

    if name == "echo":
        from backends.echo import EchoBackend
        return EchoBackend()

    if name == "claude":
        from backends.claude import ClaudeBackend
        return ClaudeBackend()

    if name == "codex":
        from backends.codex_cli import CodexCliBackend
        return CodexCliBackend()

    raise ValueError(f"Unknown JARVIS_CODEX_BACKEND: {name!r} (expected 'echo', 'claude', or 'codex')")
