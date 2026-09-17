"""Tests backends/codex_cli.py against a mocked subprocess.run -- no real
`codex` invocation, since that depends on a live ChatGPT/Codex session
this sandbox doesn't have. Covers prompt construction, reply/marker
parsing, and error handling (non-zero exit, timeout)."""

import subprocess
import unittest
import unittest.mock

from backends.codex_cli import CodexCliBackend, CodexCliBackendError
from contracts.reasoning import ContextItem, ReasoningRequest


def make_backend() -> CodexCliBackend:
    with unittest.mock.patch("backends.codex_cli.shutil.which", return_value="/usr/bin/codex"):
        return CodexCliBackend()


class TestConstruction(unittest.TestCase):
    def test_missing_binary_raises(self):
        with unittest.mock.patch("backends.codex_cli.shutil.which", return_value=None):
            with self.assertRaises(CodexCliBackendError):
                CodexCliBackend()


class TestBuildPrompt(unittest.TestCase):
    def setUp(self):
        self.backend = make_backend()

    def test_no_context(self):
        req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
        prompt = self.backend._build_prompt(req)
        self.assertIn("Mesaj nou: salut", prompt)
        self.assertNotIn("Context relevant", prompt)

    def test_with_context(self):
        req = ReasoningRequest(
            session_id="s", input_text="ce ziceam?", input_event_id="e1",
            context=[ContextItem(text="prefer local-first", source_event_id="e0")],
        )
        prompt = self.backend._build_prompt(req)
        self.assertIn("- prefer local-first", prompt)
        self.assertIn("Mesaj nou: ce ziceam?", prompt)


class TestParseReply(unittest.TestCase):
    def setUp(self):
        self.backend = make_backend()

    def test_plain_reply_no_marker(self):
        response = self.backend._parse_reply("Salut! Cum te pot ajuta?")
        self.assertEqual(response.text, "Salut! Cum te pot ajuta?")
        self.assertEqual(response.proposed_memories, [])

    def test_reply_with_memory_marker_is_stripped_and_parsed(self):
        raw = "Am notat ideea ta.\nMEMORY: Preferă instrumente local-first | confidence=0.75"
        response = self.backend._parse_reply(raw)
        self.assertEqual(response.text, "Am notat ideea ta.")
        self.assertEqual(len(response.proposed_memories), 1)
        self.assertEqual(response.proposed_memories[0].statement, "Preferă instrumente local-first")
        self.assertEqual(response.proposed_memories[0].confidence, 0.75)


class TestRespond(unittest.TestCase):
    def setUp(self):
        self.backend = make_backend()

    def test_successful_run_reads_output_file(self):
        def fake_run(cmd, **kwargs):
            out_path = cmd[cmd.index("-o") + 1]
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("raspuns de test")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with unittest.mock.patch("backends.codex_cli.subprocess.run", side_effect=fake_run):
            req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
            response = self.backend.respond(req)
        self.assertEqual(response.text, "raspuns de test")

    def test_nonzero_exit_raises_with_stderr(self):
        result = subprocess.CompletedProcess([], returncode=1, stdout="", stderr="usage limit reached")
        with unittest.mock.patch("backends.codex_cli.subprocess.run", return_value=result):
            req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
            with self.assertRaises(CodexCliBackendError) as ctx:
                self.backend.respond(req)
        self.assertIn("usage limit reached", str(ctx.exception))

    def test_timeout_is_wrapped(self):
        with unittest.mock.patch(
            "backends.codex_cli.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=120),
        ):
            req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
            with self.assertRaises(CodexCliBackendError):
                self.backend.respond(req)

    def test_runs_with_stdin_closed_and_readonly_sandbox(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["stdin"] = kwargs.get("stdin")
            out_path = cmd[cmd.index("-o") + 1]
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("ok")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with unittest.mock.patch("backends.codex_cli.subprocess.run", side_effect=fake_run):
            req = ReasoningRequest(session_id="s", input_text="salut", input_event_id="e1")
            self.backend.respond(req)

        self.assertEqual(captured["stdin"], subprocess.DEVNULL)
        self.assertIn("--sandbox", captured["cmd"])
        self.assertIn("read-only", captured["cmd"])
        self.assertIn("--skip-git-repo-check", captured["cmd"])


if __name__ == "__main__":
    unittest.main()
