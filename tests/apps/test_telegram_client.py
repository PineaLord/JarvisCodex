"""Tests apps/telegram/client.py's error handling against a mocked
urlopen -- no real network call."""

import unittest
import unittest.mock
import urllib.error

from apps.telegram.client import TelegramApiError, TelegramClient


class TestTelegramClientErrorHandling(unittest.TestCase):
    def setUp(self):
        self.client = TelegramClient(token="test-token")

    def test_url_error_is_wrapped(self):
        with unittest.mock.patch(
            "apps.telegram.client.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(TelegramApiError):
                self.client.get_updates(offset=None)

    def test_plain_timeout_is_wrapped_not_left_uncaught(self):
        # Reproduces a bug hit live: a long-poll running past the socket
        # read timeout raises a bare TimeoutError (an OSError subclass),
        # not a urllib.error.URLError, and previously propagated uncaught
        # out of get_updates(), killing the whole polling loop.
        with unittest.mock.patch(
            "apps.telegram.client.urllib.request.urlopen",
            side_effect=TimeoutError("The read operation timed out"),
        ):
            with self.assertRaises(TelegramApiError):
                self.client.get_updates(offset=None)


if __name__ == "__main__":
    unittest.main()
