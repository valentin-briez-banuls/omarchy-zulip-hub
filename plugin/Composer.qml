import QtQuick
import Quickshell.Io
import "I18n.js" as I18n

QtObject {
  id: root

  readonly property bool available: true
  property bool open: false
  property bool loaded: false
  property bool busy: process.running
  property var users: []
  property var recentUserIds: []
  property var selectedIds: []
  property string query: ""
  property string content: ""
  property string error: ""
  property string message: ""
  property int maxMessageLength: 10000
  property var pendingRequest: null
  property string activeAction: ""
  property string responseLine: ""

  signal sent(int messageId)
  readonly property string localeName: Qt.locale().name
  readonly property string runnerPath: decodeURIComponent(
    String(Qt.resolvedUrl("../run-plugin.py")).replace(/^file:\/\//, ""))

  function t(key) { return I18n.text(key, root.localeName) }

  function request(payload) {
    if (process.running) return false
    root.error = ""
    root.message = ""
    root.responseLine = ""
    root.pendingRequest = payload
    root.activeAction = String(payload.action || "")
    process.stdinEnabled = true
    process.command = ["/usr/bin/python3", root.runnerPath, "compose"]
    process.running = true
    return true
  }

  function loadDirectory(force) {
    if (root.loaded && force !== true) return
    request({ action: "directory" })
  }

  function isSelected(userId) {
    return root.selectedIds.indexOf(Number(userId)) !== -1
  }

  function toggleUser(userId) {
    var id = Number(userId)
    var next = root.selectedIds.slice()
    var index = next.indexOf(id)
    if (index === -1) next.push(id)
    else next.splice(index, 1)
    root.selectedIds = next
  }

  function selectedUsers() {
    var result = []
    for (var index = 0; index < root.selectedIds.length; index++) {
      var id = root.selectedIds[index]
      for (var userIndex = 0; userIndex < root.users.length; userIndex++) {
        if (root.users[userIndex].id === id) {
          result.push(root.users[userIndex])
          break
        }
      }
    }
    return result
  }

  function filteredUsers() {
    var needle = root.query.trim().toLocaleLowerCase()
    var result = root.users.filter(function(user) {
      return needle === ""
        || String(user.full_name).toLocaleLowerCase().indexOf(needle) !== -1
        || String(user.email).toLocaleLowerCase().indexOf(needle) !== -1
    })
    result.sort(function(left, right) {
      var leftRecent = root.recentUserIds.indexOf(left.id) !== -1 ? 0 : 1
      var rightRecent = root.recentUserIds.indexOf(right.id) !== -1 ? 0 : 1
      if (leftRecent !== rightRecent) return leftRecent - rightRecent
      return String(left.full_name).localeCompare(String(right.full_name))
    })
    return result.slice(0, 12)
  }

  function send() {
    if (root.selectedIds.length === 0 || root.content.trim() === ""
        || root.content.length > root.maxMessageLength) return false
    return request({
      action: "send_direct",
      recipient_ids: root.selectedIds,
      content: root.content
    })
  }

  function applyResponse(raw) {
    var response
    try {
      response = JSON.parse(String(raw || ""))
    } catch (exception) {
      root.error = root.t("invalidLocal")
      return
    }
    if (response.ok !== true) {
      root.error = response.delivery_uncertain === true
        ? root.t("uncertain") + String(response.error || "")
        : String(response.error || root.t("operationFailed"))
      return
    }
    if (root.activeAction === "directory") {
      root.users = Array.isArray(response.users) ? response.users : []
      root.recentUserIds = Array.isArray(response.recent_user_ids) ? response.recent_user_ids : []
      root.maxMessageLength = Math.max(1, Number(response.max_message_length) || 10000)
      root.loaded = true
      return
    }
    if (root.activeAction === "send_direct") {
      var messageId = Number(response.message_id) || 0
      root.selectedIds = []
      root.query = ""
      root.content = ""
      root.message = root.t("sent")
      root.open = false
      root.sent(messageId)
    }
  }

  property Process process: Process {
    command: ["/usr/bin/python3", root.runnerPath, "compose"]
    stdinEnabled: true
    stdout: SplitParser {
      onRead: function(value) { root.responseLine = String(value || "") }
    }
    onStarted: {
      if (!root.pendingRequest) {
        process.signal(15)
        return
      }
      process.write(JSON.stringify(root.pendingRequest) + "\n")
      root.pendingRequest = null
      process.stdinEnabled = false
    }
    onExited: function(exitCode) {
      if (root.responseLine !== "") root.applyResponse(root.responseLine)
      else root.error = exitCode === 0
        ? root.t("noLocalResponse")
        : root.t("composeUnavailable")
      root.activeAction = ""
    }
  }
}
