import QtQuick
import Quickshell
import Quickshell.Io

Scope {
  id: root

  readonly property string runnerPath: decodeURIComponent(
    String(Qt.resolvedUrl("../run-plugin.py")).replace(/^file:\/\//, ""))
  property bool stopping: false

  function startBridge() {
    if (!bridge.running && !root.stopping) {
      bridge.command = ["/usr/bin/python3", root.runnerPath, "daemon"]
      bridge.running = true
    }
  }

  function restartBridge() {
    if (bridge.running) bridge.signal(15)
    else retry.restart()
  }

  Component.onCompleted: startBridge()
  Component.onDestruction: {
    root.stopping = true
    if (bridge.running) bridge.signal(15)
  }

  Process {
    id: bridge
    onExited: if (!root.stopping) retry.restart()
  }

  Timer {
    id: retry
    interval: 5000
    repeat: false
    onTriggered: root.startBridge()
  }

  FileView {
    path: Quickshell.env("XDG_CONFIG_HOME") !== ""
      ? Quickshell.env("XDG_CONFIG_HOME") + "/zulip-hub/config.toml"
      : Quickshell.env("HOME") + "/.config/zulip-hub/config.toml"
    watchChanges: true
    onFileChanged: root.restartBridge()
  }

  FileView {
    path: Quickshell.env("XDG_STATE_HOME") !== ""
      ? Quickshell.env("XDG_STATE_HOME") + "/zulip-hub/restart"
      : Quickshell.env("HOME") + "/.local/state/zulip-hub/restart"
    watchChanges: true
    onFileChanged: root.restartBridge()
  }
}
