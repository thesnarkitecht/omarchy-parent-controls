import json
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from school_voice.client import decide


class TLSClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cert = self.root / "host.crt"
        self.key = self.root / "host.key"
        self.token = self.root / "device.token"
        self.token.write_text("a" * 48)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-keyout", str(self.key), "-out", str(self.cert), "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
        self.mode = "ok"
        self.received = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.received.append((body, self.headers["Authorization"]))
                if owner.mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "https://127.0.0.1:1/stolen")
                    self.end_headers()
                    return
                result = {"version": 1, "id": body["id"], "action": "open_math"}
                if owner.mode == 'slot': result['action'] = 'choice_0'
                if owner.mode == "mismatch": result["id"] = "z" * 32
                if owner.mode == "forbidden": result["action"] = "volume_up"
                if owner.mode == "extra": result["argv"] = ["/bin/sh"]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.cert), str(self.key))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.policy = json.loads((Path(__file__).resolve().parents[1] / "policy.example.json").read_text())
        self.policy["server"] = {"url": f"https://127.0.0.1:{self.server.server_port}", "ca_file": str(self.cert), "token_file": str(self.token)}
        # Fixture paths are not privileged files; only ownership checks are replaced.
        self.trust = patch("school_voice.client.trusted_file", side_effect=lambda p: p)
        self.trust.start()

    def tearDown(self):
        self.trust.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def test_https_auth_text_only(self):
        self.assertEqual(decide("Please open math", self.policy), "open_math")
        body, auth = self.received[0]
        self.assertEqual(set(body), {"version", "id", "text", "actions"})
        self.assertEqual(set(body["actions"]), {"open_math"})
        self.assertEqual(auth, "Bearer " + "a" * 48)

    def test_unrelated_requests_never_leave_machine(self):
        self.assertEqual(decide("disable parental controls", self.policy), "unknown")
        self.assertEqual(self.received, [])

    def test_invalid_responses_and_redirects(self):
        for mode in ("mismatch", "forbidden", "extra", "redirect"):
            self.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                decide("Please open math", self.policy)

    def test_certificate_hostname_enforced(self):
        self.policy["server"]["url"] = f"https://localhost:{self.server.server_port}"
        with self.assertRaises(Exception):
            decide("Please open math", self.policy)
        self.assertEqual(self.received, [])

    def test_integrated_catalog_maps_bounded_slot_back_to_local_app(self):
        self.mode = 'slot'
        self.policy['parent_controls'] = True
        self.assertEqual(decide('Please open math', self.policy), 'open_math')
        self.assertEqual(self.received[0][0]['actions'], {'choice_0': 'Open Math Match'})


if __name__ == "__main__":
    unittest.main()
