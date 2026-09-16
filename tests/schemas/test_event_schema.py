import unittest

from contracts.schema_validation import SchemaValidationError, validate_event, validate_payload


def make_event(**overrides) -> dict:
    event = {
        "id": "evt-1",
        "schema_version": 1,
        "occurred_at": "2026-09-16T12:00:00Z",
        "type": "task.created",
        "source": "cli",
        "parent_id": None,
        "correlation_id": None,
        "payload": {"task_id": "task-1", "title": "Write restore test"},
    }
    event.update(overrides)
    return event


class TestEventSchema(unittest.TestCase):
    def test_valid_event_passes(self):
        validate_event(make_event())  # must not raise

    def test_missing_required_field_fails(self):
        event = make_event()
        del event["source"]
        with self.assertRaises(SchemaValidationError):
            validate_event(event)

    def test_wrong_schema_version_fails(self):
        with self.assertRaises(SchemaValidationError):
            validate_event(make_event(schema_version=2))

    def test_type_pattern_enforced(self):
        with self.assertRaises(SchemaValidationError):
            validate_event(make_event(type="NotLowercaseDotted"))

    def test_additional_properties_rejected(self):
        event = make_event()
        event["unexpected"] = "nope"
        with self.assertRaises(SchemaValidationError):
            validate_event(event)

    def test_known_payload_schema_enforced(self):
        with self.assertRaises(SchemaValidationError):
            validate_payload("task.created", {"title": "missing task_id"})

    def test_unknown_event_type_payload_is_unconstrained(self):
        validate_payload("plugin.custom_thing", {"anything": "goes"})  # must not raise


if __name__ == "__main__":
    unittest.main()
