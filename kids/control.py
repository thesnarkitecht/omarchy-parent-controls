"""Small root broker: structured policy operations only; never accepts commands."""
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import tempfile
import time
import struct

from core import CATALOG, pin_record, validate_policy, verify_pin
from client import LIMIT, SOCKET

STATE = Path("/var/lib/omarchy-kids-control")
EMPTY = {"native": [], "webapps": []}

def atomic_json(path, value):
    fd, temp = tempfile.mkstemp(prefix=".kids-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        d = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

class Store:
    def __init__(self, directory=STATE, clock=time.time):
        self.path, self.clock = Path(directory), clock

    def read(self, name):
        return json.loads((self.path / name).read_text())

    def save(self, name, value):
        atomic_json(self.path / name, value)

    def initialize(self, pin):
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.save("pin.json", pin_record(pin))
        if not (self.path / "policy.json").exists():
            self.save("policy.json", EMPTY)
        self.save("attempts.json", {"failures": 0, "until": 0})

    def authenticate(self, pin):
        # Global, persisted backoff prevents parallel connections and reboot resets.
        attempts = self.read("attempts.json")
        now = self.clock()
        if attempts["until"] > now:
            raise ValueError(f"Try again in {int(attempts['until'] - now) + 1} seconds.")
        if not verify_pin(pin, self.read("pin.json")):
            failures = min(attempts["failures"] + 1, 20)
            delay = min(3600, 2 ** failures)
            self.save("attempts.json", {"failures": failures, "until": now + delay})
            raise ValueError("Incorrect parent PIN.")
        self.save("attempts.json", {"failures": 0, "until": 0})

    def dispatch(self, req):
        if not isinstance(req, dict):
            raise ValueError("Invalid request.")
        action = req.get("action")
        if action == 'family-status':
            from family import public
            return public(self)
        if action == 'voice-catalog':
            from family import voice_catalog
            return voice_catalog(self)
        if action == 'remote-parent':
            from family import remote
            return remote(self, req.get('envelope'))
        if action == 'remote-sealed':
            from sealed_remote import dispatch
            return dispatch(self, req.get('packet'))
        if action == 'family-change':
            from family import read, apply, public
            self.authenticate(req.get('pin'))
            state = read(self)
            apply(self, state, req.get('operation'), req.get('fields', {}))
            self.save('family.json', state)
            return public(self)
        if action == "status":
            return {"policy": self.read("policy.json"), "catalog": {
                key: {**app, "installed": Path(app["binary"]).is_file()} for key, app in CATALOG.items()
            }}
        if action not in ("save", "change-pin", "check-pin", "enable-controls", "disable-controls", "clear-webapp-data"):
            raise ValueError("Unknown action.")
        self.authenticate(req.get("pin"))
        if action == "check-pin":
            return {}
        if action == 'enable-controls':
            from parent_tools import ensure_windows_stopped
            ensure_windows_stopped()
        if action == 'clear-webapp-data':
            from webapp_data import clear
            clear(req.get('id'), self.read('policy.json'))
            return {}
        if action == "save":
            policy = validate_policy(req.get("policy"))
            from sandbox import trusted_executable
            for key in policy["native"]:
                trusted_executable(CATALOG[key]["binary"])
            self.save("policy.json", policy)
            from native_runtime import configured, desktop_entries
            if configured(): desktop_entries(policy)
            # End all old apps and renderer processes; revocations apply immediately.
            return {"effect": "restart"}
        if action == "change-pin":
            self.save("pin.json", pin_record(req.get("new_pin")))
            return {}
        return {"effect": action}

def service_action(action):
    if action in ('enable-controls', 'disable-controls'):
        unit = 'omarchy-kids-' + ('enable' if action == 'enable-controls' else 'disable') + '.service'
        subprocess.run(['/usr/bin/systemctl', 'start', unit], check=True, timeout=90)
    elif action == 'restart':
        from native_runtime import revoke_webapps
        revoke_webapps()
    else:
        raise ValueError('Unknown service action.')

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        effect = None
        try:
            raw = self.rfile.readline(LIMIT + 1)
            if len(raw) > LIMIT or not raw.endswith(b"\n"):
                raise ValueError("Invalid request size.")
            req = json.loads(raw)
            if isinstance(req, dict) and req.get('action') in ('ask-parent', 'remote-enroll', 'remote-revoke', 'access-admin'):
                _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                response = peer_action(self.server.store, req, uid)
            elif isinstance(req, dict) and req.get("action") == "launch-hermes":
                from managed_hermes import launch
                _, uid, _ = struct.unpack("3i", self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                response = launch(uid)
            elif isinstance(req, dict) and req.get("action") == "launch-webapp":
                from native_runtime import launch_webapp
                _, uid, _ = struct.unpack("3i", self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                response = launch_webapp(req.get("id"), uid, self.server.store.read("policy.json"), req.get('url'))
            else:
                response = self.server.store.dispatch(req)
            effect = response.pop("effect", None)
            if effect:
                action = effect
                effect = None
                service_action(action)
            reply = {"ok": True, **response}
        except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as e:
            reply = {"ok": False, "error": str(e)}
        try:
            self.wfile.write(json.dumps(reply).encode() + b"\n")
            self.wfile.flush()
        except OSError:
            pass

def peer_action(store, req, uid):
    from family import submit, enroll, revoke
    if req['action'] == 'ask-parent':
        from native_runtime import account
        if uid != account()['uid']:
            raise ValueError('Requests must come from the school desktop account.')
        return submit(store, req.get('request'))
    if uid != 0:
        raise ValueError('Pairing and revocation require parent administrator access.')
    if req['action'] == 'access-admin':
        from access_control import change, status
        change(req.get('paused'))
        return status()
    if req['action'] == 'remote-enroll':
        return {'pairing': enroll(store, req.get('endpoint'), req.get('name'), req.get('relay'), req.get('temporary', False))}
    if req['action'] == 'remote-revoke':
        return revoke(store)
    raise ValueError('Unknown peer action.')

def main():
    if os.geteuid() != 0:
        raise SystemExit("The control broker must run as root.")
    if not (STATE / "pin.json").exists():
        raise SystemExit("Set the parent PIN with omarchy-kids-admin set-pin first.")
    path = Path(SOCKET)
    path.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        server.store = Store()
        os.chmod(SOCKET, 0o666)  # Local callers; every mutation authenticates server-side.
        server.serve_forever()

if __name__ == "__main__":
    main()
