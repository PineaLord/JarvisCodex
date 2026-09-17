"""Tests apps/telegram/bot.py against a fake TelegramClient -- no real
network call and no real bot token, since neither exists in CI or dev
sandboxes. This still exercises the part that actually matters: auth
against the allowlist, routing to core.conversation, and reply delivery."""

import tempfile
import unittest
from pathlib import Path

from apps.telegram.bot import parse_allowed_users, process_updates, run_forever
from apps.telegram.client import TelegramApiError
from backends.echo import EchoBackend
from storage.sqlite_store import SqliteEventStore, connect


def make_update(update_id: int, user_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": user_id},
            "text": text,
        },
    }


class FakeTelegramClient:
    def __init__(self, get_updates_results=None):
        self.sent: list[tuple] = []
        self._results = list(get_updates_results or [])

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    def get_updates(self, offset, timeout=30):
        if not self._results:
            return []
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class TestParseAllowedUsers(unittest.TestCase):
    def test_parses_comma_separated_ids(self):
        self.assertEqual(parse_allowed_users("111, 222,333"), {"111", "222", "333"})

    def test_empty_string_yields_empty_set(self):
        self.assertEqual(parse_allowed_users(""), set())


class TestProcessUpdates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.backend = EchoBackend()
        self.allowed = {"42"}

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_authorized_message_gets_a_reply(self):
        client = FakeTelegramClient()
        updates = [make_update(1, user_id=42, chat_id=999, text="salut")]

        highest = process_updates(self.conn, self.backend, client, updates, self.allowed)

        self.assertEqual(highest, 1)
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0][0], 999)

    def test_unauthorized_message_is_rejected_and_audited(self):
        client = FakeTelegramClient()
        updates = [make_update(1, user_id=1337, chat_id=999, text="cine esti")]

        process_updates(self.conn, self.backend, client, updates, self.allowed)

        self.assertEqual(client.sent, [])
        rejected = SqliteEventStore(self.conn).list_by_type("channel.message_rejected")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].payload["external_user_id"], "1337")

        messages = SqliteEventStore(self.conn).list_by_type("session.message")
        self.assertEqual(messages, [])

    def test_non_text_update_is_skipped_without_error(self):
        client = FakeTelegramClient()
        updates = [{"update_id": 5, "edited_message": {"chat": {"id": 1}, "text": "edit"}}]

        highest = process_updates(self.conn, self.backend, client, updates, self.allowed)
        self.assertEqual(highest, 5)
        self.assertEqual(client.sent, [])

    def test_highest_update_id_is_the_max_not_the_last(self):
        client = FakeTelegramClient()
        updates = [
            make_update(3, user_id=42, chat_id=1, text="a"),
            make_update(1, user_id=42, chat_id=1, text="b"),
        ]
        highest = process_updates(self.conn, self.backend, client, updates, self.allowed)
        self.assertEqual(highest, 3)

    def test_empty_batch_returns_negative_one(self):
        client = FakeTelegramClient()
        self.assertEqual(process_updates(self.conn, self.backend, client, [], self.allowed), -1)

    def test_backend_failure_on_one_message_does_not_crash_the_batch(self):
        class BrokenBackend:
            def respond(self, request):
                raise RuntimeError("simulated backend outage")

        client = FakeTelegramClient()
        updates = [
            make_update(1, user_id=42, chat_id=1, text="primul"),
            make_update(2, user_id=42, chat_id=1, text="al doilea"),
        ]

        highest = process_updates(self.conn, BrokenBackend(), client, updates, self.allowed)

        self.assertEqual(highest, 2)  # offset still advances past both
        self.assertEqual(len(client.sent), 2)  # an apology reply for each, not a crash
        for _chat_id, text in client.sent:
            self.assertIn("eroare", text)

        # The user's messages were still durably recorded before the backend call failed.
        messages = SqliteEventStore(self.conn).list_by_type("session.message")
        self.assertEqual(len(messages), 2)


class TestRunForever(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_survives_a_transient_api_error_and_keeps_polling(self):
        client = FakeTelegramClient(get_updates_results=[
            TelegramApiError("simulated network blip"),
            [make_update(1, user_id=42, chat_id=1, text="salut")],
        ])
        run_forever(
            self.conn, EchoBackend(), client, {"42"},
            poll_timeout=1, max_iterations=2, retry_delay_seconds=0,
        )
        self.assertEqual(len(client.sent), 1)


if __name__ == "__main__":
    unittest.main()
