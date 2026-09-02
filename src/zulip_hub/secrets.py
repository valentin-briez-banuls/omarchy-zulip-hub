from __future__ import annotations

from . import commands
from .commands import CommandError


class SecretError(RuntimeError):
    """The API key is unavailable from Secret Service."""


class SecretToolProvider:
    service = "omarchy-zulip-hub"

    def get(self, site: str, email: str) -> str:
        try:
            result = commands.run(
                ["secret-tool", "lookup", "service", self.service, "site", site, "account", email],
                timeout=15,
            )
        except CommandError as exc:
            raise SecretError("le trousseau de secrets est indisponible") from exc
        key = result.stdout.strip()
        if result.returncode != 0 or not key:
            raise SecretError("clé API Zulip absente du trousseau")
        return key

    def store(self, site: str, email: str, key: str) -> None:
        if not key.strip():
            raise SecretError("la clé API est vide")
        try:
            result = commands.run(
                [
                    "secret-tool", "store", "--label", "Omarchy Zulip Hub API key",
                    "service", self.service, "site", site, "account", email,
                ],
                stdin=key.strip(), timeout=30,
            )
        except CommandError as exc:
            raise SecretError("impossible d'enregistrer la clé dans le trousseau") from exc
        if result.returncode != 0:
            raise SecretError("impossible d'enregistrer la clé dans le trousseau")

    def delete(self, site: str, email: str) -> None:
        try:
            result = commands.run(
                [
                    "secret-tool", "clear", "service", self.service,
                    "site", site, "account", email,
                ],
                timeout=15,
            )
        except CommandError as exc:
            raise SecretError("le trousseau de secrets est indisponible") from exc
        if result.returncode not in {0, 1}:
            raise SecretError("impossible de supprimer la clé du trousseau")
