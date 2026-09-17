#!/usr/bin/env python3
"""Telegram channel adapter. See docs/01-architecture.md and
docs/06-roadmap.md Faza B.1.

Only messages from TELEGRAM_ALLOWED_USERS are ever routed to
core.conversation.handle_message; everyone else is rejected and the
rejection is recorded as a channel.message_rejected event, so
unauthorized contact attempts are auditable in the same ledger as
everything else. The bot token never enters the ledger or reasoning
context -- it's only ever used by TelegramClient's outgoing HTTP calls.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apps.telegram.client import TelegramApiError, TelegramClient  # noqa: E402
from backends.echo import EchoBackend  # noqa: E402
from contracts.models import Event  # noqa: E402
from contracts.reasoning import ReasoningBackend  # noqa: E402
from core.conversation import handle_message  # noqa: E402
from storage.sqlite_store import SqliteEventStore, connect  # noqa: E402


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_allowed_users(raw: str) -> set[str]:
    return {u.strip() for u in raw.split(",") if u.strip()}


def process_updates(conn, backend: ReasoningBackend, client, updates: list[dict], allowed_users: set[str]) -> int:
    """Handle one batch of Telegram updates. Returns the highest update_id
    seen (-1 if the batch was empty), so the caller can advance its
    polling offset past rejected messages too, not just accepted ones."""

    store = SqliteEventStore(conn)
    highest_update_id = -1

    for update in updates:
        highest_update_id = max(highest_update_id, update.get("update_id", -1))
        message = update.get("message")
        if not message or "text" not in message:
            continue  # non-text updates (edits, channel posts, etc.) are out of scope

        chat_id = message["chat"]["id"]
        from_id = str(message["from"]["id"])
        text = message["text"]
        session_id = f"telegram:{chat_id}"

        if from_id not in allowed_users:
            store.append(Event(
                id=f"channel-rejected-{update['update_id']}", schema_version=1, occurred_at=_iso_now(),
                type="channel.message_rejected", source="telegram",
                payload={
                    "channel": "telegram",
                    "external_user_id": from_id,
                    "reason": "not in TELEGRAM_ALLOWED_USERS",
                },
            ))
            continue

        reply = handle_message(conn, backend, session_id, text)
        client.send_message(chat_id, reply)

    return highest_update_id


def run_forever(
    conn, backend: ReasoningBackend, client, allowed_users: set[str],
    poll_timeout: int = 30, max_iterations: int | None = None, retry_delay_seconds: float = 5,
) -> None:
    offset = None
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        try:
            updates = client.get_updates(offset, timeout=poll_timeout)
        except TelegramApiError as e:
            print(f"Telegram poll failed, retrying: {e}", file=sys.stderr)
            time.sleep(retry_delay_seconds)
            continue

        highest = process_updates(conn, backend, client, updates, allowed_users)
        if highest >= 0:
            offset = highest + 1


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed_raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    data_dir = os.environ.get("JARVIS_CODEX_DATA_DIR")

    if not token or not allowed_raw or not data_dir:
        print(
            "Set TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS and JARVIS_CODEX_DATA_DIR "
            "(see .env.example and docs/01-architecture.md).",
            file=sys.stderr,
        )
        return 2

    allowed_users = parse_allowed_users(allowed_raw)
    conn = connect(Path(data_dir) / "jarvis.db")
    client = TelegramClient(token)

    print(f"JarvisCodex Telegram adapter running, {len(allowed_users)} allowed user(s).")
    run_forever(conn, EchoBackend(), client, allowed_users)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
