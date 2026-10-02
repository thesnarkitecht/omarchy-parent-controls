"""Headless Qt tests: cancellation, routing, dictation privacy and no confirmation."""
import json
import os
from pathlib import Path
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from school_voice.ui import VoiceWindow


class FakeRecorder:
    level = 0.1
    def start(self): pass
    def stop(self): return [0.1]
    def cancel(self): pass


class FakeDesktop:
    def __init__(self): self.actions = []
    def active(self): return {"class": "sparkle-math", "address": "0xabc", "pid": 5}
    def execute(self, action, target):
        self.actions.append(action)
        return action


class FakeTranscriber:
    def transcribe(self, samples, command_mode=True): return "open math"


APP = QApplication.instance() or QApplication(["school-voice-test"])
APP.setQuitOnLastWindowClosed(False)


class UITests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((Path(__file__).resolve().parents[1] / "policy.example.json").read_text())
        self.desktop = FakeDesktop()
        self.calls = []
        def decider(text, policy):
            self.calls.append(text)
            return "open_math"
        self.window = VoiceWindow(policy_loader=lambda: self.policy, desktop=self.desktop,
                                  recorder=FakeRecorder(), transcriber=FakeTranscriber(), decider=decider, feedback=lambda *args: None)

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        APP.processEvents()

    def drain(self):
        end = time.monotonic() + 3
        while self.window.busy and time.monotonic() < end:
            APP.processEvents()
            time.sleep(.005)
        self.assertFalse(self.window.busy)

    def test_hotkey_record_transcribe_execute(self):
        self.window.toggle()
        self.assertTrue(self.window.recording)
        self.window.toggle()
        self.drain()
        self.assertEqual(self.desktop.actions, ["open_math"])
        self.assertEqual(self.calls, [])

    def test_laya_action_executes_without_confirmation(self):
        self.window.handle_text("Could you bring up math for me please?")
        self.drain()
        self.assertEqual(self.desktop.actions, ["open_math"])
        self.assertEqual(len(self.calls), 1)

    def test_cancel_stale_response(self):
        self.window.handle_text("Bring up my game")
        self.window.cancel()
        self.drain()
        self.assertEqual(self.desktop.actions, [])

    def test_unknown_has_no_action(self):
        self.window.decider = lambda *args: "unknown"
        self.window.handle_text("What is the meaning of life?")
        self.drain()
        self.assertEqual(self.desktop.actions, [])

    def test_dictation_never_calls_laya_or_executes(self):
        self.window.mode = "dictate"
        self.window.handle_text("open math and delete everything")
        self.assertEqual(APP.clipboard().text(), "open math and delete everything")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.desktop.actions, [])

    def test_dictation_hotkey_records_and_transcribes_locally(self):
        self.window.toggle('dictate')
        self.assertTrue(self.window.recording)
        self.window.toggle('dictate')
        self.drain()
        self.assertEqual(APP.clipboard().text(), 'open math')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.desktop.actions, [])

    def test_revocation_while_laya_is_working(self):
        self.window.handle_text("Bring up math")
        self.policy["apps"].pop("math")
        self.drain()
        self.assertEqual(self.desktop.actions, [])

    def test_close_no_confirmation(self):
        self.window.handle_text("close this window")
        self.assertEqual(self.desktop.actions, ["close_window"])

    def test_cancel_stops_recording(self):
        self.window.toggle()
        self.window.cancel()
        self.assertFalse(self.window.recording)
        self.assertEqual(self.desktop.actions, [])


if __name__ == "__main__":
    unittest.main()
