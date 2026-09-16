"""Minimal JSON Schema validation, stdlib-only.

No `jsonschema` package is assumed to be installed, and the durable core
should not require one just to boot: pulling in fewer dependencies keeps
the "recoverable brain" promise (docs/05-recovery.md) cheap to satisfy on a
clean machine. This implements only the subset of JSON Schema draft 2020-12
that schemas/*.json actually uses: type, const, enum, pattern,
required, properties, additionalProperties, items.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


class SchemaValidationError(ValueError):
    pass


@lru_cache(maxsize=None)
def load_schema(filename: str) -> dict:
    path = SCHEMAS_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _check_type(value, type_spec, path: str) -> None:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    for t in types:
        py_type = _TYPE_MAP[t]
        if t == "integer" and isinstance(value, bool):
            continue
        if isinstance(value, py_type):
            return
    raise SchemaValidationError(f"{path}: expected type {types}, got {type(value).__name__}")


def validate(instance, schema: dict, path: str = "$") -> None:
    """Raise SchemaValidationError on the first violation found."""

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(f"{path}: expected const {schema['const']!r}, got {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{path}: {instance!r} not in enum {schema['enum']}")

    if "type" in schema:
        _check_type(instance, schema["type"], path)

    if isinstance(instance, str) and "pattern" in schema:
        if not re.match(schema["pattern"], instance):
            raise SchemaValidationError(f"{path}: {instance!r} does not match pattern {schema['pattern']!r}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                raise SchemaValidationError(f"{path}: missing required property {key!r}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(properties)
            if extra:
                raise SchemaValidationError(f"{path}: unexpected properties {sorted(extra)}")

        for key, sub_schema in properties.items():
            if key in instance:
                validate(instance[key], sub_schema, f"{path}.{key}")

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            validate(item, schema["items"], f"{path}[{i}]")


def validate_event(event_dict: dict) -> None:
    validate(event_dict, load_schema("event.v1.json"))


_PAYLOAD_SCHEMA_BY_TYPE = {
    "task.created": "task_created.v1.json",
    "approval.requested": "approval_requested.v1.json",
    "approval.decided": "approval_decided.v1.json",
    "memory.candidate_proposed": "memory_candidate_proposed.v1.json",
}


def validate_payload(event_type: str, payload: dict) -> None:
    """Validate an event's payload against its type-specific schema, if one
    is registered. Unknown event types are accepted with no payload
    constraints -- the ledger must be able to store events for plugins and
    types that don't exist yet without a core code change."""

    schema_file = _PAYLOAD_SCHEMA_BY_TYPE.get(event_type)
    if schema_file is None:
        return
    validate(payload, load_schema(schema_file), path="$.payload")
