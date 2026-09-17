"""Adversarial cases for the policy engine.

Each test tries a specific way to trick the engine into allowing (or
under-scrutinizing) something it shouldn't, per the structural rules in
docs/04-safety-model.md.
"""

import tempfile
import unittest
from pathlib import Path

from contracts.models import Event
from contracts.policy import ActionRequest
from policy.engine import RuleBasedPolicyEngine
from storage.sqlite_store import SqliteEventStore, connect


class TestPolicyAdversarial(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.engine = RuleBasedPolicyEngine(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_unregistered_capability_is_denied(self):
        req = ActionRequest(
            id="adv-1", plugin_id="rogue", capability="system.shell_exec",
            declared_level="L0", intent="run a script", target={"command": "rm -rf /"},
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "deny")

    def test_plugin_cannot_self_declare_a_lower_level_than_the_registry(self):
        # telegram.send is registered at L4; a plugin claiming L0 must not
        # get away with skipping the approval that L4 requires.
        req = ActionRequest(
            id="adv-2", plugin_id="chatty", capability="telegram.send",
            declared_level="L0", intent="notify the owner",
            target={"recipient": "owner", "message": "hi"},
            diff_preview="send 'hi' to owner", requested_expires_in_seconds=600,
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.effective_level, "L4")
        self.assertEqual(decision.decision, "require_approval")

    def test_untrusted_sourced_intent_always_requires_approval_at_l2plus(self):
        req = ActionRequest(
            id="adv-3", plugin_id="researcher", capability="fs.write_jarvis_space",
            declared_level="L2", intent="save what the webpage told me to save",
            target={"path": "data/live/notes.md"}, source_trust="untrusted",
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "require_approval")
        self.assertIn("untrusted", " ".join(decision.reasons))

    def test_l3_request_missing_diff_preview_is_denied_not_downgraded(self):
        req = ActionRequest(
            id="adv-4", plugin_id="installer", capability="system.package_install",
            declared_level="L3", intent="install something", target={"package": "curl"},
            diff_preview=None, requested_expires_in_seconds=3600,
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "deny")

    def test_path_traversal_outside_jarvis_space_is_denied(self):
        req = ActionRequest(
            id="adv-5", plugin_id="researcher", capability="fs.write_jarvis_space",
            declared_level="L2", intent="write a file",
            target={"path": "data/live/../../etc/passwd"},
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "deny")

    def test_non_string_target_field_is_rejected(self):
        req = ActionRequest(
            id="adv-6", plugin_id="researcher", capability="fs.write_jarvis_space",
            declared_level="L2", intent="write a file",
            target={"path": {"$ne": None}},  # injection-style non-string value
        )
        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "deny")

    def test_l2_quota_exhaustion_falls_back_to_approval(self):
        engine = RuleBasedPolicyEngine(self.conn, daily_quota_by_capability={"fs.write_jarvis_space": 2})
        for i in range(2):
            req = ActionRequest(
                id=f"adv-quota-{i}", plugin_id="researcher", capability="fs.write_jarvis_space",
                declared_level="L2", intent="write a note", target={"path": "data/live/notes.md"},
            )
            decision = engine.evaluate(req)
            self.assertEqual(decision.decision, "allow")

        third = ActionRequest(
            id="adv-quota-3", plugin_id="researcher", capability="fs.write_jarvis_space",
            declared_level="L2", intent="write a note", target={"path": "data/live/notes.md"},
        )
        decision = engine.evaluate(third)
        self.assertEqual(decision.decision, "require_approval")

    def test_expired_pending_approval_is_denied_not_silently_valid(self):
        req = ActionRequest(
            id="adv-7", plugin_id="installer", capability="system.package_install",
            declared_level="L3", intent="install curl", target={"package": "curl"},
            diff_preview="+curl", requested_expires_in_seconds=1,
        )
        first = self.engine.evaluate(req)
        self.assertEqual(first.decision, "require_approval")

        # Backdate the approval's expiry directly (simulating time passing)
        # rather than sleeping in a test.
        self.conn.execute(
            "UPDATE approvals SET expires_at = '2000-01-01T00:00:00Z' WHERE id = ?", (req.id,)
        )
        self.conn.commit()

        second = self.engine.evaluate(req)
        self.assertEqual(second.decision, "deny")
        self.assertIn("expired", " ".join(second.reasons))

    def test_rejected_approval_stays_denied_on_replay(self):
        req = ActionRequest(
            id="adv-8", plugin_id="installer", capability="system.package_install",
            declared_level="L3", intent="install curl", target={"package": "curl"},
            diff_preview="+curl", requested_expires_in_seconds=3600,
        )
        self.engine.evaluate(req)

        SqliteEventStore(self.conn).append(Event(
            id="evt-reject-adv-8", schema_version=1, occurred_at="2026-09-17T12:00:00Z",
            type="approval.decided", source="human",
            payload={"approval_id": "adv-8", "decision": "rejected"},
        ))

        decision = self.engine.evaluate(req)
        self.assertEqual(decision.decision, "deny")
        self.assertIn("rejected", " ".join(decision.reasons))


if __name__ == "__main__":
    unittest.main()
