"""End-to-end tests of the CLI adapter as an actual subprocess, so a
regression in argument parsing or wiring shows up here, not just in the
functions it calls."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent.parent / "apps" / "cli" / "jarvis.py"


class TestCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"JARVIS_CODEX_DATA_DIR": self._tmp.name, "PATH": "/usr/bin:/bin"}

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True, text=True, env=self.env,
        )

    def test_healthcheck_reports_ok_on_a_fresh_database(self):
        result = self._run("healthcheck")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["database"], "ok")
        self.assertEqual(report["migrations_pending"], [])

    def test_status_reports_zero_counts_on_a_fresh_database(self):
        result = self._run("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        counts = json.loads(result.stdout)
        self.assertEqual(counts["events"], 0)

    def test_chat_then_status_reflects_the_new_memory_candidate(self):
        chat = self._run("chat", "sess-1", "Prefer instrumente local-first pentru munca mea")
        self.assertEqual(chat.returncode, 0, chat.stderr)
        self.assertIn("local-first", chat.stdout)

        status = json.loads(self._run("status").stdout)
        self.assertEqual(status["events"], 3)  # user msg, assistant msg, memory candidate
        self.assertEqual(status["memory_candidates"], 1)

    def test_approvals_list_is_empty_on_a_fresh_database(self):
        result = self._run("approvals", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No pending approvals", result.stdout)

    def test_kill_is_an_honest_noop(self):
        result = self._run("kill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("to stop yet", result.stdout)

    def test_heartbeat_runs_on_a_fresh_database(self):
        result = self._run("heartbeat")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Consolidare", result.stdout)

    def test_status_includes_faza_c_counts(self):
        counts = json.loads(self._run("status").stdout)
        self.assertIn("signals", counts)
        self.assertIn("initiatives_proposed", counts)
        self.assertIn("goals_active", counts)


if __name__ == "__main__":
    unittest.main()
