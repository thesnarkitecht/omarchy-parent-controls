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
  property var state: ({policy: {native: [], webapps: []}, ready: false, active: false, hermes: false})
  property var pending: ({})
  property string requestJson: ""
  property string currentAction: ""
  readonly property bool busy: bridge.running

  function open(payloadJson) {
    opened = true
    page = "home"
    message = ""
    call({action: "status"})
  }
  function close() { opened = false; pin.text = ""; newPin.text = ""; confirmPin.text = ""; pending = ({}); requestJson = "" }
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
          newPin.text = ""; confirmPin.text = ""
          if (root.currentAction === "start") root.close()
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
            Label { width: parent.width; text: root.state.active ? "Controlled mode is on" : (root.state.ready ? "Controlled mode is off" : "Finishing account setup"); font.pixelSize: Style.font.subtitle; color: Color.accent }
            Label { width: parent.width; text: root.state.active ? "Only approved apps and websites. Changes need your PIN." : "All apps and browsing are available. Turn controls on when ready." }
            Action { width: parent.width; text: root.state.active ? "Turn controlled mode off" : "Turn controlled mode on"; selected: true; onClicked: root.approve({action: root.state.active ? "disable-controls" : "enable-controls"}) }
            Row {
              width: parent.width
              Label { width: parent.width - addButton.width; text: "Approved webapps"; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
              Button { id: addButton; text: "+ Add"; focusable: true; onClicked: { root.page = "webapp"; root.message = ""; appName.text = ""; appUrl.text = ""; appOrigins.text = ""; appName.forceActiveFocus() } }
            }
            Label { visible: root.state.policy.webapps.length === 0; width: parent.width; text: "None yet. Only websites you approve will appear."; opacity: 0.65 }
            Repeater {
              model: root.state.policy.webapps
              Row {
                required property var modelData
                width: content.width
                spacing: Style.space(8)
                Image { width: Style.space(32); height: width; anchors.verticalCenter: parent.verticalCenter; source: "file:///var/lib/omarchy-kids/icons/" + modelData.id + ".png"; fillMode: Image.PreserveAspectFit }
                Button { width: parent.width - removeButton.width - Style.space(48); text: modelData.name; focusable: true; onClicked: Quickshell.execDetached(["/usr/local/bin/omarchy-kids-webapp", modelData.id]) }
                Button { id: removeButton; text: "Remove"; focusable: true; onClicked: root.approve({action: "remove-webapp", id: modelData.id}) }
              }
            }
            Label { visible: !root.state.ready && !root.busy; width: parent.width; text: root.state.notice || "Checking setup…"; color: Color.accent }
            Row {
              width: parent.width
              Button { text: "Change parent PIN"; focusable: true; onClicked: { root.page = "change"; root.message = "" } }
            }
          }
          Column {
            visible: root.page === "webapp"
            width: parent.width
            spacing: Style.space(12)
            Label { text: "Approve a webapp"; font.pixelSize: Style.font.subtitle; font.bold: true }
            TextField { id: appName; width: parent.width; placeholderText: "App name"; maximumLength: 60 }
            TextField { id: appUrl; width: parent.width; placeholderText: "https://example.org"; maximumLength: 2048 }
            Label { width: parent.width; text: "Approval covers this website. Downloads are allowed; other websites need approval."; opacity: 0.65 }
            TextField { id: appOrigins; width: parent.width; placeholderText: "Extra content / login sites (optional)"; maximumLength: 4096 }
            Action { width: parent.width; text: "Continue with parent PIN"; onClicked: root.approve({action: "add-webapp", name: appName.text, url: appUrl.text, origins: appOrigins.text}) }
            Button { text: "← Back"; focusable: true; onClicked: root.page = "home" }
          }
          Column {
            visible: root.page === "change"
            width: parent.width
            spacing: Style.space(12)
            Label { text: "Change parent PIN"; font.pixelSize: Style.font.subtitle; font.bold: true }
            TextField { id: newPin; width: parent.width; password: true; placeholderText: "New PIN · 8–12 digits"; maximumLength: 12 }
            TextField { id: confirmPin; width: parent.width; password: true; placeholderText: "Repeat new PIN"; maximumLength: 12 }
            Action { width: parent.width; text: "Continue with current PIN"; onClicked: {
              if (!/^[0-9]{8,12}$/.test(newPin.text) || newPin.text !== confirmPin.text) { root.failed = true; root.message = "Use 8–12 digits and repeat the same PIN."; return }
              root.approve({action: "change-pin", new_pin: newPin.text, confirm: confirmPin.text})
            } }
            Button { text: "← Back"; focusable: true; onClicked: root.page = "home" }
          }
          Column {
            visible: root.page === "pin"
            width: parent.width
            spacing: Style.space(12)
            Label { text: "Parent approval"; font.pixelSize: Style.font.subtitle; font.bold: true }
            Label { width: parent.width; text: "Enter your PIN to approve this change." }
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
