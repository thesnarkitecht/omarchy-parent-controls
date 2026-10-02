import json
import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from school_voice.wake import WakeCapture, strip_wake
from school_voice.preferences import Preferences
from school_voice.policy import validate
from school_voice.ui import VoiceWindow
from test_ui import FakeDesktop, FakeRecorder, FakeTranscriber


class CaptureTests(unittest.TestCase):
    def test_ordinary_speech_is_never_captured(self):
        c = WakeCapture()
        for _ in range(1000):
            self.assertIsNone(c.feed(b"frame", speech=True))
        self.assertEqual(len(c.pre), 25)
        self.assertEqual(c.frames, [])

    def test_command_ends_on_silence(self):
        c = WakeCapture()
        self.assertEqual(c.feed(b"wake", keyword=True)[0], "awake")
        for _ in range(20): self.assertIsNone(c.feed(b"speech", speech=True))
        result = None
        for _ in range(25):
            event = c.feed(b"silence")
            if event: result = event
        self.assertEqual(result[0], "audio")
        self.assertIn(b"wake", result[1])
        self.assertEqual(c.state, "done")
        self.assertIsNone(c.feed(b"more", keyword=True, speech=True))

    def test_wake_without_command_times_out(self):
        c = WakeCapture()
        c.feed(b"wake", keyword=True)
        events = [c.feed(b"silence") for _ in range(102)]
        self.assertTrue(any(e and e[0] == "timeout" for e in events))
        self.assertEqual(c.frames, [])

    def test_long_command_is_discarded(self):
        c = WakeCapture()
        c.feed(b"wake", keyword=True)
        events = [c.feed(b"speech", speech=True) for _ in range(380)]
        self.assertTrue(any(e and e[0] == "timeout" for e in events))
        self.assertFalse(any(e and e[0] == "audio" for e in events))
        self.assertEqual(c.frames, [])

    def test_cancel_drops_all_buffered_audio(self):
        c = WakeCapture()
        c.feed(b"wake", keyword=True)
        c.feed(b"speech", speech=True)
        c.cancel()
        self.assertEqual(c.frames, [])
        self.assertEqual(list(c.pre), [])

    def test_prefix_removal_does_not_change_other_text(self):
        self.assertEqual(strip_wake("Hey Laya, open math", "Hey Laya"), "open math")
        self.assertEqual(strip_wake("Hey Leia, open math", "Hey Laya"), "open math")
        self.assertEqual(strip_wake("Hey, Laya, stop listening", "Hey Laya"), "stop listening")
        self.assertEqual(strip_wake("say hey laya later", "Hey Laya"), "say hey laya later")
        self.assertEqual(strip_wake("Hey Layaway open math", "Hey Laya"), "Hey Layaway open math")

    def test_mute_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "preferences.json"
            Preferences(path).save(True, False)
            self.assertTrue(Preferences(path).read()["muted"])
            path.write_text("invalid")
            self.assertTrue(Preferences(path).read()["muted"])

    def test_invalid_wake_policy(self):
        policy = json.loads((Path(__file__).resolve().parents[1] / "policy.example.json").read_text())
        for key, value in [("phrase", "hey;exec()"), ("phrase", "hello"), ("threshold", 2), ("silence_seconds", 0), ("model_dir", "/tmp/model")]:
            modified = {**policy, "wake_word": {**policy["wake_word"], key: value}}
            with self.subTest(key=key), self.assertRaises(ValueError): validate(modified)


class MemoryPreferences:
    def __init__(self, muted=False): self.data = {"muted": muted, "wake_paused": False}
    def read(self): return dict(self.data)
    def save(self, muted, wake_paused): self.data = {"muted": muted, "wake_paused": wake_paused}


class FakeWake:
    level = .1
    def __init__(self, config, callback): self.callback, self.stopped = callback, False
    def start(self): pass
    def stop(self): self.stopped = True
    def finish(self): pass


APP = QApplication.instance() or QApplication(["wake-tests"])
APP.setQuitOnLastWindowClosed(False)


