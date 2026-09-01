from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from .files import BEGIN, END, HYPR_BLOCK, is_managed_module, write_atomic


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
    def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
            raise IntegrationError(detail.strip()) from exc

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
        backup = self.hypr_main.with_suffix(".lua.zulip-hub.bak")
        shutil.copy2(self.hypr_main, backup)
        try:
            self.hypr_module.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.source_module, self.hypr_module)
            if not managed:
                write_atomic(self.hypr_main, text.rstrip() + "\n" + HYPR_BLOCK)
            self._validate()
        except Exception:
            shutil.copy2(backup, self.hypr_main)
            if previous_module is None:
                self.hypr_module.unlink(missing_ok=True)
            else:
                self.hypr_module.write_bytes(previous_module)
            subprocess.run(["hyprctl", "reload"], check=False, capture_output=True, text=True)
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
        if HYPR_BLOCK in text:
            write_atomic(self.hypr_main, text.replace(HYPR_BLOCK, "\n"))
        self.hypr_module.unlink(missing_ok=True)
        self._validate()
        return {"ok": True, "installed": False, "plugin_id": PLUGIN_ID}


def run_action(source_root: Path, action: str) -> dict[str, object]:
    integration = OsIntegration(source_root)
    return {"status": integration.status, "install": integration.install, "remove": integration.remove}[action]()
