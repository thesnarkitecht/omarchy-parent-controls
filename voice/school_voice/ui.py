from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
                             QProgressBar, QPushButton, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu, QCheckBox)

from .audio import Recorder, Transcriber
from .client import decide
from .desktop import Desktop
from .policy import catalog, load
from .routing import exact_action, normalize
from .wake import WakeListener, strip_wake
from .preferences import Preferences
from .session import is_locked
from .feedback import chime

STYLE = """
QWidget { background: #111b2b; color: #eff5fc; font-family: 'DejaVu Sans'; font-size: 14px; }
QLabel#eyebrow { color: #8fcabe; font-size: 11px; font-weight: 700; }
QLabel#title { font-size: 30px; font-weight: 700; }
QLabel#subtitle, QLabel#footnote { color: #9daec4; }
QFrame#card { background: #1a2940; border: 1px solid #30415a; border-radius: 18px; }
QFrame#card QLabel { background: transparent; }
QLabel#state { font-size: 21px; font-weight: 600; }
QLabel#transcript { color: #bce7df; font-size: 18px; }
QPushButton { background: #263850; padding: 12px 18px; border: 1px solid #41536c; border-radius: 10px; }
QPushButton:hover { background: #334b69; }
QPushButton:focus { border: 2px solid #a8e6d7; }
QPushButton#record { background: #bcebdc; color: #102d2a; border: none; font-weight: 700; font-size: 17px; padding: 18px; }
QPushButton#record:disabled { background: #41566b; color: #b6c5d2; }
QComboBox { background: #1a2940; border: 1px solid #41536c; border-radius: 8px; padding: 8px; }
QProgressBar { border: none; border-radius: 3px; background: #30415a; height: 6px; }
QProgressBar::chunk { background: #bcebdc; border-radius: 3px; }
"""


class Signals(QObject):
    completed = Signal(int, object, object)
    wake = Signal(int, str, object)


