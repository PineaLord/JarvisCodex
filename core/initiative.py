"""Faza C: intent -> signal -> candidate initiative -> goal.

Deterministic, explainable heuristics only (no ML). This is the first
place the system acts somewhat on its own, so every candidate initiative
is routed through the same RuleBasedPolicyEngine as any other action
(contracts/policy.py) -- there is no separate, softer approval path for
"the system's own idea" than for a plugin's. An initiative only ever
reaches L2; it is never allowed to propose L3+ on its own.

Everything here stays event-sourced: the "pending approval" state of an
initiative is never written directly, only re-derived each pass by
re-evaluating still-'proposed' initiatives against the policy engine
(which is itself idempotent -- see policy/engine.py).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from contracts.models import Event
from contracts.policy import ActionRequest
from policy.engine import RuleBasedPolicyEngine
from policy.executor import DryRunExecutor
from storage.sqlite_store import SqliteEventStore

REPEAT_THRESHOLD = 2  # a statement proposed this many times becomes a signal
SIGNAL_COOLDOWN_HOURS = 24


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _recent_signal_subjects(store: SqliteEventStore) -> set[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=SIGNAL_COOLDOWN_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        event.payload["subject"] for event in store.list_by_type("signal.detected")
        if event.occurred_at >= cutoff
    }


def detect_signals(conn: sqlite3.Connection) -> list[Event]:
    """Look for memory candidates repeated across separate proposals --
    a statement said more than once is durable enough to be worth
    consolidating. Subjects already signaled within the cooldown window
    are skipped, so the same repeated statement doesn't re-signal every
    single consolidation pass."""

    store = SqliteEventStore(conn)
    by_statement: dict[str, list[Event]] = {}
    for event in store.list_by_type("memory.candidate_proposed"):
        key = event.payload["statement"].strip().lower()
        by_statement.setdefault(key, []).append(event)

    already_recent = _recent_signal_subjects(store)
    new_signals = []

    for key, events in by_statement.items():
        if len(events) < REPEAT_THRESHOLD or key in already_recent:
            continue

        new_signals.append(store.append(Event(
            id=_new_id("signal"), schema_version=1, occurred_at=_iso_now(),
            type="signal.detected", source="consolidation",
            payload={
                "signal_id": _new_id("sig"),
                "kind": "repeated_memory",
                "subject": key,
                "description": f"Afirmația \"{events[0].payload['statement']}\" a fost propusă de {len(events)} ori.",
                "source_event_ids": [e.id for e in events],
            },
        )))

    return new_signals


def propose_initiatives(conn: sqlite3.Connection, signals: list[Event]) -> list[Event]:
    """Turn freshly detected signals into candidate initiatives, capped
    at L2 (write in Jarvis's own memory space) -- never higher here."""

    store = SqliteEventStore(conn)
    proposed = []

    for signal in signals:
        first_source = store.get(signal.payload["source_event_ids"][0])
        candidate_id = first_source.payload["candidate_id"] if first_source else ""

        proposed.append(store.append(Event(
            id=_new_id("initiative"), schema_version=1, occurred_at=_iso_now(),
            type="initiative.proposed", source="consolidation",
            payload={
                "initiative_id": _new_id("init"),
                "signal_id": signal.payload["signal_id"],
                "level": "L2",
                "description": f"Consolidează memoria: {signal.payload['description']}",
                "target": {"candidate_id": candidate_id},
            },
        )))

    return proposed


def _find_initiative_proposal(store: SqliteEventStore, initiative_id: str) -> Event | None:
    for event in store.list_by_type("initiative.proposed"):
        if event.payload["initiative_id"] == initiative_id:
            return event
    return None


def _accept_initiative(store: SqliteEventStore, initiative_id: str, description: str, target: dict) -> None:
    store.append(Event(
        id=_new_id("initiative-decided"), schema_version=1, occurred_at=_iso_now(),
        type="initiative.decided", source="consolidation",
        payload={"initiative_id": initiative_id, "decision": "accepted"},
    ))
    store.append(Event(
        id=_new_id("goal"), schema_version=1, occurred_at=_iso_now(),
        type="goal.created", source="consolidation",
        payload={"goal_id": _new_id("goal"), "initiative_id": initiative_id, "description": description},
    ))
    if target.get("candidate_id"):
        store.append(Event(
            id=_new_id("memory-confirmed"), schema_version=1, occurred_at=_iso_now(),
            type="memory.candidate_confirmed", source="consolidation",
            payload={"candidate_id": target["candidate_id"]},
        ))


def run_consolidation(conn: sqlite3.Connection, policy_engine: RuleBasedPolicyEngine) -> str:
    """One pass: detect signals, propose initiatives, and resolve every
    still-'proposed' initiative against the policy engine. Returns one
    aggregated summary line -- never one message per event, so a future
    notification channel can send a single digest instead of spamming."""

    store = SqliteEventStore(conn)
    executor = DryRunExecutor(conn)

    signals = detect_signals(conn)
    propose_initiatives(conn, signals)

    accepted = pending_approval = denied = 0

    pending_rows = conn.execute(
        "SELECT id, level, description FROM initiatives WHERE status = 'proposed'"
    ).fetchall()

    for initiative_id, level, description in pending_rows:
        proposal_event = _find_initiative_proposal(store, initiative_id)
        target = proposal_event.payload["target"] if proposal_event else {}

        request = ActionRequest(
            id=initiative_id, plugin_id="consolidation", capability="memory.consolidate",
            declared_level=level, intent=description, target=target,
        )
        decision = policy_engine.evaluate(request)

        if decision.decision == "allow":
            executor.dry_run(request, decision)  # records action.simulated for ledger-derived quota accounting
            _accept_initiative(store, initiative_id, description, target)
            accepted += 1
        elif decision.decision == "require_approval":
            pending_approval += 1  # visible via `jarvis approvals list`, not a separate status write
        else:
            store.append(Event(
                id=_new_id("initiative-decided"), schema_version=1, occurred_at=_iso_now(),
                type="initiative.decided", source="consolidation",
                payload={"initiative_id": initiative_id, "decision": "dismissed", "reason": "; ".join(decision.reasons)},
            ))
            denied += 1

    return (
        f"Consolidare: {len(signals)} semnal(e) noi, {accepted} inițiativă/e acceptată/e, "
        f"{pending_approval} în așteptare de aprobare, {denied} respinsă/e."
    )


def run_heartbeat(conn: sqlite3.Connection, daily_quota: int = 3) -> str:
    """Bounded, budgeted autonomy per docs/01-architecture.md: capped at
    L2 (enforced in propose_initiatives), a daily quota derived from the
    ledger itself (RuleBasedPolicyEngine seeds usage from today's
    action.simulated events, so the budget survives process restarts --
    unlike a plain in-memory counter), and per-subject cooldown in
    detect_signals. Returns one digest string; sending it anywhere is
    left to the caller (e.g. a channel adapter), never done here."""

    engine = RuleBasedPolicyEngine(conn, daily_quota_by_capability={"memory.consolidate": daily_quota})
    return run_consolidation(conn, engine)
