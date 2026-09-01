import QtQuick
import qs.Commons

Item {
  id: root

  property real iconSize: Style.font.icon
  property color color: Color.foreground
  property bool connected: true
  property bool urgent: false

  width: iconSize
  height: iconSize
  implicitWidth: iconSize
  implicitHeight: iconSize

  // Monochrome interpretation of Zulip's round mark. Like Omarchy's Dropbox
  // and Tailscale icons, the silhouette follows the active theme color.
  Canvas {
    id: mark
    anchors.fill: parent
    opacity: root.connected ? 1.0 : 0.45
    onPaint: {
      var context = getContext("2d")
      context.reset()
      context.fillStyle = root.color
      context.beginPath()
      context.moveTo(width * 0.50, height * 0.05)
      context.bezierCurveTo(width * 0.78, height * 0.05, width * 0.95, height * 0.22, width * 0.95, height * 0.50)
      context.bezierCurveTo(width * 0.95, height * 0.78, width * 0.78, height * 0.95, width * 0.50, height * 0.95)
      context.bezierCurveTo(width * 0.22, height * 0.95, width * 0.05, height * 0.78, width * 0.05, height * 0.50)
      context.bezierCurveTo(width * 0.05, height * 0.22, width * 0.22, height * 0.05, width * 0.50, height * 0.05)
      context.closePath()
      context.fill()
    }
  }

  onColorChanged: mark.requestPaint()
  onWidthChanged: mark.requestPaint()
  onHeightChanged: mark.requestPaint()

  Text {
    anchors.centerIn: parent
    anchors.verticalCenterOffset: -root.height * 0.02
    text: "Z"
    color: Color.background
    font.family: Style.font.family
    font.pixelSize: root.height * 0.58
    font.bold: true
  }

  Rectangle {
    visible: root.urgent
    width: Math.max(3, root.width * 0.24)
    height: width
    radius: width / 2
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    color: Color.urgent
    border.width: 1
    border.color: Color.background
  }
}
