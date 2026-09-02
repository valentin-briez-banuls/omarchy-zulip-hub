from __future__ import annotations

import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ZulipAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = True,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        # Delai reclame par le serveur, en secondes. Le respecter evite de
        # consommer le quota du compte, partage avec le client Zulip.
        self.retry_after = retry_after


def _retry_after(body: object) -> float | None:
    if not isinstance(body, dict):
        return None
    value = body.get("retry-after")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


class ZulipClient:
    def __init__(self, site: str, email: str, api_key: str, timeout: int = 90):
        self.site = site.rstrip("/")
        token = base64.b64encode(f"{email}:{api_key}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "User-Agent": "omarchy-zulip-hub/2.0"}
        self.timeout = timeout

    def _request(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        encoded = urlencode({
            key: json.dumps(value) if isinstance(value, (list, dict, bool)) else value
            for key, value in params.items()
        })
        url = f"{self.site}/api/v1/{path}"
        data = None
        if method == "GET":
            url = f"{url}?{encoded}"
        else:
            data = encoded.encode()
        request = Request(url, data=data, headers=self.headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            code = None
            delay = None
            message = f"erreur HTTP Zulip {exc.code}"
            try:
                body = json.loads(exc.read().decode())
                code = body.get("code")
                message = body.get("msg", message)
                delay = _retry_after(body)
            except (ValueError, UnicodeDecodeError):
                pass
            raise ZulipAPIError(
                message,
                code=code,
                retryable=exc.code >= 500 or exc.code == 429,
                retry_after=delay,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ZulipAPIError("serveur Zulip inaccessible", retryable=True) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise ZulipAPIError("réponse Zulip invalide", retryable=True) from exc
        if payload.get("result") == "error":
            raise ZulipAPIError(
                payload.get("msg", "erreur API Zulip"),
                code=payload.get("code"),
                retry_after=_retry_after(payload),
            )
        return payload

    def register(self) -> dict[str, Any]:
        return self._request(
            "POST", "register",
            {
                "event_types": ["message", "update_message_flags", "user_topic"],
                "fetch_event_types": ["message", "user_topic"],
                "apply_markdown": False,
            },
        )

    def test_connection(self) -> dict[str, Any]:
        return self._request("GET", "users/me", {})

    def events(self, queue_id: str, last_event_id: int) -> list[dict[str, Any]]:
        payload = self._request(
            "GET", "events", {"queue_id": queue_id, "last_event_id": last_event_id},
        )
        return list(payload.get("events", []))

    def mark_read(self, message_ids: list[int]) -> None:
        if not message_ids:
            return
        self._request(
            "POST", "messages/flags",
            {"messages": message_ids, "op": "add", "flag": "read"},
        )

    def users(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "users", {"client_gravatar": True})
        members = payload.get("members", [])
        return [member for member in members if isinstance(member, dict)]

    @staticmethod
    def _sent_message_id(payload: dict[str, Any]) -> int:
        message_id = payload.get("id")
        if not isinstance(message_id, int) or message_id <= 0:
            raise ZulipAPIError("réponse d’envoi Zulip invalide", retryable=False)
        return message_id

    def send_direct(self, recipient_ids: list[int], content: str) -> int:
        params: dict[str, Any] = {"type": "direct", "to": recipient_ids, "content": content}
        try:
            payload = self._request("POST", "messages", params)
        except ZulipAPIError as exc:
            detail = str(exc).casefold()
            legacy_type_rejected = exc.code == "BAD_REQUEST" and (
                "direct" in detail or "message type" in detail or "invalid type" in detail
            )
            if not legacy_type_rejected:
                raise
            params["type"] = "private"
            payload = self._request("POST", "messages", params)
        return self._sent_message_id(payload)

    def send_stream(self, stream_id: int, topic: str, content: str) -> int:
        params: dict[str, Any] = {
            "type": "stream", "to": stream_id, "topic": topic, "content": content,
        }
        try:
            payload = self._request("POST", "messages", params)
        except ZulipAPIError as exc:
            detail = str(exc).casefold()
            # Zulip nommait ce champ « subject » avant la 2.0. Un rejet portant sur
            # le canal ou le contenu ne doit pas déclencher ce repli.
            legacy_topic_rejected = exc.code == "BAD_REQUEST" and (
                "topic" in detail or "subject" in detail
            )
            if not legacy_topic_rejected:
                raise
            del params["topic"]
            params["subject"] = topic
            payload = self._request("POST", "messages", params)
        return self._sent_message_id(payload)
