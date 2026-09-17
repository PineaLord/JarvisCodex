"""Rule-based policy engine. See docs/04-safety-model.md and contracts/policy.py.

The model does not classify its own action, and a plugin's declared_level
is only ever trusted upward, never downward: policy/capabilities.py sets
the floor. Everything at L3+ requires an approval that lives in the same
event ledger as everything else, so it's auditable and recoverable rather
than a side channel.
"""

from __future__ import annotations

import posixpath
import sqlite3
from datetime import datetime, timedelta, timezone

from contracts.models import Event
from contracts.policy import ActionRequest, PolicyDecision, level_index
from policy.capabilities import CAPABILITIES
from storage.sqlite_store import SqliteEventStore

APPROVAL_REQUIRED_FROM = level_index("L3")
UNTRUSTED_SOURCE_ESCALATION_FROM = level_index("L2")
DEFAULT_APPROVAL_TTL_SECONDS = 3600


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path_within(path: str, prefixes: tuple[str, ...]) -> bool:
    normalized = posixpath.normpath(path)
    if normalized.startswith("..") or normalized.startswith("/"):
        return False
    return any(normalized == p.rstrip("/") or normalized.startswith(p) for p in prefixes)


class RuleBasedPolicyEngine:
    """Evaluates ActionRequests against the static capability registry.

    Per-capability daily quota usage is seeded from today's
    action.simulated events in the ledger, not a bare in-memory counter --
    a budget that resets whenever the process restarts (e.g. each
    heartbeat run, per docs/06-roadmap.md Faza C.3) isn't really a budget.
    A fresh engine instance and a long-lived one agree on how much of
    today's quota is left, because both read the same ledger.
    """

    def __init__(self, conn: sqlite3.Connection, daily_quota_by_capability: dict[str, int] | None = None):
        self._conn = conn
        self._event_store = SqliteEventStore(conn)
        self._quota = daily_quota_by_capability or {}
        self._usage: dict[str, int] = self._load_todays_usage()

    def _load_todays_usage(self) -> dict[str, int]:
        today = _iso_now()[:10]
        usage: dict[str, int] = {}
        for event in self._event_store.list_by_type("action.simulated"):
            if event.occurred_at[:10] == today:
                capability = event.payload.get("capability")
                usage[capability] = usage.get(capability, 0) + 1
        return usage

    def evaluate(self, request: ActionRequest) -> PolicyDecision:
        reasons: list[str] = []

        spec = CAPABILITIES.get(request.capability)
        if spec is None:
            return PolicyDecision(request.id, "deny", request.declared_level, ["unregistered capability"])

        effective_level = spec.min_level
        if level_index(request.declared_level) > level_index(effective_level):
            effective_level = request.declared_level
            reasons.append(f"declared level {request.declared_level} is stricter than registry minimum {spec.min_level}")

        missing = [f for f in spec.required_target_fields if f not in request.target]
        if missing:
            return PolicyDecision(request.id, "deny", effective_level, [f"missing required target fields: {missing}"])

        for f in spec.required_target_fields:
            if not isinstance(request.target[f], str):
                return PolicyDecision(request.id, "deny", effective_level, [f"target field {f!r} must be a string"])

        if spec.allowed_path_prefixes and "path" in request.target:
            if not _path_within(request.target["path"], spec.allowed_path_prefixes):
                return PolicyDecision(request.id, "deny", effective_level, ["target path outside allowed prefixes"])

        existing = self._existing_approval_decision(request.id)
        if existing is not None:
            return existing

        if request.source_trust == "untrusted" and level_index(effective_level) >= UNTRUSTED_SOURCE_ESCALATION_FROM:
            reasons.append("intent derived from untrusted data at L2+ always requires approval")
            return self._request_approval(request, effective_level, reasons)

        if level_index(effective_level) >= APPROVAL_REQUIRED_FROM:
            if not request.target or request.diff_preview is None or not request.requested_expires_in_seconds:
                return PolicyDecision(
                    request.id, "deny", effective_level,
                    ["L3+ action requires target, diff_preview and requested_expires_in_seconds"],
                )
            return self._request_approval(request, effective_level, reasons)

        if effective_level == "L2":
            quota = self._quota.get(request.capability)
            if quota is not None:
                used = self._usage.get(request.capability, 0)
                if used >= quota:
                    reasons.append("daily quota exhausted")
                    return self._request_approval(request, effective_level, reasons)
                self._usage[request.capability] = used + 1

        return PolicyDecision(request.id, "allow", effective_level, reasons)

    def _existing_approval_decision(self, approval_id: str) -> PolicyDecision | None:
        row = self._conn.execute(
            "SELECT status, level, expires_at FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            return None

        status, level, expires_at = row
        if status == "approved":
            return PolicyDecision(approval_id, "allow", level, ["previously approved"], approval_id=approval_id)
        if status == "rejected":
            return PolicyDecision(approval_id, "deny", level, ["previously rejected"], approval_id=approval_id)

        # status == "pending"
        if expires_at is not None and _iso_now() > expires_at:
            return PolicyDecision(approval_id, "deny", level, ["approval request expired without a decision"], approval_id=approval_id)
        return PolicyDecision(approval_id, "require_approval", level, ["awaiting decision"], approval_id=approval_id)

    def _request_approval(self, request: ActionRequest, effective_level: str, reasons: list[str]) -> PolicyDecision:
        ttl = request.requested_expires_in_seconds or DEFAULT_APPROVAL_TTL_SECONDS
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._event_store.append(Event(
            id=f"approval-req-{request.id}",
            schema_version=1,
            occurred_at=_iso_now(),
            type="approval.requested",
            source=request.plugin_id,
            payload={
                "approval_id": request.id,
                "level": effective_level,
                "description": request.intent,
                "expires_at": expires_at,
            },
        ))
        return PolicyDecision(request.id, "require_approval", effective_level, reasons, approval_id=request.id)
