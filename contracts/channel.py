"""ChannelAdapter contract. See docs/01-architecture.md.

A channel's only job is authenticating who's talking and moving text
across the wire; core/conversation.handle_message is the actual loop.
CLI is simple enough to call that directly (apps/cli/jarvis.py) -- this
contract is for adapters that run as a persistent process, like
Telegram, so a future one doesn't reinvent polling/auth/reply plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InboundMessage:
    session_id: str
    external_user_id: str
    text: str


class ChannelAdapter(Protocol):
    def poll(self) -> list[InboundMessage]: ...

    def send(self, session_id: str, text: str) -> None: ...
