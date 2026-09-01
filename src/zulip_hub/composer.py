from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from .api import ZulipAPIError, ZulipClient
from .config import ConfigError, Paths, load_config
from .secrets import SecretError, SecretToolProvider


class ComposerError(RuntimeError):
    """A request from the graphical message composer was invalid."""


@dataclass
class ComposerManager:
    config_path: Path
    state_path: Path | None = None
    secrets: SecretToolProvider | None = None

    def __post_init__(self) -> None:
        if self.state_path is None:
            self.state_path = Paths.defaults().state
        if self.secrets is None:
            self.secrets = SecretToolProvider()

    def _client(self) -> tuple[ZulipClient, Any]:
        config = load_config(self.config_path)
        assert self.secrets is not None
        key = self.secrets.get(config.account.site, config.account.email)
        return ZulipClient(
            config.account.site,
            config.account.email,
            key,
            config.request_timeout_seconds,
        ), config

    def _local_state(self) -> dict[str, Any]:
        try:
            assert self.state_path is not None
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def directory(self) -> dict[str, Any]:
        client, config = self._client()
        identity = client.test_connection()
        self_id = identity.get("user_id")
        users = []
        for member in client.users():
            user_id = member.get("user_id")
            if (
                not isinstance(user_id, int)
                or user_id <= 0
                or user_id == self_id
                or member.get("is_active") is not True
                or member.get("is_bot") is True
                or member.get("is_deleted") is True
                or member.get("is_imported_stub") is True
            ):
                continue
            users.append({
                "id": user_id,
                "full_name": str(member.get("full_name") or member.get("email") or user_id),
                "email": str(member.get("email") or ""),
            })
        users.sort(key=lambda item: (item["full_name"].casefold(), item["id"]))

        state = self._local_state()
        recent_ids: list[int] = []
        for row in state.get("recent", []):
            if not isinstance(row, dict) or row.get("type") != "private":
                continue
            candidates = [row.get("sender_id"), *row.get("recipient_ids", [])]
            for value in candidates:
                if isinstance(value, int) and value > 0 and value != self_id and value not in recent_ids:
                    recent_ids.append(value)
        maximum = state.get("max_message_length", 10000)
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            maximum = 10000
        return {
            "ok": True,
            "users": users,
            "recent_user_ids": recent_ids,
            "max_message_length": maximum,
            "site": config.account.site,
        }

    @staticmethod
    def _recipient_ids(request: dict[str, Any]) -> list[int]:
        raw = request.get("recipient_ids")
        if not isinstance(raw, list):
            raise ComposerError("La liste des destinataires est invalide.")
        result: list[int] = []
        for value in raw:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ComposerError("Un destinataire est invalide.")
            if value not in result:
                result.append(value)
        if not result:
            raise ComposerError("Sélectionnez au moins un destinataire.")
        if len(result) > 100:
            raise ComposerError("Le groupe de destinataires est trop grand.")
        return result

    def send_direct(self, request: dict[str, Any]) -> dict[str, Any]:
        recipient_ids = self._recipient_ids(request)
        content = request.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ComposerError("Le message est vide.")
        state = self._local_state()
        maximum = state.get("max_message_length", 10000)
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            maximum = 10000
        if len(content) > maximum:
            raise ComposerError(f"Le message dépasse la limite de {maximum} caractères.")
        client, _config = self._client()
        return {"ok": True, "message_id": client.send_direct(recipient_ids, content)}

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "directory":
            return self.directory()
        if action == "send_direct":
            return self.send_direct(request)
        raise ComposerError("Action de composition inconnue.")


def serve_once(
    config_path: Path | None = None,
    state_path: Path | None = None,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    try:
        raw = input_stream.readline(65537)
        if not raw or len(raw) > 65536:
            raise ComposerError("Requête de composition absente ou trop volumineuse.")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ComposerError("La requête de composition doit être un objet JSON.")
        response = ComposerManager(
            config_path or Paths.defaults().config,
            state_path=state_path,
        ).handle(request)
    except (ComposerError, ZulipAPIError, SecretError, ConfigError, json.JSONDecodeError) as exc:
        response = {
            "ok": False,
            "error": str(exc),
            "delivery_uncertain": isinstance(exc, ZulipAPIError) and exc.code is None,
        }
    output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
    output_stream.flush()
    return 0
