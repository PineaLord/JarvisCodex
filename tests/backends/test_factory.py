import unittest
import unittest.mock

from backends.echo import EchoBackend
from backends.factory import get_backend


class TestBackendFactory(unittest.TestCase):
    def test_defaults_to_echo(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsInstance(get_backend(), EchoBackend)

    def test_explicit_echo(self):
        with unittest.mock.patch.dict("os.environ", {"JARVIS_CODEX_BACKEND": "echo"}):
            self.assertIsInstance(get_backend(), EchoBackend)

    def test_claude_is_selected_and_constructed(self):
        with unittest.mock.patch.dict("os.environ", {
            "JARVIS_CODEX_BACKEND": "Claude", "ANTHROPIC_API_KEY": "sk-test",
        }):
            from backends.claude import ClaudeBackend
            self.assertIsInstance(get_backend(), ClaudeBackend)

    def test_unknown_backend_raises(self):
        with unittest.mock.patch.dict("os.environ", {"JARVIS_CODEX_BACKEND": "nope"}):
            with self.assertRaises(ValueError):
                get_backend()


if __name__ == "__main__":
    unittest.main()
