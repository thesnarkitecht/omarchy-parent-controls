import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kids"))
from core import origin, approved_url, validate_policy, pin_record, verify_pin
from control import Store

def policy():
    return {"native": [], "webapps": [{"id": "learn", "name": "Learn", "url": "https://learn.example.org/start",
            "origins": ["https://learn.example.org"]}]}

class PolicyTests(unittest.TestCase):
    def test_exact_https_origin(self):
        self.assertTrue(approved_url("https://learn.example.org/lesson?id=1", ["https://learn.example.org"]))
        for url in ["http://learn.example.org", "https://evil.learn.example.org", "https://learn.example.org.evil.com",
                    "https://learn.example.org@evil.com", "https://evil.com@learn.example.org", "file:///etc/passwd",
                    "javascript:alert(1)", "data:text/html,hi", "blob:https://learn.example.org/id",
                    "chrome://settings", "devtools://devtools", "ftp://learn.example.org", "https://learn.example.org:8443"]:
            with self.subTest(url=url): self.assertFalse(approved_url(url, ["https://learn.example.org"]))

    def test_reject_ambiguous_hosts(self):
        for value in ["https://localhost", "https://127.0.0.1", "https://[::1]", "https://2130706433", "https://0x7f000001",
                      "https://x.local", "https://x.internal", "https://*.example.org", "https://foo..example.org",
                      "https://good.org\\@evil.com", "https://good.org\n", "https://good.org.", "https://good.org:abc"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): origin(value)

    def test_normalization(self):
        self.assertEqual(origin("https://EXAMPLE.ORG:443/a"), "https://example.org")
        self.assertEqual(origin("https://bücher.de"), "https://xn--bcher-kva.de")

    def test_bad_policy_shapes(self):
        for value in [None, [], {}, {"native": ["/bin/bash"], "webapps": []}, {"native": ["calculator", "calculator"], "webapps": []},
                      {"native": "calculator", "webapps": []}, {"native": [], "webapps": "bad"}]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): validate_policy(value)

    def test_start_origin_must_be_approved(self):
        value = policy(); value["webapps"][0]["url"] = "https://other.example.org"
        with self.assertRaises(ValueError): validate_policy(value)

    def test_no_injected_commands(self):
        value = policy(); value["webapps"][0]["exec"] = "sudo sh"
        with self.assertRaises(ValueError): validate_policy(value)

    def test_duplicate_ids(self):
        value = policy(); value["webapps"].append(copy.deepcopy(value["webapps"][0]))
        with self.assertRaises(ValueError): validate_policy(value)

    def test_valid_policy(self):
        self.assertEqual(validate_policy(policy()), policy())

class AuthTests(unittest.TestCase):
    def test_hashes_are_salted(self):
        first, second = pin_record("13579246"), pin_record("13579246")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_pin("13579246", first))
        self.assertFalse(verify_pin("00000000", first))
        self.assertNotIn("13579246", json.dumps(first))

    def test_pin_constraints(self):
        for value in [None, "1234", "a"*8, "１２３４５６７８", "0"*13, "12345678\n"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): pin_record(value)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.store = Store(self.temp.name, clock=lambda: self.now)
        self.store.initialize("13579246")
        from unittest.mock import patch
        native = patch('native_runtime.configured', return_value=False)
        native.start()
        self.addCleanup(native.stop)

    def test_backoff_survives_new_process(self):
        with self.assertRaisesRegex(ValueError, "Incorrect"):
            self.store.authenticate("00000000")
        other = Store(self.temp.name, clock=lambda: self.now)
        with self.assertRaisesRegex(ValueError, "Try again"):
            other.authenticate("13579246")
        self.now += 3
        other.authenticate("13579246")
        self.assertEqual(other.read("attempts.json")["failures"], 0)

    def test_all_mutations_require_pin(self):
        for action in ["save", "start", "stop", "change-pin", "check-pin", "enable-controls", "disable-controls"]:
            self.now += 4000
            with self.subTest(action=action):
                with self.assertRaises(ValueError): self.store.dispatch({"action": action})
        self.assertEqual(self.store.read("policy.json"), {"native": [], "webapps": []})

    def test_unknown_action(self):
        with self.assertRaises(ValueError): self.store.dispatch({"action": "exec", "command": "sh"})

    def test_save_is_atomic_and_restarts(self):
        reply = self.store.dispatch({"action": "save", "pin": "13579246", "policy": policy()})
        self.assertEqual(reply, {"effect": "restart"})
        self.assertEqual(self.store.read("policy.json"), policy())
        self.assertEqual(os.stat(Path(self.temp.name) / "policy.json").st_mode & 0o777, 0o600)

    def test_failed_validation_preserves_policy(self):
        with self.assertRaises(ValueError):
            self.store.dispatch({"action": "save", "pin": "13579246", "policy": {"native": ["bash"], "webapps": []}})
        self.assertEqual(self.store.read("policy.json"), {"native": [], "webapps": []})

    def test_pin_rotation(self):
        self.store.dispatch({"action": "change-pin", "pin": "13579246", "new_pin": "24681357"})
        self.store.authenticate("24681357")
        with self.assertRaises(ValueError): self.store.authenticate("13579246")

    def test_status_never_exposes_hash(self):
        value = self.store.dispatch({"action": "status"})
        self.assertEqual(set(value), {"policy", "catalog"})
        self.assertNotIn("hash", json.dumps(value))

