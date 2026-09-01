from __future__ import annotations

import subprocess


class SecretError(RuntimeError):
    """The API key is unavailable from Secret Service."""


class SecretToolProvider:
    service = "omarchy-zulip-hub"

    def get(self, site: str, email: str) -> str:
        try:
            result = subprocess.run(
                ["secret-tool", "lookup", "service", self.service, "site", site, "account", email],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError as exc:
            raise SecretError("secret-tool est absent (paquet libsecret requis)") from exc
        except subprocess.TimeoutExpired as exc:
            raise SecretError("le trousseau de secrets ne répond pas") from exc
        key = result.stdout.strip()
        if result.returncode != 0 or not key:
            raise SecretError("clé API Zulip absente du trousseau")
        return key

    def store(self, site: str, email: str, key: str) -> None:
        if not key.strip():
            raise SecretError("la clé API est vide")
        try:
            subprocess.run(
                [
                    "secret-tool", "store", "--label", "Omarchy Zulip Hub API key",
                    "service", self.service, "site", site, "account", email,
                ],
                input=key.strip(), check=True, capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError as exc:
            raise SecretError("secret-tool est absent (paquet libsecret requis)") from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise SecretError("impossible d'enregistrer la clé dans le trousseau") from exc

    def delete(self, site: str, email: str) -> None:
        try:
            result = subprocess.run(
                [
                    "secret-tool", "clear", "service", self.service,
                    "site", site, "account", email,
                ],
                check=False, capture_output=True, text=True, timeout=15,
            )
        except FileNotFoundError as exc:
            raise SecretError("secret-tool est absent (paquet libsecret requis)") from exc
        except subprocess.TimeoutExpired as exc:
            raise SecretError("le trousseau de secrets ne répond pas") from exc
        if result.returncode not in {0, 1}:
            raise SecretError("impossible de supprimer la clé du trousseau")
