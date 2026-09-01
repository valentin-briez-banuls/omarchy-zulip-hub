#!/bin/bash

# Regenere preview.png a partir de tests/fixtures/state.json.
# Necessite une session Wayland active (Quickshell exige le backend layer-shell).

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin_id=io.github.valentin-briez-banuls.zulip-hub
test_root=$(mktemp -d /tmp/zulip-hub-preview.XXXXXX)
shell_pid=""
cleanup() {
  [[ -n $shell_pid ]] && kill "$shell_pid" 2>/dev/null || true
  rm -rf -- "$test_root"
}
trap cleanup EXIT

# grim attend une image du compositeur. Ecran en veille, cette attente ne finit
# jamais : mieux vaut echouer que bloquer sans rien afficher. Une sortie qui
# vient d etre rallumee met un instant a se declarer active, d ou l attente.
awake=0
for _ in $(seq 1 12); do
  if [[ $(hyprctl monitors -j | jq -r "any(.[]; .dpmsStatus == true)") == true ]]; then
    awake=1
    break
  fi
  sleep 0.5
done
(( awake )) || {
  echo "make-preview: reveillez l ecran avant de capturer" >&2
  exit 1
}

cp -a /usr/share/omarchy/shell "$test_root/shell"
mkdir -p "$test_root/shell/plugins/$plugin_id"
for item in plugin src config hyprland run-plugin.py manifest.json; do
  cp -a "$project_dir/$item" "$test_root/shell/plugins/$plugin_id/$item"
done
cp "$project_dir/tools/PreviewHarness.qml" "$test_root/shell/PreviewHarness.qml"

mkdir -p "$test_root/state/zulip-hub" "$test_root/config"
cp "$project_dir/tests/fixtures/state.json" "$test_root/state/zulip-hub/state.json"

XDG_STATE_HOME="$test_root/state" \
  XDG_CONFIG_HOME="$test_root/config" \
  OMARCHY_PATH="$test_root" \
  quickshell --no-color -p "$test_root/shell/PreviewHarness.qml" >"$test_root/log" 2>&1 &
shell_pid=$!

for _ in $(seq 1 60); do
  grep -q ZULIP_HUB_PREVIEW_GEOMETRY "$test_root/log" && break
  sleep 0.5
done
geometry_line=$(grep -m1 ZULIP_HUB_PREVIEW_GEOMETRY "$test_root/log" || true)
[[ -n $geometry_line ]] || {
  tail -20 "$test_root/log" >&2
  echo "make-preview: le panneau ne sest pas ouvert" >&2
  exit 1
}
sleep 2
geometry_line=$(grep ZULIP_HUB_PREVIEW_GEOMETRY "$test_root/log" | tail -1)
read -r x y w h <<<"${geometry_line##*ZULIP_HUB_PREVIEW_GEOMETRY}"

timeout 20 grim -g "$x,$y ${w}x${h}" "$project_dir/preview.png" || {
  echo "make-preview: grim na pas rendu dimage en 20 s" >&2
  exit 1
}
echo "preview.png regenere depuis $x,$y ${w}x${h}"
