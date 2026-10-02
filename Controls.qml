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
            Label { width: parent.width; visible: !!root.state.family.screen_time; text: root.state.family.screen_time ? "Screen time today: " + Math.floor(root.state.family.screen_time.today_seconds / 60) + " min · unlocked desktop time" : "" }
            Label { width: parent.width; visible: !!root.state.family.access && root.state.family.access.paused; text: "Computer paused by a parent"; color: Color.accent }
            Action { width: parent.width; text: "Pair parent phone · get code"; onClicked: root.call({action:"open-pairing"}) }
            Label { width: parent.width; text: "Scan once in Parent Pocket. The setup window asks for your parent PIN and guides the private connection."; opacity: 0.65 }
            Action { width: parent.width; text: "Voice, videos & requests"; onClicked: { root.page = "family"; voicePhrase.text = root.state.family.voice.phrase } }
            Action { width: parent.width; text: "Little Screen · watch or ask a parent"; onClicked: { Quickshell.execDetached(["/usr/local/bin/omarchy-kids-videos"]); root.dismiss() } }
            Row {
              width: parent.width
              Label { width: parent.width - addButton.width; text: "Approved webapps"; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
              Button { id: addButton; text: "+ Add"; focusable: true; onClicked: { root.editingId = ""; root.page = "webapp"; root.message = ""; appName.text = ""; appUrl.text = ""; appOrigins.text = ""; appUrl.forceActiveFocus() } }
            }
            Label { visible: root.state.policy.webapps.length === 0; width: parent.width; text: "None yet. Only websites you approve will appear."; opacity: 0.65 }
            Repeater {
              model: root.state.policy.webapps
              Column {
                required property var modelData
                width: content.width
                spacing: Style.space(8)
                Row {
                width: parent.width
                spacing: Style.space(8)
                Image { width: Style.space(32); height: width; anchors.verticalCenter: parent.verticalCenter; source: "file:///var/lib/omarchy-kids/icons/" + modelData.id + ".png"; fillMode: Image.PreserveAspectFit }
                Button { width: parent.width - editButton.width - Style.space(48); text: modelData.name; focusable: true; onClicked: Quickshell.execDetached(["/usr/local/bin/omarchy-kids-webapp", modelData.id]) }
                Button { id: editButton; text: "Edit"; focusable: true; onClicked: {
                  root.editingId = modelData.id; appName.text = modelData.name; appUrl.text = modelData.url;
                  appOrigins.text = modelData.origins.join(", "); root.page = "webapp"; root.message = ""
                } }
                }
                Row {
                  spacing: Style.space(12)
                  Button { text: "Clear data…"; focusable: true; onClicked: root.approve({action: "clear-webapp-data", id: modelData.id}) }
                  Button { text: "Remove"; focusable: true; onClicked: root.approve({action: "remove-webapp", id: modelData.id}) }
                }
              }
            }
            Label { visible: !root.state.ready && !root.busy; width: parent.width; text: root.state.notice || "Checking setup…"; color: Color.accent }
            Row {
              width: parent.width
              Button { text: "Change parent PIN"; focusable: true; onClicked: { root.page = "change"; root.message = "" } }
              Button { text: "Parent tools"; focusable: true; onClicked: { root.page = "tools"; root.message = "" } }
            }
          }
          Column {
            visible: root.page === "family"
            width: parent.width
            spacing: Style.space(12)
            Label { text: "Voice & Little Screen"; font.pixelSize: Style.font.subtitle; font.bold: true }
            Label { width: parent.width; text: root.state.family.voice.enabled ? "Voice control is on. Approved commands happen without confirmation." : "Voice control is off." }
            Label { visible: !root.state.family.voice_installed; width: parent.width; text: "Voice support needs to be installed with this computer’s Laya pairing first." }
            TextField { id: voicePhrase; width: parent.width; placeholderText: "Hey Laya"; maximumLength: 60 }
            Action { width: parent.width; text: root.state.family.voice.enabled ? "Turn voice control off" : "Turn voice control on"; enabled: !root.busy && root.state.family.voice_installed; onClicked: root.approve({action:"family-change",operation:"set-voice",fields:{enabled:!root.state.family.voice.enabled,wake_enabled:root.state.family.voice.wake_enabled,phrase:voicePhrase.text}}) }
            Action { width: parent.width; text: root.state.family.voice.wake_enabled ? "Use hotkeys only" : "Listen for the wake word"; enabled: !root.busy && root.state.family.voice_installed; onClicked: root.approve({action:"family-change",operation:"set-voice",fields:{enabled:root.state.family.voice.enabled,wake_enabled:!root.state.family.voice.wake_enabled,phrase:voicePhrase.text}}) }
            Action { width: parent.width; text: "Save wake phrase"; enabled: !root.busy && root.state.family.voice_installed; onClicked: root.approve({action:"family-change",operation:"set-voice",fields:{enabled:root.state.family.voice.enabled,wake_enabled:root.state.family.voice.wake_enabled,phrase:voicePhrase.text}}) }
            Label { text: "Requests"; font.bold: true }
            Repeater {
              model: root.state.family.requests.filter(function(r) { return r.status === "pending" })
              Column {
                required property var modelData
                width: content.width
                spacing: Style.space(6)
                Label { width: parent.width; text: modelData.name + " · " + modelData.kind; font.bold: true }
                Label { width: parent.width; text: modelData.target + (modelData.reason ? "\n" + modelData.reason : "") }
                Row {
                  spacing: Style.space(12)
                  Button { text: "Allow"; enabled: !root.busy; onClicked: root.approve({action:"family-change",operation:"review",fields:{request_id:modelData.id,allow:true}}) }
                  Button { text: "Not now"; enabled: !root.busy; onClicked: root.approve({action:"family-change",operation:"review",fields:{request_id:modelData.id,allow:false}}) }
                }
              }
            }
            Label { text: "Only videos you pick"; font.bold: true }
            Label { width: parent.width; text: "Approve individual videos. No channels, playlists or recommendations." }
            TextField { id: videoUrl; width: parent.width; placeholderText: "YouTube video link"; maximumLength: 2048 }
            TextField { id: videoName; width: parent.width; placeholderText: "Video title · optional"; maximumLength: 80 }
            Action { width: parent.width; text: "Add to Little Screen"; onClicked: root.approve({action:"family-change",operation:"add-video",fields:{name:videoName.text,url:videoUrl.text}}) }
            Repeater {
              model: root.state.family.videos
              Row {
                required property var modelData
                width: content.width
                Label { width: parent.width - removeVideo.width; text: modelData.name }
                Button { id: removeVideo; text: "Remove"; enabled: !root.busy; onClicked: root.approve({action:"family-change",operation:"remove-video",fields:{video_id:modelData.id}}) }
              }
            }
            Button { text: "← Back"; onClicked: root.page = "home" }
          }
          Column {
            visible: root.page === "webapp"
            width: parent.width
            spacing: Style.space(12)
            Label { text: root.editingId ? "Edit webapp" : "Approve a webapp"; font.pixelSize: Style.font.subtitle; font.bold: true }
            TextField { id: appUrl; width: parent.width; placeholderText: "Paste an app or website URL"; maximumLength: 2048 }
            TextField { id: appName; width: parent.width; placeholderText: "App name · optional"; maximumLength: 60 }
            Label { width: parent.width; text: "Links can open approved websites. Add related or login sites below, separated by commas. For x.ai → Grok, include https://grok.com."; opacity: 0.65 }
            TextField { id: appOrigins; width: parent.width; placeholderText: "Related sites · https://example.org"; maximumLength: 4096 }
            Action { width: parent.width; text: "Continue with parent PIN"; onClicked: root.approve({action: root.editingId ? "edit-webapp" : "add-webapp", id: root.editingId, name: appName.text, url: appUrl.text, origins: appOrigins.text}) }
            Button { text: "← Back"; focusable: true; onClicked: root.page = "home" }
          }
          Column {
            visible: root.page === "tools"
            width: parent.width
            spacing: Style.space(12)
            Label { text: "Parent tools"; font.pixelSize: Style.font.subtitle; font.bold: true }
            Label { width: parent.width; text: "Turn controlled mode off first. These tools use Omarchy’s normal setup screens; nothing is installed until you choose it." }
            Action { width: parent.width; text: "Choose default agent…"; enabled: !root.busy && !root.state.active; onClicked: root.approve({action: "parent-tool", tool: "agent"}) }
            Action { width: parent.width; text: "Install or repair Hermes…"; enabled: !root.busy && !root.state.active; onClicked: root.approve({action: "parent-tool", tool: "hermes-repair"}) }
            Action { width: parent.width; text: "Set up Windows…"; enabled: !root.busy && !root.state.active; onClicked: root.approve({action: "parent-tool", tool: "windows-install"}) }
            Action { width: parent.width; text: "Open Windows…"; enabled: !root.busy && !root.state.active; onClicked: root.approve({action: "parent-tool", tool: "windows-launch"}) }
            Label { width: parent.width; text: "Windows apps and browsers need their own controls inside Windows. Shut Windows down before turning Omarchy controls back on."; opacity: 0.65 }
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
