"""Faza C: intent -> signal -> candidate initiative -> goal.

Exercises the deterministic repeated-memory heuristic, the L2-only cap,
and -- the important part -- that the daily quota really is ledger-
persisted across fresh RuleBasedPolicyEngine instances, since a real
heartbeat is a separate process invocation each time."""

import tempfile
import unittest
from pathlib import Path

from contracts.models import Event
from core.initiative import detect_signals, propose_initiatives, run_consolidation, run_heartbeat
from policy.engine import RuleBasedPolicyEngine
from storage.sqlite_store import SqliteEventStore, connect


def seed_memory_candidate(store: SqliteEventStore, candidate_id: str, statement: str, event_id: str) -> Event:
    return store.append(Event(
        id=event_id, schema_version=1, occurred_at="2026-09-17T10:00:00Z",
        type="memory.candidate_proposed", source="test",
        payload={"candidate_id": candidate_id, "statement": statement, "confidence": 0.6, "source_event_ids": []},
    ))


class TestDetectSignals(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.store = SqliteEventStore(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_no_signal_below_repeat_threshold(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        self.assertEqual(detect_signals(self.conn), [])

    def test_signal_when_statement_repeated_case_insensitively(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "Prefer Local-First", "evt-2")

        signals = detect_signals(self.conn)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].payload["subject"], "prefer local-first")
        self.assertCountEqual(signals[0].payload["source_event_ids"], ["evt-1", "evt-2"])

    def test_cooldown_prevents_immediate_resignal(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "prefer local-first", "evt-2")
        self.assertEqual(len(detect_signals(self.conn)), 1)

        seed_memory_candidate(self.store, "mem-3", "prefer local-first", "evt-3")
        self.assertEqual(detect_signals(self.conn), [])  # same subject, still within cooldown


class TestProposeInitiatives(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.store = SqliteEventStore(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_initiative_is_capped_at_l2_and_carries_source_candidate(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "prefer local-first", "evt-2")
        signals = detect_signals(self.conn)

        initiatives = propose_initiatives(self.conn, signals)
        self.assertEqual(len(initiatives), 1)
        self.assertEqual(initiatives[0].payload["level"], "L2")
        self.assertEqual(initiatives[0].payload["target"]["candidate_id"], "mem-1")


class TestRunConsolidation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.store = SqliteEventStore(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_full_pipeline_auto_accepts_within_quota(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "prefer local-first", "evt-2")

        engine = RuleBasedPolicyEngine(self.conn, daily_quota_by_capability={"memory.consolidate": 5})
        summary = run_consolidation(self.conn, engine)

        self.assertIn("1 semnal", summary)
        self.assertIn("1 inițiativă", summary)

        goal = self.conn.execute("SELECT status FROM goals").fetchone()
        self.assertEqual(goal, ("active",))

        confirmed = self.conn.execute("SELECT status FROM memory_candidates WHERE id = 'mem-1'").fetchone()
        self.assertEqual(confirmed, ("confirmed",))

    def test_quota_exhaustion_falls_back_to_approval(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "prefer local-first", "evt-2")
        seed_memory_candidate(self.store, "mem-3", "loves docker compose", "evt-3")
        seed_memory_candidate(self.store, "mem-4", "loves docker compose", "evt-4")

        engine = RuleBasedPolicyEngine(self.conn, daily_quota_by_capability={"memory.consolidate": 1})
        summary = run_consolidation(self.conn, engine)

        self.assertIn("1 inițiativă", summary)
        self.assertIn("1 în așteptare", summary)

        pending = self.conn.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending'").fetchone()[0]
        self.assertEqual(pending, 1)

    def test_quota_persists_across_fresh_engine_instances(self):
        # Simulates separate heartbeat process invocations: a second,
        # brand-new engine must see the first one's usage via the ledger,
        # not start back at zero.
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "prefer local-first", "evt-2")
        seed_memory_candidate(self.store, "mem-3", "loves docker compose", "evt-3")
        seed_memory_candidate(self.store, "mem-4", "loves docker compose", "evt-4")

        engine_a = RuleBasedPolicyEngine(self.conn, daily_quota_by_capability={"memory.consolidate": 1})
        run_consolidation(self.conn, engine_a)

        engine_b = RuleBasedPolicyEngine(self.conn, daily_quota_by_capability={"memory.consolidate": 1})
        summary_b = run_consolidation(self.conn, engine_b)

        self.assertIn("0 inițiativă", summary_b)  # today's quota of 1 was already spent by engine_a


class TestRunHeartbeat(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "jarvis.db")
        self.store = SqliteEventStore(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_heartbeat_runs_one_pass(self):
        seed_memory_candidate(self.store, "mem-1", "prefer local-first", "evt-1")
        seed_memory_candidate(self.store, "mem-2", "prefer local-first", "evt-2")

        summary = run_heartbeat(self.conn, daily_quota=5)
        self.assertIn("Consolidare", summary)


if __name__ == "__main__":
    unittest.main()
