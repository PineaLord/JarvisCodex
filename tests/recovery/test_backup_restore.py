import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from contracts.models import Event
from recovery.backup import BackupError, create_backup
from recovery.restore import RestoreError, restore_backup
from storage.migrate import migrate
from storage.projections import rebuild_projections
from storage.sqlite_store import SqliteEventStore, connect

AGE_AVAILABLE = shutil.which("age") is not None and shutil.which("age-keygen") is not None


@unittest.skipUnless(AGE_AVAILABLE, "age / age-keygen not installed")
class TestEncryptedBackupRestore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

        # Ephemeral keypair for this test only -- never a real backup identity.
        self.identity_path = self.root / "identity.txt"
        keygen = subprocess.run(
            ["age-keygen", "-o", str(self.identity_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(keygen.returncode, 0, keygen.stderr)
        pubkey_line = [
            line for line in self.identity_path.read_text().splitlines()
            if line.startswith("# public key:")
        ][0]
        self.recipient = pubkey_line.split(":", 1)[1].strip()

        self.db_path = self.root / "jarvis.db"
        conn = connect(self.db_path)
        store = SqliteEventStore(conn)
        store.append(Event(
            id="evt-task", schema_version=1, occurred_at="2026-09-17T09:00:00Z",
            type="task.created", source="test",
            payload={"task_id": "task-1", "title": "Verify encrypted backup"},
        ))
        conn.close()

        self.out_dir = self.root / "backups"

    def tearDown(self):
        self._tmp.cleanup()

    def test_backup_then_restore_reproduces_state(self):
        archive_path, manifest_path = create_backup(self.db_path, self.out_dir, self.recipient)
        self.assertTrue(archive_path.exists())
        self.assertTrue(manifest_path.exists())

        restore_dir = self.root / "restored"
        restored_db = restore_backup(archive_path, manifest_path, self.identity_path, restore_dir)

        restored_conn = connect(restored_db)
        migrate(restored_conn)  # must be a no-op, not an error
        rebuild_projections(restored_conn)

        events = SqliteEventStore(restored_conn).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "evt-task")

        task = restored_conn.execute(
            "SELECT title FROM tasks WHERE id = 'task-1'"
        ).fetchone()
        self.assertEqual(task, ("Verify encrypted backup",))
        restored_conn.close()

    def test_restore_rejects_tampered_archive(self):
        archive_path, manifest_path = create_backup(self.db_path, self.out_dir, self.recipient)

        # Simulate corruption/tampering of the encrypted archive on disk.
        with archive_path.open("r+b") as f:
            f.seek(0)
            f.write(b"\x00" * 16)

        restore_dir = self.root / "restored-tampered"
        with self.assertRaises((RestoreError,)):
            restore_backup(archive_path, manifest_path, self.identity_path, restore_dir)

    def test_restore_with_wrong_identity_fails(self):
        archive_path, manifest_path = create_backup(self.db_path, self.out_dir, self.recipient)

        wrong_identity_path = self.root / "wrong-identity.txt"
        subprocess.run(["age-keygen", "-o", str(wrong_identity_path)], capture_output=True)

        restore_dir = self.root / "restored-wrong-key"
        with self.assertRaises(RestoreError):
            restore_backup(archive_path, manifest_path, wrong_identity_path, restore_dir)


class TestBackupWithoutAge(unittest.TestCase):
    @unittest.skipIf(AGE_AVAILABLE, "this test only makes sense when age is absent")
    def test_missing_age_raises_clear_error(self):
        with self.assertRaises(BackupError):
            create_backup("unused.db", "unused-out", "age1notarealrecipient")


if __name__ == "__main__":
    unittest.main()
