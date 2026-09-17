import tempfile
import unittest
from pathlib import Path

from contracts.models import Event
from storage.projections import rebuild_projections
from storage.sqlite_store import SqliteEventStore, connect


class TestProjections(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "jarvis.db"
        self.conn = connect(self.db_path)
        self.store = SqliteEventStore(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _seed(self):
        self.store.append(Event(
            id="evt-task", schema_version=1, occurred_at="2026-09-16T12:00:00Z",
            type="task.created", source="test",
            payload={"task_id": "task-1", "title": "Write restore test"},
        ))
        self.store.append(Event(
            id="evt-approval-req", schema_version=1, occurred_at="2026-09-16T12:01:00Z",
            type="approval.requested", source="test",
            payload={
                "approval_id": "appr-1", "level": "L3", "description": "Install a package",
                "expires_at": "2026-09-16T13:01:00Z",
            },
        ))
        self.store.append(Event(
            id="evt-approval-dec", schema_version=1, occurred_at="2026-09-16T12:02:00Z",
            type="approval.decided", source="test",
            payload={"approval_id": "appr-1", "decision": "approved"},
        ))
        self.store.append(Event(
            id="evt-memory", schema_version=1, occurred_at="2026-09-16T12:03:00Z",
            type="memory.candidate_proposed", source="test",
            payload={
                "candidate_id": "mem-1",
                "statement": "User prefers local-first tools",
                "confidence": 0.7,
                "source_event_ids": ["evt-task"],
            },
        ))

    def test_projections_fold_incrementally(self):
        self._seed()

        task = self.conn.execute("SELECT title, status FROM tasks WHERE id = 'task-1'").fetchone()
        self.assertEqual(task, ("Write restore test", "open"))

        approval = self.conn.execute(
            "SELECT status FROM approvals WHERE id = 'appr-1'"
        ).fetchone()
        self.assertEqual(approval, ("approved",))

        memory = self.conn.execute(
            "SELECT status FROM memory_candidates WHERE id = 'mem-1'"
        ).fetchone()
        self.assertEqual(memory, ("proposed",))

    def test_rebuild_matches_incremental_state(self):
        self._seed()

        before = self._snapshot()
        rebuild_projections(self.conn)
        after = self._snapshot()

        self.assertEqual(before, after)

    def _snapshot(self):
        return {
            "tasks": self.conn.execute("SELECT * FROM tasks ORDER BY id").fetchall(),
            "approvals": self.conn.execute("SELECT * FROM approvals ORDER BY id").fetchall(),
            "memory_candidates": self.conn.execute(
                "SELECT * FROM memory_candidates ORDER BY id"
            ).fetchall(),
        }


if __name__ == "__main__":
    unittest.main()
