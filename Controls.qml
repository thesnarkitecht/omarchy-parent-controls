import QtQuick
import QtQuick.Controls as QQC
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

Item {
  id: root
  property var shell: null
  property var manifest: null
  property bool opened: false
  property string page: "home"
  property string message: ""
  property bool failed: false
  property var state: ({policy: {native: [], webapps: []}, family: {voice: {enabled:false,wake_enabled:true,phrase:"Hey Laya"}, videos:[], requests:[], voice_installed:false}, ready: false, active: false, hermes: false})
  property var pending: ({})
  property string requestJson: ""
  property string currentAction: ""
  property string editingId: ""
  readonly property bool busy: bridge.running

  function open(payloadJson) {
    opened = true
    page = "home"
    message = ""
    call({action: "status"})
  }
  function close() { opened = false; pin.text = ""; pending = ({}); requestJson = "" }
  function dismiss() {
    if (busy) return
    close()
    if (shell) shell.hide("thesnarkitecht.kids-lockdown")
  }
  function toggle() { opened ? dismiss() : open("{}") }
  function call(value) {
    if (busy) return
    currentAction = value.action
    requestJson = JSON.stringify(value)
    message = ""
    failed = false
    bridge.running = true
  }
  function approve(value) {
    pending = value
    page = "pin"
    pin.text = ""
    message = ""
    Qt.callLater(function() { pin.forceActiveFocus() })
  }
  function submit() {
    if (!/^[0-9]{8,12}$/.test(pin.text)) {
      failed = true; message = "Enter your 8–12 digit parent PIN."; return
    }
    var value = Object.assign({}, pending, {pin: pin.text})
    pin.text = ""
    call(value)
  }

  Process {
    id: bridge
    command: ["/usr/local/lib/omarchy-kids/run", "bridge"]
    stdinEnabled: true
    onStarted: { write(root.requestJson + "\n"); root.requestJson = "" }
    stdout: StdioCollector { id: output; waitForEnd: true }
    onExited: function(code) {
      try {
        var response = JSON.parse(output.text)
        if (!response.ok) throw new Error(response.error || "Could not complete this action.")
        if (root.currentAction === "status") root.state = response
        else {
          if (response.policy) root.state = Object.assign({}, root.state, response)
          if (root.currentAction === "start" || root.currentAction === "stop")
            root.state = Object.assign({}, root.state, {active: root.currentAction === "start"})
          root.message = response.message || "Saved."
          root.page = "home"
          root.pending = ({})
          if (root.currentAction === "start") root.close()
          if ((root.currentAction === "parent-tool" || root.currentAction === "open-pairing")) root.dismiss()
        }
      } catch (error) {
        root.failed = true
        root.message = String(error.message || error)
      }
    }
  }

  component Label: Text {
    color: Color.menu.text
    font.family: Style.font.menuFamily
    font.pixelSize: Style.font.body
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
  }
  component Action: Button {
    focusable: true
    bordered: true
    enabled: !root.busy
    opacity: enabled ? 1 : 0.5
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-kids-controls"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    Rectangle { anchors.fill: parent; color: Color.menu.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.dismiss() }
    BorderSurface {
      id: card
      anchors.centerIn: parent
      width: Math.min(Style.space(500), panel.width - Style.space(32))
      height: Math.min(content.implicitHeight + Style.spacing.panelPadding * 2, panel.height - Style.space(32))
      color: Qt.rgba(Color.menu.background.r, Color.menu.background.g, Color.menu.background.b, 1)
      radius: Style.cornerRadius
      borderSpec: Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))
      MouseArea { anchors.fill: parent; onClicked: {} }
      Flickable {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        contentHeight: content.implicitHeight
        clip: true
        Column {
          id: content
          width: parent.width
          spacing: Style.spacing.panelPadding
          Keys.onEscapePressed: root.dismiss()
          Row {
            width: parent.width
            Label { width: parent.width - closeButton.width; text: "Parent controls"; font.pixelSize: Style.font.title; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
            Button { id: closeButton; text: "Esc  ×"; focusable: true; onClicked: root.dismiss() }
          }
          Column {
            visible: root.page === "home"
            width: parent.width
            spacing: Style.space(16)
            Label { width: parent.width; text: root.state.active ? (root.state.healthy === false ? "Controls need attention" : "Controlled mode is on") : (root.state.ready ? "Controlled mode is off" : "Finishing account setup"); font.pixelSize: Style.font.subtitle; color: Color.accent }
            Label { visible: root.state.active && root.state.healthy === false; width: parent.width; text: "The last change did not finish. Turn controls off with your PIN to retry restoring normal access."; color: Color.urgent }
            Label { width: parent.width; text: root.state.active ? "Only approved apps and websites. Changes need your PIN." : "All apps and browsing are available. Turn controls on when ready." }
            Action { width: parent.width; text: root.state.active ? "Turn controlled mode off" : "Turn controlled mode on"; selected: true; onClicked: root.approve({action: root.state.active ? "disable-controls" : "enable-controls"}) }
            Label { width: parent.width; text: "Manage apps, videos and settings in Omarchy Parent Controls on your phone."; opacity: 0.7 }
            Label { width: parent.width; text: "To pair a phone, run omarchy-parent-controls pair in Terminal."; opacity: 0.65 }
            Label { visible: !root.state.ready && !root.busy; width: parent.width; text: root.state.notice || "Checking setup…"; color: Color.accent }
          }
          Column {
            visible: root.page === "pin"
            width: parent.width
            spacing: Style.space(12)
            Label { text: "Parent approval"; font.pixelSize: Style.font.subtitle; font.bold: true }
            Label { width: parent.width; text: root.pending.action === "clear-webapp-data" ? "Clear this webapp’s history, cookies and cached files? This signs it out. Enter your PIN to continue." : "Enter your PIN to approve this change." }
            TextField { id: pin; width: parent.width; password: true; placeholderText: "Parent PIN"; maximumLength: 12; enabled: !root.busy; onAccepted: root.submit() }
            Action { width: parent.width; text: root.busy ? "Working…" : "Approve"; selected: true; onClicked: root.submit() }
            Button { text: "← Back"; enabled: !root.busy; focusable: true; onClicked: { pin.text = ""; root.pending = ({}); root.page = "home" } }
          }
          Label { visible: root.message !== ""; width: parent.width; text: root.message; color: root.failed ? Color.urgent : Color.accent }
        }
      }
    }
  }
}
