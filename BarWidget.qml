import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "thesnarkitecht.kids-lockdown"
  implicitWidth: label.implicitWidth + 20
  implicitHeight: label.implicitHeight + 12
  Text {
    id: label
    anchors.centerIn: parent
    text: "Parents"
    color: Color.foreground
    font.family: Style.font.family
    font.pixelSize: Style.font.body
  }
  MouseArea {
    anchors.fill: parent
    onClicked: Quickshell.execDetached(["/usr/local/bin/omarchy-kids"])
  }
}
