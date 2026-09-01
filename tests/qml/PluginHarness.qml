import QtQuick
import Quickshell

ShellRoot {
  readonly property bool expectOffline: Quickshell.env("ZULIP_HUB_EXPECT_OFFLINE") === "1"

  Loader {
    id: pluginLoader
    source: Qt.resolvedUrl("plugins/io.github.valentin-briez-banuls.zulip-hub/plugin/Panel.qml")
    onStatusChanged: {
      if (status === Loader.Error) {
        console.error("ZULIP_HUB_PLUGIN_LOAD_ERROR")
        Qt.exit(1)
      }
    }
  }

  Loader {
    id: serviceLoader
    source: Qt.resolvedUrl("plugins/io.github.valentin-briez-banuls.zulip-hub/plugin/Service.qml")
    onStatusChanged: if (status === Loader.Error) {
      console.error("ZULIP_HUB_SERVICE_LOAD_ERROR")
      Qt.exit(1)
    }
  }

  Timer {
    interval: 1500
    running: true
    onTriggered: {
      if (pluginLoader.status !== Loader.Ready) {
        console.error("ZULIP_HUB_PLUGIN_NOT_READY")
        Qt.exit(1)
        return
      }
      if (serviceLoader.status !== Loader.Ready) {
        console.error("ZULIP_HUB_SERVICE_NOT_READY")
        Qt.exit(1)
        return
      }
      var plugin = pluginLoader.item
      if (!plugin.onboardingController || plugin.onboardingController.available !== true) {
        console.error("ZULIP_HUB_ONBOARDING_NOT_READY")
        Qt.exit(1)
        return
      }
      plugin.onboardingController.ready = true
      plugin.onboardingController.configured = true
      plugin.onboardingController.settingsOpen = true
      if (!plugin.showSettings) {
        console.error("ZULIP_HUB_SETTINGS_NOT_READY")
        Qt.exit(1)
        return
      }
      plugin.onboardingController.settingsOpen = false
      plugin.onboardingController.diagnosticsOpen = true
      if (!plugin.showDiagnostics) {
        console.error("ZULIP_HUB_DIAGNOSTICS_NOT_READY")
        Qt.exit(1)
        return
      }
      plugin.onboardingController.diagnosticsOpen = false
      if (!plugin.composerController || plugin.composerController.available !== true) {
        console.error("ZULIP_HUB_COMPOSER_NOT_READY")
        Qt.exit(1)
        return
      }
      plugin.composerController.loaded = true
      plugin.composerController.users = [
        {id: 7, full_name: "Alice", email: "alice@example.com"},
        {id: 8, full_name: "Bob", email: "bob@example.com"}
      ]
      plugin.composerController.recentUserIds = [8]
      plugin.composerController.selectedIds = [7, 8]
      plugin.composerController.content = "Brouillon"
      plugin.composerController.open = true
      if (!plugin.showComposer || plugin.composerController.selectedUsers().length !== 2
          || plugin.composerController.filteredUsers()[0].id !== 8) {
        console.error("ZULIP_HUB_COMPOSER_STATE_MISMATCH")
        Qt.exit(1)
        return
      }
      plugin.composerController.open = false
      if (plugin.composerController.content !== "Brouillon") {
        console.error("ZULIP_HUB_DRAFT_NOT_PRESERVED")
        Qt.exit(1)
        return
      }
      if (expectOffline) {
        if (plugin.hub.loaded || plugin.hub.connected || plugin.hub.statusText === "") {
          console.error("ZULIP_HUB_OFFLINE_STATE_MISMATCH")
          Qt.exit(1)
          return
        }
        console.log("ZULIP_HUB_PLUGIN_OFFLINE_READY")
        Qt.exit(0)
        return
      }
      if (!plugin.hub.loaded || !plugin.hub.connected) {
        console.error("ZULIP_HUB_STATE_NOT_LOADED")
        Qt.exit(1)
        return
      }
      if (plugin.hub.unread.total !== 5 || plugin.hub.unread.mentions !== 2
          || plugin.hub.unread.private !== 1 || plugin.messageCount !== 2
          || plugin.hasMentions !== true) {
        console.error("ZULIP_HUB_STATE_MISMATCH")
        Qt.exit(1)
        return
      }
      console.log("ZULIP_HUB_PLUGIN_READY")
      Qt.exit(0)
    }
  }
}
