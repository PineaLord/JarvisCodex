"""Stable policy/execution contracts. See docs/04-safety-model.md.

The model never classifies its own action -- an executor must get a
signed decision from a PolicyEngine first. These types are the boundary
between "a plugin wants to do something" and "the core decided what's
allowed", and must not change shape when the rule set or the executor
implementation changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

LEVEL_ORDER = ["L0", "L1", "L2", "L3", "L4", "L5"]


def level_index(level: str) -> int:
    return LEVEL_ORDER.index(level)


@dataclass(frozen=True)
class ActionRequest:
    """A plugin's request to do something. `declared_level` is the
    plugin's own claim and is never trusted alone -- see
    policy/capabilities.py for the authoritative floor per capability."""

    id: str
    plugin_id: str
    capability: str
    declared_level: str
    intent: str
    target: dict = field(default_factory=dict)
    source_trust: str = "trusted"  # "trusted" | "untrusted" -- see docs/04-safety-model.md
    diff_preview: str | None = None
    requested_expires_in_seconds: int | None = None


@dataclass(frozen=True)
class PolicyDecision:
    request_id: str
    decision: str  # "allow" | "require_approval" | "deny"
    effective_level: str
    reasons: list[str]
    approval_id: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    request_id: str
    status: str  # "simulated" | "blocked"
    detail: str


class PolicyEngine(Protocol):
    def evaluate(self, request: ActionRequest) -> PolicyDecision: ...


class Executor(Protocol):
    def dry_run(self, request: ActionRequest, decision: PolicyDecision) -> ExecutionResult: ...
