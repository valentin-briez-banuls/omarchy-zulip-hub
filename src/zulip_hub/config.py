from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import tomllib


class ConfigError(ValueError):
    """Configuration cannot be loaded safely."""


def _xdg_path(variable: str, fallback: str) -> Path:
    return Path(os.environ.get(variable, str(Path.home() / fallback))).expanduser()


@dataclass(frozen=True)
class Paths:
    config: Path
    state: Path

    @classmethod
    def defaults(cls) -> "Paths":
        return cls(
            config=_xdg_path("XDG_CONFIG_HOME", ".config") / "zulip-hub/config.toml",
            state=_xdg_path("XDG_STATE_HOME", ".local/state") / "zulip-hub/state.json",
        )


@dataclass(frozen=True)
class AccountConfig:
    site: str
    email: str


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool = True
    private_messages: bool = True
    mentions: bool = True
    followed_topics: bool = True
    other_messages: bool = False
    hide_content_when_locked: bool = True
    group_window_seconds: int = 10
    muted_channels: tuple[str, ...] = ()
    always_channels: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpenConfig:
    mode: str = "auto"
    desktop_command: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceConfig:
    name: str = "zulip"
    class_pattern: str = r"^(Zulip|zulip|zulip-hub|org\.zulip\.Zulip)$"
    launch_command: tuple[str, ...] = ()


@dataclass(frozen=True)
class BridgeConfig:
    account: AccountConfig
    notifications: NotificationConfig = NotificationConfig()
    opening: OpenConfig = OpenConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    recent_message_limit: int = 30
    request_timeout_seconds: int = 90
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0


def load_config(path: Path) -> BridgeConfig:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration introuvable: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"configuration TOML invalide: {exc}") from exc

    account = raw.get("account", {})
    meta = raw.get("meta", {})
    schema_version = meta.get("schema_version", 1)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ConfigError("meta.schema_version doit être un entier")
    if schema_version != 1:
        raise ConfigError(f"version de configuration non prise en charge: {schema_version}")
    site = str(account.get("site", "")).strip().rstrip("/")
    email = str(account.get("email", "")).strip()
    if not site.startswith("https://"):
        raise ConfigError("account.site doit utiliser https://")
    if not email or "@" not in email:
        raise ConfigError("account.email est manquant ou invalide")
    if "key" in account or "api_key" in account:
        raise ConfigError("la clé API ne doit pas être stockée dans config.toml")

    bridge = raw.get("bridge", {})
    limit = int(bridge.get("recent_message_limit", 30))
    timeout = int(bridge.get("request_timeout_seconds", 90))
    initial = float(bridge.get("initial_backoff_seconds", 1))
    maximum = float(bridge.get("max_backoff_seconds", 60))
    if not 1 <= limit <= 200:
        raise ConfigError("recent_message_limit doit être compris entre 1 et 200")
    if timeout < 10:
        raise ConfigError("request_timeout_seconds doit être >= 10")
    if initial <= 0 or maximum < initial:
        raise ConfigError("configuration du backoff invalide")
    notifications = raw.get("notifications", {})
    group_window = int(notifications.get("group_window_seconds", 10))
    if not 1 <= group_window <= 300:
        raise ConfigError("group_window_seconds doit être compris entre 1 et 300")

    def string_tuple(name: str) -> tuple[str, ...]:
        value = notifications.get(name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ConfigError(f"notifications.{name} doit être une liste de chaînes")
        return tuple(item.strip() for item in value if item.strip())

    def boolean(name: str, default: bool) -> bool:
        value = notifications.get(name, default)
        if not isinstance(value, bool):
            raise ConfigError(f"notifications.{name} doit être un booléen")
        return value

    notification_config = NotificationConfig(
        enabled=boolean("enabled", True),
        private_messages=boolean("private_messages", True),
        mentions=boolean("mentions", True),
        followed_topics=boolean("followed_topics", True),
        other_messages=boolean("other_messages", False),
        hide_content_when_locked=boolean("hide_content_when_locked", True),
        group_window_seconds=group_window,
        muted_channels=string_tuple("muted_channels"),
        always_channels=string_tuple("always_channels"),
    )

    opening = raw.get("open", {})
    mode = str(opening.get("mode", "auto")).strip().lower()
    if mode not in {"auto", "desktop", "browser"}:
        raise ConfigError("open.mode doit valoir auto, desktop ou browser")
    desktop_command = opening.get("desktop_command", [])
    if not isinstance(desktop_command, list) or not all(
        isinstance(item, str) and item for item in desktop_command
    ):
        raise ConfigError("open.desktop_command doit être une liste de chaînes non vides")

    workspace = raw.get("workspace", {})
    workspace_name = str(workspace.get("name", "zulip")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", workspace_name):
        raise ConfigError("workspace.name contient des caractères non autorisés")
    class_pattern = str(
        workspace.get("class_pattern", r"^(Zulip|zulip|zulip-hub|org\.zulip\.Zulip)$")
    )
    if not class_pattern or len(class_pattern) > 300:
        raise ConfigError("workspace.class_pattern est vide ou trop long")
    if re.search(r"\(\?[=!<]|\\[1-9]", class_pattern):
        raise ConfigError("workspace.class_pattern utilise une fonction non compatible avec RE2")
    try:
        re.compile(class_pattern)
    except re.error as exc:
        raise ConfigError(f"workspace.class_pattern est invalide: {exc}") from exc
    launch_command = workspace.get("launch_command", [])
    if not isinstance(launch_command, list) or not all(
        isinstance(item, str) and item for item in launch_command
    ):
        raise ConfigError("workspace.launch_command doit être une liste de chaînes non vides")

    return BridgeConfig(
        AccountConfig(site, email),
        notification_config,
        OpenConfig(mode, tuple(desktop_command)),
        WorkspaceConfig(workspace_name, class_pattern, tuple(launch_command)),
        limit,
        timeout,
        initial,
        maximum,
    )
