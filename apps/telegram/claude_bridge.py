#!/usr/bin/env python3
"""Telegram bridge to a real `claude` (Claude Code) session.

⚠️  NOT part of JarvisCodex's core control plane (docs/01-architecture.md).
Per docs/04-safety-model.md, the core promise is that no external effect
happens without policy-engine mediation (contracts/policy.py). This
bridge deliberately breaks that promise: every message is run with
`--permission-mode bypassPermissions`, meaning full, unrestricted file
and shell access, with no approval step. It exists only because the
sole authorized Telegram user (TELEGRAM_ALLOWED_USERS) *is* the person
who would otherwise be typing at the keyboard themselves -- it is not a
capability any plugin or autonomous loop gets. Do not import this
module from core/, policy/, or apps/telegram/bot.py, and do not wire it
into the event ledger's projections; keep it operationally separate so
the safe, policy-mediated path is never weakened by this one.

Do not run this at the same time as apps/telegram/bot.py against the
same bot token -- two independent long-pollers on one token will race.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apps.telegram.bot import parse_allowed_users  # noqa: E402
from apps.telegram.client import TelegramApiError, TelegramClient  # noqa: E402
from contracts.models import Event  # noqa: E402
from storage.sqlite_store import SqliteEventStore, connect  # noqa: E402

CLAUDE_BINARY = "claude"
DEFAULT_TIMEOUT_SECONDS = 300
NO_SESSION_MARKER = "No conversation found with session ID"

# Fixed, non-secret namespace for deterministic per-chat session ids
# (uuid.uuid5(SESSION_NAMESPACE, chat_id) is stable across restarts,
# so no separate bookkeeping file is needed).
SESSION_NAMESPACE = uuid.UUID("2f6a6b8e-6e3f-4c7a-9c0a-6a0a2b7c9e10")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_id_for_chat(chat_id) -> str:
    return str(uuid.uuid5(SESSION_NAMESPACE, str(chat_id)))


def run_claude(session_id: str, prompt: str, workdir: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Resume the chat's claude session; if it doesn't exist yet, start
    it fresh under that exact session id. Returns the parsed --output-format
    json result (has "result" for the reply text, "total_cost_usd", etc.)."""

    resume_cmd = [
        CLAUDE_BINARY, "-p", "--output-format", "json",
        "--resume", session_id, "--permission-mode", "bypassPermissions",
        prompt,
    ]
    result = subprocess.run(resume_cmd, capture_output=True, text=True, cwd=workdir, timeout=timeout)

    if result.returncode != 0 and NO_SESSION_MARKER in (result.stdout + result.stderr):
        start_cmd = [
            CLAUDE_BINARY, "-p", "--output-format", "json",
            "--session-id", session_id, "--permission-mode", "bypassPermissions",
            prompt,
        ]
        result = subprocess.run(start_cmd, capture_output=True, text=True, cwd=workdir, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr.strip()[-2000:]}")

    return json.loads(result.stdout)


def process_updates(conn, client, updates: list[dict], allowed_users: set[str], workdir: str, timeout: int) -> int:
    store = SqliteEventStore(conn)
    highest_update_id = -1

    for update in updates:
        highest_update_id = max(highest_update_id, update.get("update_id", -1))
        message = update.get("message")
        if not message or "text" not in message:
            continue

        chat_id = message["chat"]["id"]
        from_id = str(message["from"]["id"])
        text = message["text"]

        if from_id not in allowed_users:
            store.append(Event(
                id=f"channel-rejected-{update['update_id']}", schema_version=1, occurred_at=_iso_now(),
                type="channel.message_rejected", source="telegram-claude-bridge",
                payload={"channel": "telegram", "external_user_id": from_id, "reason": "not in TELEGRAM_ALLOWED_USERS"},
            ))
            continue

        session_id = session_id_for_chat(chat_id)
        try:
            result = run_claude(session_id, text, workdir, timeout)
            reply = result.get("result") or "(fără răspuns)"
            client.send_message(chat_id, reply)
            store.append(Event(
                id=f"bridge-{update['update_id']}", schema_version=1, occurred_at=_iso_now(),
                type="bridge.claude_message", source="telegram-claude-bridge",
                payload={
                    "claude_session_id": session_id,
                    "cost_usd": result.get("total_cost_usd", 0),
                    "duration_ms": result.get("duration_ms", 0),
                },
            ))
        except Exception as e:
            print(f"claude bridge failed for chat {chat_id}: {e}", file=sys.stderr)
            try:
                client.send_message(chat_id, "A apărut o eroare la procesarea mesajului. Încearcă din nou.")
            except Exception:
                pass

    return highest_update_id


def run_forever(
    conn, client, allowed_users: set[str], workdir: str,
    poll_timeout: int = 30, claude_timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_iterations: int | None = None, retry_delay_seconds: float = 5,
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

        highest = process_updates(conn, client, updates, allowed_users, workdir, claude_timeout)
        if highest >= 0:
            offset = highest + 1


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed_raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    data_dir = os.environ.get("JARVIS_CODEX_DATA_DIR")
    workdir = os.environ.get("JARVIS_CLAUDE_BRIDGE_WORKDIR", os.path.expanduser("~"))

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

    print("=" * 70)
    print("JarvisCodex Claude bridge: FULL, UNRESTRICTED claude access.")
    print(f"Working directory: {workdir}")
    print(f"Allowed user(s): {len(allowed_users)}")
    print("Every message can edit files or run commands on this machine.")
    print("This bypasses the JarvisCodex policy engine entirely, on purpose.")
    print("=" * 70)

    run_forever(conn, client, allowed_users, workdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
