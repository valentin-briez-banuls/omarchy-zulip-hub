from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from . import commands
from .commands import CommandError

from .files import (
    BEGIN,
    END,
    HYPR_BLOCK,
    is_managed_module,
    write_atomic,
    write_exclusive,
    write_no_follow,
)


PLUGIN_ID = "io.github.valentin-briez-banuls.zulip-hub"


class IntegrationError(RuntimeError):
    pass


class OsIntegration:
    def __init__(self, source_root: Path, home: Path | None = None) -> None:
        self.source_root = source_root
        self.home = home or Path.home()
        self.config = self.home / ".config"
        self.hypr_main = self.config / "hypr/hyprland.lua"
        self.hypr_module = self.config / "hypr/zulip_hub.lua"
        self.source_module = source_root / "hyprland/zulip.lua"

    def status(self) -> dict[str, object]:
        installed = (
            self.hypr_main.exists()
            and self.hypr_module.exists()
            and HYPR_BLOCK.strip() in self.hypr_main.read_text(encoding="utf-8")
            and self.hypr_module.read_bytes() == self.source_module.read_bytes()
        )
        return {"ok": True, "installed": installed, "plugin_id": PLUGIN_ID}

    @staticmethod
    def _run(argv: list[str]):
        try:
            result = commands.run(argv, timeout=30)
        except CommandError as exc:
            raise IntegrationError(str(exc)) from exc
        if result.returncode != 0:
            raise IntegrationError(result.stdout.strip() or f"échec de {argv[0]}")
        return result

    @staticmethod
    def _reload_quietly() -> None:
        """Rechargement de secours : son échec ne doit pas masquer l’erreur."""
        try:
            commands.run(["hyprctl", "reload"], timeout=30)
        except CommandError:
            pass

    def _prepare_backup(self, path: Path) -> None:
        """Libère le chemin de sauvegarde, sans jamais écrire à travers autre chose.

        Une sauvegarde laissée par une installation précédente est un fichier
        ordinaire, remplaçable. Tout le reste — lien symbolique, répertoire —
        signale que le chemin est détourné, et le retrait est refusé.
        """
        try:
            status = os.lstat(path)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise IntegrationError(f"sauvegarde inaccessible: {path}") from exc
        if not stat.S_ISREG(status.st_mode):
            raise IntegrationError(f"chemin de sauvegarde non géré: {path}")
        path.unlink()

    def _validate(self) -> None:
        self._run(["hyprland", "--verify-config", "-c", str(self.hypr_main)])
        self._run(["hyprctl", "reload"])
        errors = self._run(["hyprctl", "configerrors"]).stdout.strip()
        if errors:
            raise IntegrationError(f"Hyprland signale une erreur: {errors}")

    def install(self) -> dict[str, object]:
        if self.status()["installed"]:
            return self.status()
        if not self.hypr_main.exists():
            raise IntegrationError("configuration Hyprland utilisateur introuvable")
        text = self.hypr_main.read_text(encoding="utf-8")
        managed = HYPR_BLOCK in text
        if not managed and (BEGIN in text or END in text):
            raise IntegrationError("bloc Zulip Hub existant incomplet ou modifié")
        if not is_managed_module(self.hypr_module):
            raise IntegrationError(f"fichier existant non géré: {self.hypr_module}")
        previous_module = self.hypr_module.read_bytes() if self.hypr_module.exists() else None
        original = self.hypr_main.read_bytes()
        backup = self.hypr_main.with_suffix(".lua.zulip-hub.bak")
        self._prepare_backup(backup)
        write_exclusive(backup, original)
        try:
            write_no_follow(self.hypr_module, self.source_module.read_bytes())
            if not managed:
                write_atomic(self.hypr_main, text.rstrip() + "\n" + HYPR_BLOCK)
            self._validate()
        except Exception:
            write_no_follow(self.hypr_main, original)
            if previous_module is None:
                self.hypr_module.unlink(missing_ok=True)
            else:
                write_no_follow(self.hypr_module, previous_module)
            self._reload_quietly()
            raise
        return self.status()

    def remove(self) -> dict[str, object]:
        if not self.hypr_main.exists():
            return {"ok": True, "installed": False, "plugin_id": PLUGIN_ID}
        if not is_managed_module(self.hypr_module):
            raise IntegrationError(f"fichier modifié conservé: {self.hypr_module}")
        text = self.hypr_main.read_text(encoding="utf-8")
        if BEGIN in text and HYPR_BLOCK not in text:
            raise IntegrationError("bloc Zulip Hub modifié; retrait refusé")
        # Le retrait est une transaction : une validation Hyprland qui échoue
        # laisserait sinon la configuration amputée de son bloc et le module
        # supprimé, sans moyen de revenir en arrière.
        previous_module = self.hypr_module.read_bytes() if self.hypr_module.exists() else None
        original = self.hypr_main.read_bytes()
        try:
            if HYPR_BLOCK in text:
                write_atomic(self.hypr_main, text.replace(HYPR_BLOCK, "\n"))
            self.hypr_module.unlink(missing_ok=True)
            self._validate()
        except Exception:
            write_no_follow(self.hypr_main, original)
            if previous_module is not None:
                write_no_follow(self.hypr_module, previous_module)
            self._reload_quietly()
            raise
        return {"ok": True, "installed": False, "plugin_id": PLUGIN_ID}


def run_action(source_root: Path, action: str) -> dict[str, object]:
    integration = OsIntegration(source_root)
    return {"status": integration.status, "install": integration.install, "remove": integration.remove}[action]()
