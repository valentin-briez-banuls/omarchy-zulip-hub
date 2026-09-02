from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from .api import ZulipAPIError, ZulipClient
from .config import ConfigError, Paths, load_config
from .limits import MAX_CONTENT, bounded_text, encoded_response
from .secrets import SecretError, SecretToolProvider
from .state import recent_row


class ReaderError(RuntimeError):
    """Une demande de lecture de message était invalide."""


@dataclass
class ReaderManager:
    """Lit un message affiché dans la liste, sans jamais l’écrire sur disque.

    L’appelant ne fournit qu’un identifiant : la conversation est retrouvée dans
    l’état local, et l’en-tête présenté vient de cet état plutôt que de la
    réponse distante. Le corps est récupéré à la demande et reste en mémoire.
    """

    config_path: Path
    state_path: Path | None = None
    secrets: SecretToolProvider | None = None

    def __post_init__(self) -> None:
        if self.state_path is None:
            self.state_path = Paths.defaults().state
        if self.secrets is None:
            self.secrets = SecretToolProvider()

    def _client(self) -> ZulipClient:
        config = load_config(self.config_path)
        assert self.secrets is not None
        key = self.secrets.get(config.account.site, config.account.email)
        return ZulipClient(
            config.account.site,
            config.account.email,
            key,
            config.request_timeout_seconds,
        )

    def _local_state(self) -> dict[str, Any]:
        try:
            assert self.state_path is not None
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def read(self, request: dict[str, Any]) -> dict[str, Any]:
        message_id = request.get("message_id")
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise ReaderError("Le message demandé est invalide.")
        row = recent_row(self._local_state(), message_id)
        if row is None:
            raise ReaderError("Ce message n’est plus dans les conversations récentes.")
        content = self._client().message(message_id).get("content")
        if not isinstance(content, str):
            raise ReaderError("Le serveur n’a renvoyé aucun contenu.")
        return {
            "ok": True,
            "message": {
                "id": message_id,
                "content": bounded_text(content, MAX_CONTENT),
                "sender": str(row.get("sender") or ""),
                "type": row.get("type"),
                "channel": row.get("channel"),
                "topic": row.get("topic"),
                "timestamp": row.get("timestamp"),
            },
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("action") == "read":
            return self.read(request)
        raise ReaderError("Action de lecture inconnue.")


def serve_once(
    config_path: Path | None = None,
    state_path: Path | None = None,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    try:
        raw = input_stream.readline(65537)
        if not raw or len(raw) > 65536:
            raise ReaderError("Requête de lecture absente ou trop volumineuse.")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ReaderError("La requête de lecture doit être un objet JSON.")
        response = ReaderManager(
            config_path or Paths.defaults().config,
            state_path=state_path,
        ).handle(request)
    except (ReaderError, ZulipAPIError, SecretError, ConfigError, json.JSONDecodeError) as exc:
        response = {"ok": False, "error": str(exc)}
    output_stream.write(encoded_response(response))
    output_stream.flush()
    return 0
