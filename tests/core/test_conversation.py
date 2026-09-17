"""Exercises README.md's Milestone 0.1 end to end against EchoBackend:
say an idea, get it recorded durably, retrieve context, get a reply, get
a sourced memory proposal, and recover it in a later turn."""

import tempfile
import unittest
from pathlib import Path

from backends.echo import EchoBackend
from core.conversation import gather_context, handle_message
from storage.sqlite_store import SqliteEventStore, connect


class TestConversation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.backend = EchoBackend()

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_message_is_recorded_and_answered(self):
        reply = handle_message(self.conn, self.backend, "sess-1", "Prefer instrumente local-first")
        self.assertIn("local-first", reply)

        store = SqliteEventStore(self.conn)
        messages = store.list_by_type("session.message")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].payload["role"], "user")
        self.assertEqual(messages[1].payload["role"], "assistant")

    def test_long_input_proposes_a_sourced_memory_candidate(self):
        handle_message(self.conn, self.backend, "sess-1", "Prefer instrumente local-first pentru munca mea")

        store = SqliteEventStore(self.conn)
        candidates = store.list_by_type("memory.candidate_proposed")
        self.assertEqual(len(candidates), 1)

        user_message = store.list_by_type("session.message")[0]
        self.assertIn(user_message.id, candidates[0].payload["source_event_ids"])

    def test_short_input_does_not_propose_a_memory(self):
        handle_message(self.conn, self.backend, "sess-1", "salut")

        store = SqliteEventStore(self.conn)
        self.assertEqual(store.list_by_type("memory.candidate_proposed"), [])

    def test_context_is_recoverable_in_a_later_turn(self):
        handle_message(self.conn, self.backend, "sess-1", "Prefer instrumente local-first pentru munca mea")
        second_reply = handle_message(self.conn, self.backend, "sess-1", "Ce ai reținut despre preferințele mele?")

        self.assertIn("context: 3 item(s)", second_reply)  # 2 prior messages + 1 memory candidate

    def test_context_does_not_include_the_current_message_itself(self):
        from contracts.models import Event
        store = SqliteEventStore(self.conn)
        current = store.append(Event(
            id="evt-current", schema_version=1, occurred_at="2026-09-17T12:00:00Z",
            type="session.message", source="test",
            payload={"session_id": "sess-1", "role": "user", "text": "current turn"},
        ))
        context = gather_context(store, "sess-1", exclude_event_id=current.id)
        self.assertNotIn(current.id, [c.source_event_id for c in context])

    def test_raw_messages_do_not_leak_across_sessions(self):
        # Short inputs (< 4 words) so no memory candidate is created --
        # memory candidates are deliberately global/cross-session recall,
        # unlike raw session messages, which are scoped per session_id.
        handle_message(self.conn, self.backend, "sess-1", "salut")
        reply = handle_message(self.conn, self.backend, "sess-2", "salut")

        self.assertNotIn("context:", reply)  # EchoBackend omits the note when context is empty


if __name__ == "__main__":
    unittest.main()
