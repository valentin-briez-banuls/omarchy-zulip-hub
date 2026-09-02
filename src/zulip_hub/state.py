from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import tempfile

from .limits import (
    MAX_MESSAGE_LENGTH,
    MAX_PAYLOAD_BYTES,
    bounded_list,
    bounded_text,
    clamped_number,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recent_row(state: dict[str, Any], message_id: int) -> dict[str, Any] | None:
    """Retrouve une conversation récente par identifiant de message."""
    for row in state.get("recent", []):
        if isinstance(row, dict) and row.get("id") == message_id:
            return row
    return None


@dataclass
class HubState:
    schema_version: int = 1
    connected: bool = False
    last_sync: str | None = None
    unread: dict[str, int] = field(default_factory=lambda: {"total": 0, "mentions": 0, "private": 0})
    recent: list[dict[str, Any]] = field(default_factory=list)
    server_url: str = ""
    error: str | None = None
    max_message_length: int = 10000


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _within_budget(state: HubState) -> str:
        """Sérialisation de l’état, ramenée sous le budget d’écriture.

        Les bornes par champ ne s’additionnent pas : c’est ici que la taille
        totale est tenue, en abandonnant les conversations les plus anciennes.
        """
        payload = asdict(state)
        recent = list(payload.get("recent", []))
        while True:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            if len(data.encode("utf-8")) <= MAX_PAYLOAD_BYTES or not recent:
                return data
            recent = recent[: max(1, len(recent) // 2)] if len(recent) > 1 else []
            payload["recent"] = recent

    def write(self, state: HubState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = self._within_budget(state)
        fd, temporary = tempfile.mkstemp(prefix=".state-", dir=self.path.parent, text=True)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))


class StateReducer:
    def __init__(self, limit: int = 30):
        self.state = HubState()
        self.limit = limit
        self._unread_ids: set[int] = set()
        self._mention_ids: set[int] = set()
        self._private_ids: set[int] = set()

    def initialized(self, registration: dict[str, Any]) -> None:
        unread = registration.get("unread_msgs", {})
        if not isinstance(unread, dict):
            unread = {}
        mention_ids = set(bounded_list(unread.get("mentions", [])))
        private_ids = set(bounded_list(unread.get("pms", [])))
        stream_ids: set[int] = set()
        for entry in bounded_list(unread.get("streams", [])):
            if isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], list):
                stream_ids.update(bounded_list(entry[1]))
        self._mention_ids = mention_ids
        self._private_ids = private_ids
        self._unread_ids = mention_ids | private_ids | stream_ids
        self._sync_counts()
        self.state.connected = True
        self.state.error = None
        self.state.last_sync = utc_now()
        self.state.max_message_length = int(clamped_number(
            registration.get("max_message_length", 10000),
            default=10000, minimum=1, maximum=MAX_MESSAGE_LENGTH,
        ))

    def apply(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "message":
            message = event.get("message", {})
            flags = set(message.get("flags", []))
            if "read" not in flags:
                message_id = message.get("id")
                if not isinstance(message_id, int):
                    return
                self._unread_ids.add(message_id)
                if message.get("type") == "private":
                    self._private_ids.add(message_id)
                if flags & {
                    "mentioned", "wildcard_mentioned",
                    "stream_wildcard_mentioned", "topic_wildcard_mentioned",
                }:
                    self._mention_ids.add(message_id)
                self._sync_counts()
                self.state.recent.insert(0, self._summary(message))
                del self.state.recent[self.limit :]
        elif event_type == "update_message_flags":
            flag = event.get("flag")
            operation = event.get("op", event.get("operation"))
            if flag == "read" and operation == "add":
                if event.get("all") is True:
                    self._unread_ids.clear()
                    self._mention_ids.clear()
                    self._private_ids.clear()
                else:
                    message_ids = set(event.get("messages", []))
                    self._unread_ids.difference_update(message_ids)
                    self._mention_ids.difference_update(message_ids)
                    self._private_ids.difference_update(message_ids)
                self._sync_counts()
        self.state.connected = True
        self.state.error = None
        self.state.last_sync = utc_now()

    def _sync_counts(self) -> None:
        self.state.unread = {
            "total": len(self._unread_ids),
            "mentions": len(self._mention_ids),
            "private": len(self._private_ids),
        }

    @staticmethod
    def _summary(message: dict[str, Any]) -> dict[str, Any]:
        """Résumé borné d’un message, sans son corps.

        Tout ce qui vient du serveur est tronqué avant d’entrer dans l’état :
        ce fichier est relu tel quel par l’interface.
        """
        is_stream = message.get("type") == "stream"
        recipients = bounded_list(message.get("display_recipient", []))
        return {
            "id": message.get("id"),
            "type": message.get("type"),
            "sender": bounded_text(message.get("sender_full_name", "")),
            "sender_id": message.get("sender_id"),
            "channel": bounded_text(message.get("display_recipient")) if is_stream else None,
            "topic": bounded_text(message.get("subject")) if is_stream else None,
            "stream_id": message.get("stream_id") if is_stream else None,
            "recipient_ids": [
                recipient.get("id") for recipient in recipients
                if isinstance(recipient, dict) and isinstance(recipient.get("id"), int)
            ] if message.get("type") == "private" else [],
            "timestamp": message.get("timestamp"),
            "flags": [bounded_text(flag, 64) for flag in bounded_list(message.get("flags", []))],
        }
