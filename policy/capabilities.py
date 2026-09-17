"""The capability registry: the authoritative source of risk levels.

Per docs/04-safety-model.md, a plugin declares capabilities but does not
get to set its own risk level -- this registry does. A capability that
isn't listed here doesn't exist as far as the policy engine is concerned
and is denied by default (least privilege). Notably, there is no entry
for a raw shell-command capability: "Matching-ul pe stringuri de shell
este insuficient pentru producție" is enforced structurally, by simply
never registering one -- only typed, field-checked capabilities exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    min_level: str
    required_target_fields: tuple[str, ...] = ()
    allowed_path_prefixes: tuple[str, ...] = ()


CAPABILITIES: dict[str, CapabilitySpec] = {
    "web.read": CapabilitySpec(
        min_level="L0",
        required_target_fields=("url",),
    ),
    "research.report": CapabilitySpec(
        min_level="L1",
    ),
    "fs.write_jarvis_space": CapabilitySpec(
        min_level="L2",
        required_target_fields=("path",),
        allowed_path_prefixes=("data/live/",),
    ),
    "system.package_install": CapabilitySpec(
        min_level="L3",
        required_target_fields=("package",),
    ),
    "telegram.send": CapabilitySpec(
        min_level="L4",
        required_target_fields=("recipient", "message"),
    ),
    "credentials.rotate": CapabilitySpec(
        min_level="L5",
        required_target_fields=("system",),
    ),
    "memory.consolidate": CapabilitySpec(
        min_level="L2",
        required_target_fields=("candidate_id",),
    ),
}
