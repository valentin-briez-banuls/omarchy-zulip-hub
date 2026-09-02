import QtQuick
import Quickshell.Io

// Omarchy conserve le composant deja charge d un widget de barre tant que l URL
// du plugin ne change pas. Apres une mise a jour, les fichiers sont neufs mais
// l interface reste l ancienne, sans que rien ne le signale.
//
// La version lue au tout premier chargement est donc celle que le shell fait
// reellement tourner ; toute valeur differente lue ensuite vient du disque et
// revele l ecart. Aucune version en dur n est necessaire, donc aucune a oublier
// au moment d une release.
QtObject {
  id: root

  readonly property bool available: true
  property string runningVersion: ""
  property string installedVersion: ""
  property bool restarting: false

  readonly property bool restartNeeded: root.runningVersion !== ""
    && root.installedVersion !== ""
    && root.runningVersion !== root.installedVersion

  function apply(raw) {
    var version = ""
    try {
      version = String(JSON.parse(String(raw || "")).version || "")
    } catch (exception) {
      return
    }
    if (version === "") return
    root.installedVersion = version
    if (root.runningVersion === "") root.runningVersion = version
  }

  function restartShell() {
    if (root.restarting) return
    root.restarting = true
    restartProcess.running = true
  }

  property FileView manifest: FileView {
    path: decodeURIComponent(
      String(Qt.resolvedUrl("../manifest.json")).replace(/^file:\/\//, ""))
    watchChanges: true
    printErrors: false
    onLoaded: root.apply(text())
    onFileChanged: reload()
  }

  property Process restartProcess: Process {
    command: ["/usr/bin/omarchy-restart-shell"]
  }
}
