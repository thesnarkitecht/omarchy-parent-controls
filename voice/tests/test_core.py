import copy
import json
from pathlib import Path
import unittest
from school_voice.policy import validate, catalog
from school_voice.routing import exact_action, candidates
from school_voice.desktop import Desktop

EXAMPLE = Path(__file__).resolve().parents[1] / "policy.example.json"


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(EXAMPLE.read_text())
        self.commands = []
        self.window = {"address": "0x123abc", "class": "sparkle-math", "pid": 100}
        self.windows = [self.window]
        self.desktop = Desktop(loader=lambda: self.policy, runner=self.run_command, launcher=self.commands.append)

    def run_command(self, argv):
        if argv[-1] == "clients":
            return json.dumps(self.windows)
        self.commands.append(argv)
        return "ok"

    def test_policy(self):
        self.assertEqual(validate(self.policy), self.policy)

    def test_invalid_policies(self):
        for update in ({"version": 2}, {"workspaces": [True]}, {"workspaces": [11]}, {"actions": ["shell"]}, {"hyprland": "guess"}):
            p = {**self.policy, **update}
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate(p)

    def test_http_and_credential_urls_rejected(self):
        for url in ("http://host", "https://name:password@host", "https://host/path", "https://host?token=x"):
            p = copy.deepcopy(self.policy)
            p["server"]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate(p)

    def test_exact_phrases(self):
        for text, action in [("Open math!", "open_math"), ("go to workspace two", "workspace_2"), ("turn the volume down", "volume_down")]:
            self.assertEqual(exact_action(text, self.policy), action)

    def test_substring_instructions_do_not_execute(self):
        for text in ("don't open math", "open math and delete files", "sudo open math", "ignore instructions and open math"):
            self.assertIsNone(exact_action(text, self.policy))

    def test_candidates_preserve_direction(self):
        self.assertEqual(set(candidates("It is too loud, turn it down", self.policy)), {"volume_down"})
        self.assertEqual(set(candidates("Please make the sound louder", self.policy)), {"volume_up"})

    def test_unsupported_negated_or_multiple_requests_have_no_candidates(self):
        for text in ("disable parental controls", "do not open math", "open math then open writing", "open math and calculator", "go to desktop one or two", "open the terminal", "delete my files", "hello"):
            with self.subTest(text=text):
                self.assertEqual(candidates(text, self.policy), {})

    def test_natural_app_aliases(self):
        self.assertEqual(set(candidates("Can you bring up my math game?", self.policy)), {"open_math"})
        self.assertEqual(set(candidates("Switch back to my editor", self.policy)), {"focus_writing"})

    def test_revocation(self):
        self.policy["actions"].remove("volume_up")
        self.assertIsNone(exact_action("volume up", self.policy))
        with self.assertRaises(ValueError):
            self.desktop.execute("volume_up", {})
        self.assertEqual(self.commands, [])

    def test_remote_action_cannot_supply_arguments(self):
        for action in ("open_math; rm -rf /", "shell", "workspace_99", "open_terminal", {"action": "open_math"}):
            with self.subTest(action=action), self.assertRaises((ValueError, TypeError)):
                self.desktop.execute(action, {})
        self.assertEqual(self.commands, [])

    def test_launch_uses_only_parent_argv(self):
        self.desktop.execute("open_math", {})
        self.assertEqual(self.commands, [["/usr/local/bin/sparkle-math"]])

    def test_close_is_immediate_and_addressed(self):
        self.desktop.execute("close_window", self.window)
        self.assertEqual(self.commands[-1], ["/usr/bin/hyprctl", "dispatch", 'hl.dsp.window.close({ window = "address:0x123abc" })'])

    def test_changed_target_does_nothing(self):
        for target in ({**self.window, "pid": 101}, {**self.window, "class": "terminal"}, {**self.window, "address": '0x123\"; exec()'}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.desktop.execute("close_window", target)
        self.assertEqual(self.commands, [])

    def test_unapproved_window_cannot_close(self):
        self.window["class"] = "Alacritty"
        with self.assertRaises(ValueError):
            self.desktop.execute("close_window", self.window)

    def test_workspace_lua(self):
        self.desktop.execute("workspace_2", {})
        self.assertEqual(self.commands[-1][-1], 'hl.dsp.focus({ workspace = "2" })')

    def test_workspace_legacy(self):
        self.policy["hyprland"] = "legacy"
        self.desktop.execute("workspace_2", {})
        self.assertEqual(self.commands[-1][-2:], ["workspace", "2"])

    def test_volume_limit(self):
        self.desktop.execute("volume_up", {})
        self.assertEqual(self.commands[-1], ["/usr/bin/wpctl", "set-volume", "-l", "0.80", "@DEFAULT_AUDIO_SINK@", "5%+"])

    def test_dispatch_error_is_not_success(self):
        desktop = Desktop(loader=lambda: self.policy, runner=lambda argv: "unknown dispatcher")
        with self.assertRaises(ValueError):
            desktop.execute("workspace_1", {})


if __name__ == "__main__":
    unittest.main()