class WakeUITests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((Path(__file__).resolve().parents[1] / "policy.example.json").read_text())
        self.locked = False
        self.desktop = FakeDesktop()
        self.prefs = MemoryPreferences()
        self.window = VoiceWindow(policy_loader=lambda: self.policy, desktop=self.desktop,
            recorder=FakeRecorder(), transcriber=FakeTranscriber(), decider=lambda *args: "open_math",
            wake_factory=FakeWake, preferences=self.prefs, session_check=lambda: self.locked, feedback=lambda *args: None)
        self.window.initialize_voice()
        self.window.cooldown_until = 0
        self.window.sync_wake()

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        APP.processEvents()

    def drain(self):
        end = time.monotonic() + 2
        while self.window.busy and time.monotonic() < end:
            APP.processEvents()
            time.sleep(.005)

    def test_wake_starts_and_dispatches_without_confirmation(self):
        self.window.wake_event(self.window.wake_generation, "awake", None)
        self.assertTrue(self.window.recording)
        self.window.wake_event(self.window.wake_generation, "audio", [0.1])
        self.drain()
        self.assertEqual(self.desktop.actions, ["open_math"])

    def test_mute_closes_listener_and_blocks_hotkey(self):
        listener = self.window.wake
        self.window.toggle_mute()
        self.assertTrue(listener.stopped)
        self.assertTrue(self.prefs.data["muted"])
        self.window.toggle()
        self.assertFalse(self.window.recording)
        self.assertIsNone(self.window.wake)

    def test_stale_wake_result_cannot_act_after_mute(self):
        generation = self.window.wake_generation
        self.window.toggle_mute()
        self.window.wake_event(generation, "audio", [0.1])
        self.assertFalse(self.window.busy)
        self.assertEqual(self.desktop.actions, [])

    def test_lock_cancels_capture(self):
        listener = self.window.wake
        self.window.wake_event(self.window.wake_generation, "awake", None)
        self.locked = True
        self.window.sync_wake()
        self.assertTrue(listener.stopped)
        self.assertFalse(self.window.recording)
        self.assertEqual(self.desktop.actions, [])

    def test_lock_while_laya_is_working(self):
        self.window.handle_text("Could you bring up math?")
        self.locked = True
        self.drain()
        self.assertEqual(self.desktop.actions, [])

    def test_parent_disabling_wake_closes_mic(self):
        listener = self.window.wake
        self.policy["wake_word"]["enabled"] = False
        self.window.sync_wake()
        self.assertTrue(listener.stopped)
        self.assertIsNone(self.window.wake)

    def test_voice_sleep_mutes(self):
        self.window.from_wake = True
        self.window.handle_text("Hey Laya, stop listening")
        self.assertTrue(self.window.muted)
        self.assertTrue(self.prefs.data["muted"])

    def test_hands_free_dictation_never_executes(self):
        self.window.from_wake = True
        self.window.handle_text("Hey Laya, dictate open math")
        self.assertEqual(APP.clipboard().text(), "open math")
        self.assertEqual(self.desktop.actions, [])
        self.assertFalse(self.window.busy)

    def test_dictation_does_not_treat_text_as_a_mute_command(self):
        self.window.mode = "dictate"
        self.window.handle_text("go to sleep")
        self.assertFalse(self.window.muted)
        self.assertEqual(APP.clipboard().text(), "go to sleep")

    def test_switch_from_dictation_to_wake_preserves_capture(self):
        self.window.mode_picker.blockSignals(True)
        self.window.mode_picker.setCurrentIndex(1)
        self.window.mode_picker.blockSignals(False)
        listener = self.window.wake
        self.window.wake_event(self.window.wake_generation, "awake", None)
        self.assertFalse(listener.stopped)
        self.assertTrue(self.window.recording)

    def test_shutdown_releases_listener(self):
        listener = self.window.wake
        self.window.shutdown()
        self.assertTrue(listener.stopped)
        self.window.sync_wake()
        self.assertIsNone(self.window.wake)


if __name__ == "__main__": unittest.main()
