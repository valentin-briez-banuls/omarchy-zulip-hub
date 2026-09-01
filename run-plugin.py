#!/usr/bin/python3
"""Run Zulip Hub directly from an Omarchy Marketplace checkout."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
os.environ["ZULIP_HUB_EMBEDDED"] = "1"
os.environ["ZULIP_HUB_RUNNER"] = str(ROOT / "run-plugin.py")

home = Path.home()
config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
state_home = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state"))
config_path = config_home / "zulip-hub/config.toml"
if not config_path.exists():
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config/config.example.toml", config_path)
    config_path.chmod(0o600)

if len(sys.argv) > 1 and sys.argv[1] == "daemon" and (state_home / "zulip-hub/paused").exists():
    raise SystemExit(0)

from zulip_hub.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
