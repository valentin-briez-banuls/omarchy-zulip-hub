from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, TextIO
from urllib.parse import urlsplit

from .api import ZulipAPIError, ZulipClient
from .config import ConfigError, Paths, load_config
from .files import write_atomic
from .secrets import SecretError, SecretToolProvider


class OnboardingError(RuntimeError):
    """A graphical onboarding request was invalid or failed."""


@dataclass
class OnboardingManager:
    config_path: Path
    run: Any = subprocess.run
    secrets: SecretToolProvider | None = None
    state_path: Path | None = None

    def __post_init__(self) -> None:
        if self.secrets is None:
            self.secrets = SecretToolProvider()
        if self.state_path is None:
            self.state_path = Paths.defaults().state

    @staticmethod
    def _settings(config: Any) -> dict[str, Any]:
        notifications = config.notifications
        return {
            "notifications_enabled": notifications.enabled,
            "private_messages": notifications.private_messages,
            "mentions": notifications.mentions,
            "followed_topics": notifications.followed_topics,
            "other_messages": notifications.other_messages,
            "hide_content_when_locked": notifications.hide_content_when_locked,
            "group_window_seconds": notifications.group_window_seconds,
            "muted_channels": list(notifications.muted_channels),
            "always_channels": list(notifications.always_channels),
            "open_mode": config.opening.mode,
            "desktop_command": list(config.opening.desktop_command),
            "workspace_launch_command": list(config.workspace.launch_command),
            "desktop_command_text": shlex.join(config.opening.desktop_command),
            "workspace_launch_command_text": shlex.join(config.workspace.launch_command),
        }

    def _service_state(self) -> str:
        if self._embedded():
            return "inactive" if self._pause_path().exists() else "active"
        try:
            result = self.run(
                ["systemctl", "--user", "is-active", "zulip-hub.service"],
                check=False, capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        return result.stdout.strip() or "inactive"

    @staticmethod
    def _embedded() -> bool:
        return os.environ.get("ZULIP_HUB_EMBEDDED") == "1"

    def _pause_path(self) -> Path:
        assert self.state_path is not None
        return self.state_path.parent / "paused"

    def _request_restart(self) -> None:
        assert self.state_path is not None
        marker = self.state_path.parent / "restart"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    def status(self) -> dict[str, Any]:
        site = ""
        email = ""
        valid = False
        try:
            config = load_config(self.config_path)
            site, email = config.account.site, config.account.email
            valid = not (
                urlsplit(site).hostname in {"zulip.example.com", "example.com"}
                or email.endswith("@example.com")
            )
        except ConfigError:
            pass
        has_secret = False
        if valid:
            try:
                assert self.secrets is not None
                self.secrets.get(site, email)
                has_secret = True
            except SecretError:
                pass
        service = self._service_state()
        return {
            "ok": True,
            "configured": valid and has_secret,
            "site": site if valid else "",
            "email": email if valid else "",
            "has_secret": has_secret,
            "service": service,
            "active": service == "active",
            "settings": self._settings(config) if 'config' in locals() else {},
        }

    @staticmethod
    def _replace_section(text: str, name: str, values: list[tuple[str, Any]]) -> str:
        lines = text.splitlines()
        header = f"[{name}]"
        start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
        rendered = []
        for key, value in values:
            if isinstance(value, bool):
                encoded = "true" if value else "false"
            else:
                encoded = json.dumps(value, ensure_ascii=False)
            rendered.append(f"{key} = {encoded}")
        if start is None:
            return "\n".join(lines).rstrip() + f"\n\n{header}\n" + "\n".join(rendered) + "\n"
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")),
            len(lines),
        )
        keys = {key for key, _ in values}
        body = [
            line for line in lines[start + 1:end]
            if not any(re.match(rf"^\s*{re.escape(key)}\s*=", line) for key in keys)
        ]
        updated = lines[:start + 1] + rendered + body + lines[end:]
        return "\n".join(updated).rstrip() + "\n"

    @staticmethod
    def _bool(request: dict[str, Any], name: str) -> bool:
        value = request.get(name)
        if not isinstance(value, bool):
            raise OnboardingError(f"Le réglage {name} doit être un booléen.")
        return value

    @staticmethod
    def _channels(request: dict[str, Any], name: str) -> list[str]:
        value = request.get(name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise OnboardingError(f"Le réglage {name} doit être une liste.")
        result = []
        for item in value:
            normalized = item.strip()
            if normalized and normalized not in result:
                if len(normalized) > 100:
                    raise OnboardingError("Un nom de canal est trop long.")
                result.append(normalized)
        if len(result) > 100:
            raise OnboardingError("La liste de canaux est trop longue.")
        return result

    @staticmethod
    def _command(request: dict[str, Any], name: str) -> list[str]:
        raw = str(request.get(name, "")).strip()
        if len(raw) > 1000:
            raise OnboardingError("La commande de lancement est trop longue.")
        try:
            result = shlex.split(raw)
        except ValueError as exc:
            raise OnboardingError("La commande de lancement contient des guillemets invalides.") from exc
        if len(result) > 20 or any(not item or len(item) > 300 for item in result):
            raise OnboardingError("La commande de lancement est invalide.")
        return result

    def save_settings(self, request: dict[str, Any]) -> dict[str, Any]:
        group_window = request.get("group_window_seconds")
        if not isinstance(group_window, int) or isinstance(group_window, bool) or not 1 <= group_window <= 300:
            raise OnboardingError("Le regroupement doit être compris entre 1 et 300 secondes.")
        open_mode = str(request.get("open_mode", "auto"))
        if open_mode not in {"auto", "desktop", "browser"}:
            raise OnboardingError("Le mode d’ouverture est invalide.")
        desktop_command = self._command(request, "desktop_command")
        workspace_command = self._command(request, "workspace_launch_command")
        original = self.config_path.read_text(encoding="utf-8")
        updated = self._replace_section(original, "notifications", [
            ("enabled", self._bool(request, "notifications_enabled")),
            ("private_messages", self._bool(request, "private_messages")),
            ("mentions", self._bool(request, "mentions")),
            ("followed_topics", self._bool(request, "followed_topics")),
            ("other_messages", self._bool(request, "other_messages")),
            ("hide_content_when_locked", self._bool(request, "hide_content_when_locked")),
            ("group_window_seconds", group_window),
            ("muted_channels", self._channels(request, "muted_channels")),
            ("always_channels", self._channels(request, "always_channels")),
        ])
        updated = self._replace_section(updated, "open", [
            ("mode", open_mode), ("desktop_command", desktop_command),
        ])
        updated = self._replace_section(updated, "workspace", [
            ("launch_command", workspace_command),
        ])
        try:
            write_atomic(self.config_path, updated, 0o600)
            load_config(self.config_path)
        except Exception:
            write_atomic(self.config_path, original, 0o600)
            raise
        if self._embedded():
            self._request_restart()
        elif self._service_state() == "active":
            try:
                self.run(
                    ["systemctl", "--user", "restart", "zulip-hub.service"],
                    check=True, capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise OnboardingError("Réglages enregistrés, mais le bridge n’a pas redémarré.") from exc
        result = self.status()
        result["message"] = "Réglages enregistrés."
        return result

    def diagnostics(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        try:
            assert self.state_path is not None
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
        return {
            "ok": True,
            "service": self._service_state(),
            "connected": state.get("connected") is True,
            "last_sync": state.get("last_sync"),
            "bridge_error": str(state.get("error") or ""),
            "state_available": bool(state),
            "state_schema": state.get("schema_version"),
        }

    def reconnect(self) -> dict[str, Any]:
        status = self.status()
        if not status["configured"]:
            raise OnboardingError("Configurez d’abord le compte Zulip.")
        if self._embedded():
            self._pause_path().unlink(missing_ok=True)
            self._request_restart()
        else:
            try:
                self.run(
                    ["systemctl", "--user", "enable", "--now", "zulip-hub.service"],
                    check=True, capture_output=True, text=True, timeout=30,
                )
                self.run(
                    ["systemctl", "--user", "restart", "zulip-hub.service"],
                    check=True, capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise OnboardingError("Le bridge Zulip n’a pas pu redémarrer.") from exc
        result = self.diagnostics()
        result["message"] = "Reconnexion du bridge demandée."
        return result

    @staticmethod
    def _credentials(request: dict[str, Any]) -> tuple[str, str, str]:
        site = str(request.get("site", "")).strip().rstrip("/")
        email = str(request.get("email", "")).strip()
        api_key = str(request.get("api_key", "")).strip()
        parsed = urlsplit(site)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise OnboardingError("L’URL Zulip doit être une adresse HTTPS valide.")
        if parsed.query or parsed.fragment:
            raise OnboardingError("L’URL Zulip ne doit contenir ni paramètres ni fragment.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise OnboardingError("L’adresse e-mail est invalide.")
        if not api_key or len(api_key) > 500:
            raise OnboardingError("La clé API est vide ou invalide.")
        return site, email, api_key

    def _write_account(self, site: str, email: str) -> None:
        try:
            text = self.config_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise OnboardingError("Le fichier de configuration n’est pas installé.") from exc
        lines = text.splitlines()
        start = next((i for i, line in enumerate(lines) if line.strip() == "[account]"), None)
        if start is None:
            raise OnboardingError("La section [account] est absente de la configuration.")
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")),
            len(lines),
        )
        body = [
            line for line in lines[start + 1:end]
            if not re.match(r"^\s*(site|email)\s*=", line)
        ]
        escaped_site = json.dumps(site, ensure_ascii=False)
        escaped_email = json.dumps(email, ensure_ascii=False)
        updated = lines[:start + 1] + [f"site = {escaped_site}", f"email = {escaped_email}"] + body + lines[end:]
        write_atomic(self.config_path, "\n".join(updated).rstrip() + "\n", 0o600)
        load_config(self.config_path)

    def setup(self, request: dict[str, Any]) -> dict[str, Any]:
        site, email, api_key = self._credentials(request)
        identity = ZulipClient(site, email, api_key, timeout=15).test_connection()
        assert self.secrets is not None
        self.secrets.store(site, email, api_key)
        self._write_account(site, email)
        if self._embedded():
            self._pause_path().unlink(missing_ok=True)
            self._request_restart()
        else:
            try:
                self.run(
                    ["systemctl", "--user", "enable", "--now", "zulip-hub.service"],
                    check=True, capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise OnboardingError("Connexion validée, mais le service n’a pas pu démarrer.") from exc
        result = self.status()
        result["identity"] = str(identity.get("full_name") or identity.get("email") or email)
        result["message"] = "Connexion réussie. Zulip Hub est actif."
        return result

    def deactivate(self) -> dict[str, Any]:
        if self._embedded():
            pause = self._pause_path()
            pause.parent.mkdir(parents=True, exist_ok=True)
            pause.touch()
            self._request_restart()
        else:
            self.run(
                ["systemctl", "--user", "disable", "--now", "zulip-hub.service"],
                check=False, capture_output=True, text=True, timeout=30,
            )
        result = self.status()
        result["message"] = "Zulip Hub est en pause."
        return result

    def activate(self) -> dict[str, Any]:
        try:
            config = load_config(self.config_path)
            assert self.secrets is not None
            self.secrets.get(config.account.site, config.account.email)
            if self._embedded():
                self._pause_path().unlink(missing_ok=True)
                self._request_restart()
            else:
                self.run(
                    ["systemctl", "--user", "enable", "--now", "zulip-hub.service"],
                    check=True, capture_output=True, text=True, timeout=30,
                )
        except (ConfigError, SecretError) as exc:
            raise OnboardingError("Le compte doit être reconnecté avant activation.") from exc
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise OnboardingError("Le service Zulip Hub n’a pas pu démarrer.") from exc
        result = self.status()
        result["message"] = "Zulip Hub est actif."
        return result

    def disconnect(self) -> dict[str, Any]:
        try:
            config = load_config(self.config_path)
            self.deactivate()
            assert self.secrets is not None
            self.secrets.delete(config.account.site, config.account.email)
        except ConfigError as exc:
            raise OnboardingError(str(exc)) from exc
        result = self.status()
        result["message"] = "Clé supprimée du trousseau."
        return result

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request.get("action", "status"))
        if action == "status":
            return self.status()
        if action == "setup":
            return self.setup(request)
        if action == "deactivate":
            return self.deactivate()
        if action == "activate":
            return self.activate()
        if action == "disconnect":
            return self.disconnect()
        if action == "save_settings":
            return self.save_settings(request)
        if action == "diagnostics":
            return self.diagnostics()
        if action == "reconnect":
            return self.reconnect()
        raise OnboardingError("Action d’onboarding inconnue.")


def serve_once(
    config_path: Path | None = None,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    try:
        raw = input_stream.readline(65537)
        if not raw or len(raw) > 65536:
            raise OnboardingError("Requête d’onboarding absente ou trop volumineuse.")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise OnboardingError("La requête d’onboarding doit être un objet JSON.")
        response = OnboardingManager(config_path or Paths.defaults().config).handle(request)
    except (OnboardingError, ZulipAPIError, SecretError, ConfigError, json.JSONDecodeError) as exc:
        response = {"ok": False, "error": str(exc)}
    output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
    output_stream.flush()
    return 0
