"""Tests apps/telegram/claude_bridge.py against a mocked subprocess.run
-- this module runs `claude` with --permission-mode bypassPermissions,
which the assistant is not allowed to execute directly (Claude Code's
own auto-mode classifier blocks it as "Create Unsafe Agents"), so the
session-continuity mechanics here were verified manually by the user
against the real `claude` binary (see conversation record), not by an
automated test running the real command."""

import json
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from apps.telegram.claude_bridge import (
    process_updates,
    run_claude,
    session_id_for_chat,
)
from storage.sqlite_store import SqliteEventStore, connect


def make_update(update_id: int, user_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": text},
    }


class FakeTelegramClient:
    def __init__(self):
        self.sent: list[tuple] = []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


class TestSessionIdForChat(unittest.TestCase):
    def test_deterministic_across_calls(self):
        self.assertEqual(session_id_for_chat(12345), session_id_for_chat(12345))

    def test_different_per_chat(self):
        self.assertNotEqual(session_id_for_chat(1), session_id_for_chat(2))


class TestRunClaude(unittest.TestCase):
    def test_resumes_when_session_exists(self):
        completed = subprocess.CompletedProcess(
            [], returncode=0, stdout=json.dumps({"result": "42", "total_cost_usd": 0.01, "duration_ms": 500}), stderr="",
        )
        with unittest.mock.patch("apps.telegram.claude_bridge.subprocess.run", return_value=completed) as run:
            result = run_claude("sess-1", "ce numar?", "/tmp")
        self.assertEqual(result["result"], "42")
        self.assertIn("--resume", run.call_args.args[0])

    def test_falls_back_to_session_id_when_no_prior_session(self):
        not_found = subprocess.CompletedProcess(
            [], returncode=1, stdout="", stderr="No conversation found with session ID: sess-1",
        )
        started = subprocess.CompletedProcess(
            [], returncode=0, stdout=json.dumps({"result": "ok", "total_cost_usd": 0.0, "duration_ms": 100}), stderr="",
        )
        with unittest.mock.patch(
            "apps.telegram.claude_bridge.subprocess.run", side_effect=[not_found, started],
        ) as run:
            result = run_claude("sess-1", "salut", "/tmp")
        self.assertEqual(result["result"], "ok")
        self.assertEqual(run.call_count, 2)
        self.assertIn("--session-id", run.call_args.args[0])

    def test_other_failures_are_not_swallowed(self):
        failed = subprocess.CompletedProcess([], returncode=1, stdout="", stderr="some other real error")
        with unittest.mock.patch("apps.telegram.claude_bridge.subprocess.run", return_value=failed):
            with self.assertRaises(RuntimeError):
                run_claude("sess-1", "salut", "/tmp")


class TestProcessUpdates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.allowed = {"42"}

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_authorized_message_is_routed_to_claude_and_replied(self):
        client = FakeTelegramClient()
        updates = [make_update(1, user_id=42, chat_id=999, text="salut")]
        completed = subprocess.CompletedProcess(
            [], returncode=0, stdout=json.dumps({"result": "buna!", "total_cost_usd": 0.02, "duration_ms": 800}), stderr="",
        )
        with unittest.mock.patch("apps.telegram.claude_bridge.subprocess.run", return_value=completed):
            highest = process_updates(self.conn, client, updates, self.allowed, "/tmp", 60)

        self.assertEqual(highest, 1)
        self.assertEqual(client.sent, [(999, "buna!")])

        events = SqliteEventStore(self.conn).list_by_type("bridge.claude_message")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["cost_usd"], 0.02)

    def test_unauthorized_message_never_reaches_claude(self):
        client = FakeTelegramClient()
        updates = [make_update(1, user_id=1337, chat_id=999, text="cine esti")]

        with unittest.mock.patch("apps.telegram.claude_bridge.subprocess.run") as run:
            process_updates(self.conn, client, updates, self.allowed, "/tmp", 60)

        run.assert_not_called()
        self.assertEqual(client.sent, [])
        rejected = SqliteEventStore(self.conn).list_by_type("channel.message_rejected")
        self.assertEqual(len(rejected), 1)

    def test_claude_failure_does_not_crash_the_batch(self):
        client = FakeTelegramClient()
        updates = [
            make_update(1, user_id=42, chat_id=1, text="primul"),
            make_update(2, user_id=42, chat_id=1, text="al doilea"),
        ]
        failed = subprocess.CompletedProcess([], returncode=1, stdout="", stderr="boom")
        with unittest.mock.patch("apps.telegram.claude_bridge.subprocess.run", return_value=failed):
            highest = process_updates(self.conn, client, updates, self.allowed, "/tmp", 60)

        self.assertEqual(highest, 2)
        self.assertEqual(len(client.sent), 2)
        for _chat_id, text in client.sent:
            self.assertIn("eroare", text)


if __name__ == "__main__":
    unittest.main()
