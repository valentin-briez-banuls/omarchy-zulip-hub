from __future__ import annotations

import shutil
import subprocess
from typing import Sequence

from .config import OpenConfig


class OpenError(RuntimeError):
    """The message URL could not be opened."""


class UrlOpener:
    def __init__(self, config: OpenConfig):
        self.config = config

    def command(self, url: str) -> list[str]:
        desktop = list(self.config.desktop_command)
        if self.config.mode in {"auto", "desktop"} and desktop:
            if shutil.which(desktop[0]):
                return [*desktop, url]
            if self.config.mode == "desktop":
                raise OpenError(f"application Zulip introuvable: {desktop[0]}")
        if self.config.mode == "desktop":
            raise OpenError("open.desktop_command doit être configuré en mode desktop")
        if shutil.which("uwsm-app"):
            return ["uwsm-app", "--", "xdg-open", url]
        if shutil.which("xdg-open"):
            return ["xdg-open", url]
        raise OpenError("aucun ouvreur d’URL disponible")

    def open(self, url: str) -> None:
        try:
            subprocess.Popen(
                self.command(url),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise OpenError("impossible d’ouvrir le message Zulip") from exc

