"""Minimal Telegram Bot API client, stdlib-only (urllib).

Deliberately long-polling (getUpdates), not a webhook: no public port or
TLS certificate needed on a personal machine, consistent with the
project's local-first stance. Error messages never include the bot
token or the request URL, since the token must never end up in a log or
the ledger -- only ever in this process's outgoing HTTP calls.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.telegram.org"


class TelegramApiError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: int = 35):
        self._token = token
        self._timeout = timeout

    def _call(self, method: str, params: dict) -> dict:
        url = f"{API_BASE}/bot{self._token}/{method}"
        data = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise TelegramApiError(f"Telegram API call to {method} failed: {e}") from e

        if not body.get("ok"):
            raise TelegramApiError(f"Telegram API returned an error from {method}: {body.get('description')}")
        return body["result"]

    def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict]:
        params: dict = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", params)

    def send_message(self, chat_id: int | str, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})
