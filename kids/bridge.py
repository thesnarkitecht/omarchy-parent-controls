"""Unprivileged native-shell bridge. PINs travel only through stdin/socket."""
import json
from pathlib import Path
import subprocess
import sys
import time

from client import LIMIT, request
from core import origin, validate_policy


def status():
    value = request("status")
    from native_runtime import configured
    value["native"] = configured()
    value["active"] = configured() and subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", "omarchy-kids-policy.service"]
    ).returncode == 0
    value["hermes"] = subprocess.run(["/usr/bin/systemctl", "is-active", "--quiet", "omarchy-kids-hermes-desktop.service"]).returncode == 0
    value["ready"] = configured()
    value["pending_confirmation"] = False
    return value


def dispatch(value):
    action = value.get("action")
    if action == "status":
        return status()
    if action in ('enable-controls', 'disable-controls'):
        request(action, pin=value.get('pin'))
        return {**status(), 'message': 'Controlled mode is ' + ('on.' if action == 'enable-controls' else 'off.')}
    if action == "add-webapp":
        import re
        state = request("status")["policy"]
        name, url = value.get("name", "").strip(), value.get("url", "").strip()
        key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
        if not key or not key[0].isalpha():
            key = "app-" + key
        origins = [origin(url)] + [origin(x.strip()) for x in value.get("origins", "").split(",") if x.strip()]
        policy = validate_policy({**state, "webapps": [*state["webapps"],
            {"id": key, "name": name, "url": url, "origins": origins}]})
        request("save", pin=value.get("pin"), policy=policy)
        return {"ok": True, "message": name + " approved.", "policy": policy}
    if action == "remove-webapp":
        policy = request("status")["policy"]
        policy["webapps"] = [a for a in policy["webapps"] if a["id"] != value.get("id")]
        request("save", pin=value.get("pin"), policy=policy)
        return {"ok": True, "message": "Webapp removed.", "policy": policy}
    if action == "change-pin":
        if value.get("new_pin") != value.get("confirm"):
            raise ValueError("The new PINs do not match.")
        request(action, pin=value.get("pin"), new_pin=value.get("new_pin"))
        return {"ok": True, "message": "Parent PIN changed."}
    raise ValueError("Unknown action.")


def main():
    try:
        raw = sys.stdin.buffer.readline(LIMIT + 1)
        if len(raw) > LIMIT or not raw.endswith(b"\n"):
            raise ValueError("Invalid request.")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Invalid request.")
        reply = dispatch(value)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        reply = {"ok": False, "error": str(error)}
    print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
