import tempfile
import unittest
from pathlib import Path

from contracts.models import Event
from contracts.schema_validation import SchemaValidationError
from storage.migrate import migrate
from storage.sqlite_store import SqliteEventStore, connect


def make_event(id_="evt-1", type_="task.created", payload=None) -> Event:
    return Event(
        id=id_,
        schema_version=1,
        occurred_at="2026-09-16T12:00:00Z",
        type=type_,
        source="test",
        payload=payload or {"task_id": "task-1", "title": "Do the thing"},
    )


class TestSqliteLedger(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "jarvis.db"

    def tearDown(self):
        self._tmp.cleanup()

    def test_append_and_get_roundtrip(self):
        conn = connect(self.db_path)
        store = SqliteEventStore(conn)
        store.append(make_event())

        fetched = store.get("evt-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.type, "task.created")
        self.assertEqual(fetched.payload["title"], "Do the thing")

    def test_invalid_event_is_rejected_before_insert(self):
        conn = connect(self.db_path)
        store = SqliteEventStore(conn)
        bad = make_event(type_="Invalid Type")
        with self.assertRaises(SchemaValidationError):
            store.append(bad)
        self.assertEqual(store.all(), [])

    def test_invalid_payload_for_known_type_is_rejected(self):
        conn = connect(self.db_path)
        store = SqliteEventStore(conn)
        bad = make_event(payload={"title": "missing task_id"})
        with self.assertRaises(SchemaValidationError):
            store.append(bad)

    def test_events_are_returned_in_append_order(self):
        conn = connect(self.db_path)
        store = SqliteEventStore(conn)
        store.append(make_event(id_="evt-1"))
        store.append(make_event(id_="evt-2"))
        store.append(make_event(id_="evt-3"))

        ids = [e.id for e in store.all()]
        self.assertEqual(ids, ["evt-1", "evt-2", "evt-3"])

    def test_migrate_is_idempotent(self):
        conn = connect(self.db_path)
        first_run = migrate(conn)  # already applied by connect()
        self.assertEqual(first_run, [])

        second_run = migrate(conn)
        self.assertEqual(second_run, [])

        # Re-opening the database must not re-apply or fail either.
        conn.close()
        reconnected = connect(self.db_path)
        self.assertEqual(migrate(reconnected), [])


if __name__ == "__main__":
    unittest.main()