class VoiceWindow(QWidget):
    def __init__(self, policy_loader=load, desktop=None, recorder=None, transcriber=None, decider=decide,
                 wake_factory=WakeListener, preferences=None, session_check=is_locked, feedback=chime):
        super().__init__()
        self.loader = policy_loader
        self.desktop = desktop or Desktop(loader=policy_loader)
        self.recorder = recorder or Recorder()
        self.transcriber = transcriber
        self.decider = decider
        self.wake_factory = wake_factory
        self.preferences = preferences or Preferences()
        self.session_check = session_check
        self.feedback = feedback
        self.wake = None
        self.wake_generation = 0
        self.wake_recording = False
        self.from_wake = False
        self.wake_config = {"enabled": False}
        self.wake_paused = False
        self.muted = False
        self.voice_initialized = False
        self.wake_error = False
        self.cooldown_until = 0
        self.last_policy_check = 0
        self.shutting_down = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.signals = Signals()
        self.signals.completed.connect(self.complete, Qt.ConnectionType.QueuedConnection)
        self.signals.wake.connect(self.wake_event, Qt.ConnectionType.QueuedConnection)
        self.generation = 0
        self.busy = False
        self.recording = False
        self.target = {}
        self.mode = "command"
        self.started = 0
        self.callback = None
        self.setWindowTitle("School Voice")
        self.setMinimumSize(490, 710)
        self.resize(540, 730)
        self.setStyleSheet(STYLE)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(16)
        eyebrow = QLabel("SCHOOL VOICE  /  ON YOUR COMPUTER")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Say it. Do it.")
        title.setObjectName("title")
        subtitle = QLabel("Say “Hey Laya,” then tell me what to do.")
        self.subtitle = subtitle
        subtitle.setObjectName("subtitle")
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.mode_picker = QComboBox()
        self.mode_picker.addItems(["Control my computer", "Dictate and copy text"])
        self.mode_picker.setAccessibleName("Voice mode")
        self.mode_picker.currentIndexChanged.connect(self.change_mode)
        layout.addWidget(self.mode_picker)
        wake_row = QHBoxLayout()
        self.wake_toggle = QCheckBox("Wake word")
        self.wake_toggle.setEnabled(False)
        self.wake_toggle.toggled.connect(self.set_wake_enabled)
        self.mute_button = QPushButton("Mute microphone")
        self.mute_button.clicked.connect(self.toggle_mute)
        wake_row.addWidget(self.wake_toggle)
        wake_row.addStretch()
        wake_row.addWidget(self.mute_button)
        layout.addLayout(wake_row)
        self.mic_status = QLabel("Microphone off · hotkeys available")
        self.mic_status.setWordWrap(True)
        self.mic_status.setObjectName("subtitle")
        layout.addWidget(self.mic_status)
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(225)
        inside = QVBoxLayout(card)
        inside.setContentsMargins(22, 22, 22, 22)
        inside.setSpacing(15)
        self.state_label = QLabel("Ready when you are")
        self.state_label.setObjectName("state")
        self.state_label.setWordWrap(True)
        self.transcript = QLabel('Try “open math” or “turn the volume down.”')
        self.transcript.setObjectName("transcript")
        self.transcript.setWordWrap(True)
        self.transcript.setTextFormat(Qt.TextFormat.PlainText)
        self.transcript.setMinimumHeight(70)
        self.detail = QLabel("Your microphone is off.")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.meter = QProgressBar()
        self.meter.setFixedHeight(6)
        self.meter.setRange(0, 100)
        self.meter.setValue(0)
        self.meter.setTextVisible(False)
        for widget in (self.state_label, self.transcript, self.meter, self.detail):
            inside.addWidget(widget)
        layout.addWidget(card, 1)
        self.record = QPushButton("●  Start speaking")
        self.record.setObjectName("record")
        self.record.clicked.connect(lambda: self.toggle(self.mode))
        layout.addWidget(self.record)
        controls = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)
        foot = QLabel("SUPER + ALT + V  Control  ·  SUPER + ALT + D  Dictate\nSUPER + ALT + M  Mute / resume microphone\nAudio stays here. Only commands are sent to Laya.")
        foot.setObjectName("footnote")
        foot.setWordWrap(True)
        layout.addWidget(foot)
        QShortcut(QKeySequence("Escape"), self, activated=self.cancel)
        self.tray = QSystemTrayIcon(self)
        menu = QMenu(self)
        menu.addAction("Open School Voice", self.show)
        menu.addAction("Mute / resume microphone", self.toggle_mute)
        menu.addAction("Quit School Voice", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.update_mic_status("Microphone off", "#8c9bae")
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def initialize_voice(self):
        saved = self.preferences.read()
        self.muted, self.wake_paused = saved["muted"], saved["wake_paused"]
        self.voice_initialized = True
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.sync_wake()

    def update_mic_status(self, text, color="#8fcabe"):
        self.mic_status.setText(text)
        self.tray.setToolTip("School Voice — " + text)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(11, 4, 10, 17, 5, 5)
        painter.drawRoundedRect(7, 17, 18, 4, 2, 2)
        painter.drawRect(14, 20, 4, 6)
        painter.drawRoundedRect(9, 26, 14, 3, 1, 1)
        painter.end()
        self.tray.setIcon(QIcon(pixmap))

    def stop_wake(self):
        self.wake_generation += 1
        listener, self.wake = self.wake, None
        if listener:
            listener.stop()
        self.wake_recording = False

    def sync_wake(self):
        if not self.voice_initialized or self.shutting_down:
            return
        try:
            policy = self.loader()
            config = policy.get("wake_word", {"enabled": False})
        except Exception as error:
            self.cancel()
            self.update_mic_status("Microphone off · parent policy unavailable", "#8c9bae")
            self.set_status("Voice is unavailable", str(error))
            return
        if config != self.wake_config:
            self.cancel()
            self.wake_config = dict(config)
            self.wake_error = False
        self.wake_toggle.blockSignals(True)
        self.wake_toggle.setEnabled(config["enabled"])
        self.wake_toggle.setChecked(config["enabled"] and not self.wake_paused)
        self.wake_toggle.setText('Wake word: “' + config.get("phrase", "Hey Laya") + '”')
        self.wake_toggle.blockSignals(False)
        self.subtitle.setText('Say “' + config.get("phrase", "Hey Laya") + ',” then tell me what to do.' if config["enabled"] else "Press the shortcut, speak, then press it again.")
        self.mute_button.setText("Resume microphone" if self.muted or self.wake_error else "Mute microphone")
        self.record.setEnabled(not self.muted and not self.busy)
        if self.muted or self.session_check():
            if self.wake or self.recording or self.busy:
                self.cancel()
            self.update_mic_status("Microphone muted" if self.muted else "Microphone off · screen locked or session unavailable", "#8c9bae")
            return
        if not config["enabled"] or self.wake_paused:
            if self.wake:
                self.stop_wake()
            if not self.recording:
                self.update_mic_status("Microphone off · hotkeys available", "#8c9bae")
            return
        if self.wake_error or self.busy or self.recording or self.wake or time.monotonic() < self.cooldown_until:
            return
        self.wake_generation += 1
        generation = self.wake_generation
        self.wake = self.wake_factory(config, lambda kind, value: self.signals.wake.emit(generation, kind, value))
        self.update_mic_status("Starting local wake-word listening…", "#d8c381")
        self.wake.start()

    def set_wake_enabled(self, enabled):
        self.wake_paused = not enabled
        self.cancel()
        self.save_preferences()
        self.sync_wake()

    def save_preferences(self):
        try:
            self.preferences.save(self.muted, self.wake_paused)
        except OSError:
            self.set_status("Setting applies for this session", "Could not save the microphone preference for next login.")

    def toggle_mute(self):
        if self.wake_error:
            self.wake_error = False
            self.muted = False
        else:
            self.muted = not self.muted
        self.cancel()
        self.save_preferences()
        self.sync_wake()

    def wake_event(self, generation, kind, payload):
        if generation != self.wake_generation or self.muted or self.shutting_down:
            return
        if kind == "armed":
            self.update_mic_status('Microphone on · waiting for “' + self.wake_config["phrase"] + '”')
            self.set_status("Ready when you are", "Wake-word detection runs here. Say the wake phrase, then your command.")
            if not self.transcript.text():
                self.transcript.setText('Try “open math” or “turn the volume down.”')
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.show()
        elif kind == "awake":
            if self.busy or self.session_check():
                self.cancel()
                return
            self.from_wake = True
            self.mode_picker.blockSignals(True)
            self.mode_picker.setCurrentIndex(0)
            self.mode_picker.blockSignals(False)
            self.mode = "command"
            current = self.desktop.active()
            if current.get("class") not in ("school-voice", "School Voice", "school_voice"):
                self.target = current
            self.recording = self.wake_recording = True
            self.started = time.monotonic()
            self.mode_picker.setEnabled(False)
            self.record.setText("■  Finish speaking")
            self.update_mic_status("Microphone on · listening to your command", "#ef9a94")
            self.set_status("I'm listening", "Speak your command. I'll act when you finish.")
            self.show()
            self.feedback("ready")
        elif kind == "audio":
            self.wake = None
            self.recording = self.wake_recording = False
            self.from_wake = True
            self.transcribe_samples(payload)
        elif kind in ("timeout", "error"):
            self.wake = None
            self.recording = self.wake_recording = False
            self.record.setText("●  Start speaking")
            self.mode_picker.setEnabled(True)
            self.cooldown_until = time.monotonic() + 2
            self.wake_error = kind == "error"
            self.update_mic_status("Microphone off" + (" · wake listening needs attention" if self.wake_error else " · restarting wake listening"), "#8c9bae")
            self.set_status("Couldn't hear a command" if kind == "timeout" else "Wake listening stopped", payload or "Nothing changed. Say the wake phrase again when you're ready.")
            if kind == "error":
                self.feedback("error")
                self.show()

    def quit_app(self):
        self.shutdown()
        QApplication.quit()

    def change_mode(self, index):
        self.cancel()
        self.mode = "dictate" if index else "command"

    def set_status(self, heading, detail):
        self.state_label.setText(heading)
        self.detail.setText(detail)

    def tick(self):
        if time.monotonic() - self.last_policy_check >= 2:
            self.last_policy_check = time.monotonic()
            self.sync_wake()
        if self.recording:
            elapsed = time.monotonic() - self.started
            source = self.wake if self.wake_recording and self.wake else self.recorder
            self.meter.setValue(min(100, int(source.level * 700)))
            self.detail.setText(f"Listening · {elapsed:.0f} / 15 seconds · " + ("finishes when you stop speaking" if self.wake_recording else "press the shortcut again to finish"))
            if elapsed >= 15 and not self.wake_recording:
                self.finish_recording()

    def toggle(self, mode="command"):
        if self.muted or (self.voice_initialized and self.session_check()):
            self.show()
            self.set_status("Microphone is off", "Resume the microphone or unlock your session to speak.")
            return
        if self.recording:
            self.finish_recording()
            return
        if self.busy:
            self.show()
            self.set_status("Finishing your request", "You can cancel; canceled requests never take an action.")
            return
        if self.mode != mode:
            self.mode_picker.setCurrentIndex(1 if mode == "dictate" else 0)
        self.mode = mode
        try:
            self.stop_wake()
            self.from_wake = False
            policy = self.loader()
            if self.transcriber is None:
                vocabulary = ", ".join(alias for app in policy["apps"].values() for alias in [app["label"], *app["aliases"]])
                self.transcriber = Transcriber(policy["whisper_model"], vocabulary=vocabulary)
            current = self.desktop.active()
            if current.get("class") not in ("school-voice", "School Voice", "school_voice"):
                self.target = current
            self.recorder.start()
            self.recording = True
            self.started = time.monotonic()
            self.mode_picker.setEnabled(False)
            self.record.setText("■  Finish speaking")
            self.set_status("I'm listening", "Speak naturally. Press again when you're done.")
            self.update_mic_status("Microphone on · recording", "#ef9a94")
            self.show()
        except Exception as e:
            self.recorder.cancel()
            self.show()
            self.set_status("Couldn't start listening", str(e))

    def finish_recording(self):
        if self.wake_recording and self.wake:
            self.wake.finish()
            return
        self.recording = False
        self.meter.setValue(0)
        self.record.setText("●  Start speaking")
        self.mode_picker.setEnabled(True)
        try:
            samples = self.recorder.stop()
        except Exception as e:
            self.set_status("Please try again", str(e))
            return
        self.transcribe_samples(samples)

    def transcribe_samples(self, samples):
        self.record.setText("●  Start speaking")
        self.meter.setValue(0)
        try:
            policy = self.loader()
            if self.transcriber is None:
                vocabulary = ", ".join(alias for app in policy["apps"].values() for alias in [app["label"], *app["aliases"]])
                self.transcriber = Transcriber(policy["whisper_model"], vocabulary=vocabulary + ", " + self.wake_config.get("phrase", "Hey Laya"))
        except Exception as error:
            self.set_status("Nothing changed", str(error))
            return
        self.update_mic_status("Microphone off · processing command", "#d8c381")
        self.set_status("Writing down your words…", "Transcription runs on this computer. The microphone is off.")
        command_mode = self.mode == "command"
        self.submit(lambda: self.transcriber.transcribe(samples, command_mode=command_mode), self.handle_text)

    def submit(self, function, callback):
        self.busy = True
        self.callback = callback
        self.record.setEnabled(False)
        self.mode_picker.setEnabled(False)
        generation = self.generation
        future = self.pool.submit(function)
        def done(f):
            try:
                self.signals.completed.emit(generation, f.result(), None)
            except Exception as error:
                self.signals.completed.emit(generation, None, str(error))
        future.add_done_callback(done)

    def complete(self, generation, result, error):
        self.busy = False
        self.record.setEnabled(not self.muted)
        self.mode_picker.setEnabled(True)
        if generation != self.generation:
            return
        if error:
            self.set_status("Couldn't finish that", error)
            self.feedback("error")
            self.cooldown_until = time.monotonic() + 2
            return
        self.callback(result)

    def handle_text(self, text):
        if self.from_wake:
            text = strip_wake(text, self.wake_config.get("phrase", "Hey Laya"))
        self.transcript.setText(text)
        try:
            policy = self.loader()
            if not text:
                self.set_status("Ready for a command", "Say the wake phrase, then what you'd like to do.")
                return
            if self.voice_initialized and self.session_check():
                self.cancel()
                return
            if self.mode == "command" and normalize(text) in ("stop listening", "mute microphone", "mute the microphone", "go to sleep"):
                self.muted = True
                self.cancel()
                self.save_preferences()
                self.sync_wake()
                return
            if self.from_wake:
                import re
                match = re.match(r"^(?:dictate|write this|take a note)\b[\s,:-]*(.+)", text, re.I)
                if match:
                    QApplication.clipboard().setText(match.group(1))
                    self.set_status("Copied your words", "Paste into your document. Nothing was sent to Laya.")
                    self.cooldown_until = time.monotonic() + 2
                    return
            if self.mode == "dictate":
                QApplication.clipboard().setText(text)
                self.set_status("Copied your words", "Paste into your document when you're ready. Nothing was sent to Laya.")
                return
            if normalize(text) in ("cancel", "stop", "no", "never mind"):
                self.cancel()
                return
            action = exact_action(text, policy)
            if action:
                self.propose(action)
            else:
                self.set_status("Asking Laya…", "Only this sentence and the approved action list go to the home server.")
                self.submit(lambda: self.decider(text, policy), self.propose)
        except Exception as e:
            self.set_status("Nothing changed", str(e))

    def propose(self, action):
        try:
            policy = self.loader()
            if action == "unknown":
                self.set_status("Try a different request", "I can open approved apps, switch windows or desktops, and control sound.")
                self.feedback("error")
                return
            if action not in catalog(policy):
                raise ValueError("That action is not approved")
            self.perform(action, self.target)
        except Exception as e:
            self.set_status("Nothing changed", str(e))

    def perform(self, action, target):
        try:
            if self.muted or (self.voice_initialized and self.session_check()):
                raise ValueError("Microphone muted or session locked; request canceled")
            result = self.desktop.execute(action, target)
            self.set_status("Done", result)
            self.feedback("done")
            self.cooldown_until = time.monotonic() + 2
            # Hide after successful navigation so the target app remains usable.
            generation = self.generation
            QTimer.singleShot(1600, lambda: self.hide() if generation == self.generation and not self.recording and not self.busy and (QSystemTrayIcon.isSystemTrayAvailable() or not self.wake_config.get("enabled")) else None)
        except Exception as e:
            self.set_status("Couldn't do that", str(e))

    def cancel(self):
        self.generation += 1
        self.stop_wake()
        self.recorder.cancel()
        self.recording = False
        self.record.setText("●  Start speaking")
        self.mode_picker.setEnabled(not self.busy)
        self.record.setEnabled(not self.busy and not self.muted)
        self.meter.setValue(0)
        self.transcript.setText("")
        self.cooldown_until = time.monotonic() + 2
        self.update_mic_status("Microphone muted" if self.muted else "Microphone off", "#8c9bae")
        self.set_status("Nothing changed", "Your microphone is muted." if self.muted else "Canceled. Wake listening resumes shortly if enabled.")

    def closeEvent(self, event: QCloseEvent):
        self.cancel()
        if QSystemTrayIcon.isSystemTrayAvailable() or not self.wake_config.get("enabled") or self.muted:
            self.hide()
        event.ignore()

    def shutdown(self):
        self.shutting_down = True
        self.timer.stop()
        self.cancel()
        self.tray.hide()
        self.pool.shutdown(wait=False, cancel_futures=True)
