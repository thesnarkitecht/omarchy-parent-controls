import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "thesnarkitecht.kids-lockdown"
  implicitWidth: lockButton.implicitWidth
  implicitHeight: lockButton.implicitHeight
  BarIconButton {
    id: lockButton
    anchors.fill: parent
    bar: root.bar
    text: ""
    tooltipText: "Parent controls"
    Accessible.name: "Parent controls"
    onPressed: function(button) {
      if (button === Qt.LeftButton) Quickshell.execDetached(["/usr/local/bin/omarchy-kids"])
    }
  }
}
