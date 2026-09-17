import tempfile
import unittest
from pathlib import Path

from contracts.policy import ActionRequest
from policy.engine import RuleBasedPolicyEngine
from policy.executor import DryRunExecutor
from storage.sqlite_store import connect


class TestPolicyEngineBasics(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.engine = RuleBasedPolicyEngine(self.conn)
        self.executor = DryRunExecutor(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_l0_action_is_allowed_and_simulated(self):
        req = ActionRequest(
            id="req-1", plugin_id="research", capability="web.read",
            declared_level="L0", intent="read a page", target={"url": "https://example.com"},
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "allow")

        result = self.executor.dry_run(req, decision)
        self.assertEqual(result.status, "simulated")

    def test_l3_action_requires_approval_with_full_context(self):
        req = ActionRequest(
            id="req-2", plugin_id="installer", capability="system.package_install",
            declared_level="L3", intent="install ripgrep", target={"package": "ripgrep"},
            diff_preview="+ripgrep 14.1.0", requested_expires_in_seconds=3600,
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "require_approval")
        self.assertEqual(decision.approval_id, "req-2")

        approval = self.conn.execute("SELECT status FROM approvals WHERE id = 'req-2'").fetchone()
        self.assertEqual(approval, ("pending",))

    def test_approved_request_is_then_allowed(self):
        req = ActionRequest(
            id="req-3", plugin_id="installer", capability="system.package_install",
            declared_level="L3", intent="install ripgrep", target={"package": "ripgrep"},
            diff_preview="+ripgrep 14.1.0", requested_expires_in_seconds=3600,
        )
        first = self.engine.evaluate(req)
        self.assertEqual(first.decision, "require_approval")

        # A human approves out-of-band via the existing event ledger.
        from contracts.models import Event
        from storage.sqlite_store import SqliteEventStore
        SqliteEventStore(self.conn).append(Event(
            id="evt-decide-req-3", schema_version=1, occurred_at="2026-09-17T12:00:00Z",
            type="approval.decided", source="human",
            payload={"approval_id": "req-3", "decision": "approved"},
        ))

        second = self.engine.evaluate(req)
        self.assertEqual(second.decision, "allow")

        result = self.executor.dry_run(req, second)
        self.assertEqual(result.status, "simulated")

    def test_re_evaluating_pending_request_does_not_duplicate_approval_event(self):
        req = ActionRequest(
            id="req-4", plugin_id="installer", capability="system.package_install",
            declared_level="L3", intent="install ripgrep", target={"package": "ripgrep"},
            diff_preview="+ripgrep 14.1.0", requested_expires_in_seconds=3600,
        )
        self.engine.evaluate(req)
        self.engine.evaluate(req)
        self.engine.evaluate(req)

        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'approval.requested'"
        ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
