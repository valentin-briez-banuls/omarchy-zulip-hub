#!/bin/bash

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d /tmp/zulip-hub-qml.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT

cp -a /usr/share/omarchy/shell "$test_root/shell"
mkdir -p "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub"
cp -a "$project_dir/plugin" "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub/plugin"
cp -a "$project_dir/src" "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub/src"
cp -a "$project_dir/config" "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub/config"
cp -a "$project_dir/hyprland" "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub/hyprland"
cp "$project_dir/run-plugin.py" "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub/run-plugin.py"
cp "$project_dir/manifest.json" "$test_root/shell/plugins/io.github.valentin-briez-banuls.zulip-hub/manifest.json"
cp "$project_dir/tests/qml/PluginHarness.qml" "$test_root/shell/PluginHarness.qml"

mkdir -p "$test_root/state/zulip-hub"
mkdir -p "$test_root/config"
cp "$project_dir/tests/fixtures/state.json" "$test_root/state/zulip-hub/state.json"
XDG_STATE_HOME="$test_root/state" \
  XDG_CONFIG_HOME="$test_root/config" \
  OMARCHY_PATH="$test_root" \
  quickshell --no-color -p "$test_root/shell/PluginHarness.qml"

rm -f "$test_root/state/zulip-hub/state.json"
ZULIP_HUB_EXPECT_OFFLINE=1 \
  XDG_STATE_HOME="$test_root/state" \
  XDG_CONFIG_HOME="$test_root/config" \
  OMARCHY_PATH="$test_root" \
  quickshell --no-color -p "$test_root/shell/PluginHarness.qml"
