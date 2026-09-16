"""The restore test required by docs/05-recovery.md.

Full scope there also includes encryption and a dry-run service boot,
which depend on the backup tooling and executor from later Faza A steps
(see docs/06-roadmap.md) and aren't built yet. This test covers the part
that's buildable now: a backup can be restored into a clean environment
and reproduce identical event history, hashes, and provenance-carrying
memory candidates.
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from contracts.models import Event
from storage.export import export_state
from storage.migrate import migrate
from storage.projections import rebuild_projections
from storage.sqlite_store import SqliteEventStore, SqliteMemoryStore, connect


def _event_log_hash(store: SqliteEventStore) -> str:
    canonical = json.dumps([e.to_dict() for e in store.all()], sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TestRestore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_backup_restores_into_clean_environment(self):
        # 1. Reference data in the "live" environment.
        live_dir = self.root / "live"
        live_dir.mkdir()
        live_db = live_dir / "jarvis.db"

        conn = connect(live_db)
        store = SqliteEventStore(conn)
        store.append(Event(
            id="evt-task", schema_version=1, occurred_at="2026-09-16T12:00:00Z",
            type="task.created", source="test",
            payload={"task_id": "task-1", "title": "Prove restore works"},
        ))
        store.append(Event(
            id="evt-memory", schema_version=1, occurred_at="2026-09-16T12:01:00Z",
            type="memory.candidate_proposed", source="test",
            payload={
                "candidate_id": "mem-1",
                "statement": "User values a recoverable core",
                "confidence": 0.9,
                "source_event_ids": ["evt-task"],
            },
        ))
        export_state(conn, live_dir / "export")

        live_event_count = len(store.all())
        live_hash = _event_log_hash(store)
        live_memory = SqliteMemoryStore(conn).get("mem-1")
        conn.close()

        # 2. Backup: copy the ledger file. (Encryption is a follow-up step;
        # see docs/05-recovery.md and docs/06-roadmap.md Faza A.3.)
        backup_path = self.root / "backups" / "jarvis.db.bak"
        backup_path.parent.mkdir()
        shutil.copy2(live_db, backup_path)

        # 3. Restore into a clean, empty environment.
        restored_dir = self.root / "restored-clean-machine"
        restored_dir.mkdir()
        restored_db = restored_dir / "jarvis.db"
        shutil.copy2(backup_path, restored_db)

        restored_conn = connect(restored_db)  # must apply/skip migrations without error
        applied_again = migrate(restored_conn)
        self.assertEqual(applied_again, [], "restoring a backup must not re-run migrations")

        restored_store = SqliteEventStore(restored_conn)

        # 4. Verify: event count, hashes, memory with provenance.
        self.assertEqual(len(restored_store.all()), live_event_count)
        self.assertEqual(_event_log_hash(restored_store), live_hash)

        restored_memory = SqliteMemoryStore(restored_conn).get("mem-1")
        self.assertIsNotNone(restored_memory)
        self.assertEqual(restored_memory.statement, live_memory.statement)
        self.assertEqual(restored_memory.source_event_ids, live_memory.source_event_ids)
        self.assertIn("evt-task", restored_memory.source_event_ids)

        # 5. Projections are reproducible from the restored log alone --
        # this is the actual "recoverable brain" guarantee, not just file copying.
        rebuild_projections(restored_conn)
        task = restored_conn.execute(
            "SELECT title FROM tasks WHERE id = 'task-1'"
        ).fetchone()
        self.assertEqual(task, ("Prove restore works",))

        restored_conn.close()


if __name__ == "__main__":
    unittest.main()
