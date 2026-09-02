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

  // Larret est cooperatif : le bridge ne voit le signal quau retour de son
  // interrogation longue. Sans echeance, un bridge muet resterait indefiniment.
  function stopBridge() {
    if (!bridge.running) return
    bridge.signal(15)
    escalation.restart()
  }

  function restartBridge() {
    if (bridge.running) stopBridge()
    else retry.restart()
  }

  Component.onCompleted: startBridge()
  Component.onDestruction: {
    root.stopping = true
    // A la destruction, aucun minuteur ne survit pour escalader : cest le
    // verrou dinstance unique qui empeche un bridge survivant de travailler
    // en parallele du suivant.
    if (bridge.running) bridge.signal(15)
  }

  Process {
    id: bridge
    onExited: {
      escalation.stop()
      if (!root.stopping) retry.restart()
    }
  }

  Timer {
    id: escalation
    interval: 15000
    repeat: false
    onTriggered: if (bridge.running) bridge.signal(9)
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
