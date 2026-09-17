"""Tests backends/claude.py against a faked urlopen -- no real network
call and no real API key, since neither exists in CI or dev sandboxes.
Covers the parts that matter: request construction, response parsing
(text + the propose_memory tool call), and error wrapping."""

import io
import json
import unittest
import unittest.mock
import urllib.error

from backends.claude import ClaudeBackend, ClaudeBackendError
from contracts.reasoning import ContextItem, ReasoningRequest


def fake_response(body: dict):
    class FakeResponse:
        def read(self):
            return json.dumps(body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return FakeResponse()


class TestClaudeBackendConstruction(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ClaudeBackendError):
                ClaudeBackend()

    def test_explicit_api_key_is_accepted_without_env(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            backend = ClaudeBackend(api_key="sk-test")
            self.assertEqual(backend._api_key, "sk-test")


class TestBuildUserContent(unittest.TestCase):
    def setUp(self):
        self.backend = ClaudeBackend(api_key="sk-test")

    def test_no_context_returns_input_verbatim(self):
        req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
        self.assertEqual(self.backend._build_user_content(req), "salut")

    def test_context_is_prefixed_as_bullets(self):
        req = ReasoningRequest(
            session_id="s", input_text="ce ziceam?", input_event_id="e1",
            context=[ContextItem(text="prefer local-first", source_event_id="e0")],
        )
        content = self.backend._build_user_content(req)
        self.assertIn("- prefer local-first", content)
        self.assertIn("ce ziceam?", content)


class TestParseResponse(unittest.TestCase):
    def setUp(self):
        self.backend = ClaudeBackend(api_key="sk-test")

    def test_extracts_text_blocks(self):
        result = {"content": [{"type": "text", "text": "salut!"}]}
        response = self.backend._parse_response(result)
        self.assertEqual(response.text, "salut!")
        self.assertEqual(response.proposed_memories, [])

    def test_extracts_propose_memory_tool_call(self):
        result = {"content": [
            {"type": "text", "text": "Am notat."},
            {"type": "tool_use", "name": "propose_memory", "input": {
                "statement": "Preferă instrumente local-first", "confidence": 0.8,
            }},
        ]}
        response = self.backend._parse_response(result)
        self.assertEqual(response.text, "Am notat.")
        self.assertEqual(len(response.proposed_memories), 1)
        self.assertEqual(response.proposed_memories[0].statement, "Preferă instrumente local-first")
        self.assertEqual(response.proposed_memories[0].confidence, 0.8)

    def test_ignores_unrelated_tool_calls(self):
        result = {"content": [{"type": "tool_use", "name": "some_other_tool", "input": {}}]}
        response = self.backend._parse_response(result)
        self.assertEqual(response.proposed_memories, [])


class TestRespond(unittest.TestCase):
    def setUp(self):
        self.backend = ClaudeBackend(api_key="sk-test")

    def test_respond_returns_parsed_response(self):
        api_result = {"content": [{"type": "text", "text": "raspuns"}]}
        with unittest.mock.patch("backends.claude.urllib.request.urlopen", return_value=fake_response(api_result)):
            req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
            response = self.backend.respond(req)
        self.assertEqual(response.text, "raspuns")

    def test_http_error_is_wrapped_without_leaking_the_api_key(self):
        http_error = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages", code=401,
            msg="unauthorized", hdrs=None, fp=io.BytesIO(b'{"error": "bad key"}'),
        )
        with unittest.mock.patch("backends.claude.urllib.request.urlopen", side_effect=http_error):
            req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
            with self.assertRaises(ClaudeBackendError) as ctx:
                self.backend.respond(req)
        self.assertNotIn("sk-test", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
