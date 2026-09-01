import QtQuick
import Quickshell

// Rend le panneau Zulip Hub avec les donnees de tests/fixtures/state.json afin
// de produire un apercu reproductible. Aucun compte, serveur ou secret reel.
//
// KeyboardPanel dessine sa carte dans une surface layer-shell plein ecran, donc
// la geometrie utile est publiee ici pour que la capture soit cadree sur la
// carte seule et jamais sur le bureau qui se trouve derriere.
ShellRoot {
  Loader {
    id: pluginLoader
    source: Qt.resolvedUrl("plugins/io.github.valentin-briez-banuls.zulip-hub/plugin/Panel.qml")
    onStatusChanged: if (status === Loader.Error) {
      console.error("ZULIP_HUB_PREVIEW_LOAD_ERROR")
      Qt.exit(1)
    }
  }

  function findCard(node) {
    var pool = node ? node.data : null
    if (!pool) return null
    for (var index = 0; index < pool.length; index++) {
      var candidate = pool[index]
      if (candidate && candidate.cardOrigin !== undefined
          && candidate.contentWidth !== undefined) return candidate
    }
    return null
  }

  Timer {
    id: driver
    property string lastGeometry: ""
    interval: 300
    running: true
    repeat: true
    onTriggered: {
      var plugin = pluginLoader.item
      if (!plugin || !plugin.onboardingController
          || plugin.onboardingController.available !== true) return
      plugin.onboardingController.ready = true
      plugin.onboardingController.configured = true
      plugin.onboardingController.editing = false
      plugin.onboardingController.settingsOpen = false
      plugin.onboardingController.diagnosticsOpen = false
      // Les messages de statut sont transitoires : un apercu montre le panneau au repos.
      plugin.actionMessage = ""
      plugin.actionError = ""
      if (!plugin.opened) plugin.toggle()
      if (!plugin.opened || !plugin.hub.loaded) return
      var card = findCard(plugin)
      if (!card || card.contentWidth <= 0 || card.contentHeight <= 0) return
      var geometry = Math.round(card.cardOrigin.x) + " " + Math.round(card.cardOrigin.y) + " "
        + Math.round(card.contentWidth) + " " + Math.round(card.contentHeight)
      if (geometry === driver.lastGeometry) return
      driver.lastGeometry = geometry
      console.log("ZULIP_HUB_PREVIEW_GEOMETRY " + geometry)
    }
  }
}
