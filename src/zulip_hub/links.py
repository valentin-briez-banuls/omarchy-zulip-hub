from __future__ import annotations

from typing import Any
from urllib.parse import quote


class LinkError(ValueError):
    """A message does not contain enough safe metadata to build a link."""


_HASH_REPLACEMENTS = {"%": ".", "(": ".28", ")": ".29", ".": ".2E"}


def encode_hash_component(value: str) -> str:
    encoded = quote(value, safe="")
    return "".join(_HASH_REPLACEMENTS.get(character, character) for character in encoded)


def message_url(site: str, message: dict[str, Any]) -> str:
    message_id = _positive_int(message.get("id"), "message id")
    base = site.rstrip("/")
    if not base.startswith("https://"):
        raise LinkError("Zulip site must use HTTPS")

    if message.get("type") == "stream":
        stream_id = _positive_int(message.get("stream_id"), "stream id")
        channel = str(message.get("display_recipient", "")).replace(" ", "-")
        topic = str(message.get("subject", ""))
        channel_slug = f"{stream_id}-{encode_hash_component(channel)}"
        return (
            f"{base}/#narrow/channel/{channel_slug}/topic/"
            f"{encode_hash_component(topic)}/near/{message_id}"
        )

    recipients = message.get("display_recipient", [])
    if not isinstance(recipients, list):
        raise LinkError("invalid direct-message recipients")
    user_ids = sorted({_positive_int(item.get("id"), "recipient id") for item in recipients if isinstance(item, dict)})
    if not user_ids:
        raise LinkError("direct message has no recipients")
    suffix = "-group" if len(user_ids) >= 3 else ""
    slug = ",".join(str(user_id) for user_id in user_ids) + suffix
    return f"{base}/#narrow/dm/{slug}/near/{message_id}"


def summary_url(site: str, summary: dict[str, Any]) -> str:
    message = {
        "id": summary.get("id"),
        "type": summary.get("type"),
        "stream_id": summary.get("stream_id"),
        "display_recipient": (
            summary.get("recipient_ids", [])
            if summary.get("type") == "private"
            else summary.get("channel", "")
        ),
        "subject": summary.get("topic", ""),
    }
    if message["type"] == "private":
        message["display_recipient"] = [{"id": value} for value in message["display_recipient"]]
    return message_url(site, message)


def _positive_int(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise LinkError(f"invalid {label}") from exc
    if number <= 0:
        raise LinkError(f"invalid {label}")
    return number

