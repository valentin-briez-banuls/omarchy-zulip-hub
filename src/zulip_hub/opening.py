from __future__ import annotations

from typing import Sequence

from . import commands
from .commands import CommandError
from .config import OpenConfig


class OpenError(RuntimeError):
    """The message URL could not be opened."""


class UrlOpener:
    def __init__(self, config: OpenConfig):
        self.config = config

    def command(self, url: str) -> list[str]:
        desktop = list(self.config.desktop_command)
        if self.config.mode in {"auto", "desktop"} and desktop:
            if commands.available(desktop[0]):
                return [*desktop, url]
            if self.config.mode == "desktop":
                raise OpenError(f"application Zulip introuvable: {desktop[0]}")
        if self.config.mode == "desktop":
            raise OpenError("open.desktop_command doit être configuré en mode desktop")
        if commands.available("uwsm-app"):
            return ["uwsm-app", "--", "xdg-open", url]
        if commands.available("xdg-open"):
            return ["xdg-open", url]
        raise OpenError("aucun ouvreur d’URL disponible")

    def open(self, url: str) -> None:
        try:
            commands.spawn(self.command(url))
        except CommandError as exc:
            raise OpenError("impossible d’ouvrir le message Zulip") from exc

