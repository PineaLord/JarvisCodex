"""Dry-run executor. See docs/06-roadmap.md Faza A.4.

Never performs a real side effect -- it only ever logs what an allowed
action would have done. This is deliberately the only executor that
exists before Faza C: plugins get to prove their requests pass policy
long before anything is trusted with real execution.
"""

from __future__ import annotations

from datetime import datetime, timezone

from contracts.models import Event
from contracts.policy import ActionRequest, ExecutionResult, PolicyDecision
from storage.sqlite_store import SqliteEventStore


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DryRunExecutor:
    def __init__(self, conn):
        self._event_store = SqliteEventStore(conn)

    def dry_run(self, request: ActionRequest, decision: PolicyDecision) -> ExecutionResult:
        if decision.decision == "deny":
            return ExecutionResult(request.id, "blocked", "denied by policy: " + "; ".join(decision.reasons))

        if decision.decision == "require_approval":
            return ExecutionResult(request.id, "blocked", f"awaiting approval {decision.approval_id}")

        preview = f"[dry-run] would execute {request.capability} with target={request.target}"
        self._event_store.append(Event(
            id=f"sim-{request.id}",
            schema_version=1,
            occurred_at=_iso_now(),
            type="action.simulated",
            source=request.plugin_id,
            payload={"capability": request.capability, "target": request.target, "preview": preview},
        ))
        return ExecutionResult(request.id, "simulated", preview)
