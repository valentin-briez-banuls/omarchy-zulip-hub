#!/bin/bash

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -v
omarchy plugin validate .
luac -p hyprland/zulip.lua tests/hyprland/verify.lua
OMARCHY_PATH=/usr/share/omarchy \
  ZULIP_HUB_HYPR_MODULE="$project_dir/hyprland/zulip.lua" \
  hyprland --verify-config -c "$project_dir/tests/hyprland/verify.lua"
tests/run_qml_integration.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m compileall -q -f src tests

echo "ZULIP_HUB_RELEASE_CHECKS_OK"
