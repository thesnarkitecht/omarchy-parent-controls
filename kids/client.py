import json
import socket

SOCKET = "/run/omarchy-kids-control/control.sock"
LIMIT = 65536

def request(action, **fields):
    payload = json.dumps({"action": action, **fields}).encode() + b"\n"
    if len(payload) > LIMIT:
        raise ValueError("Request too large")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(110)
        s.connect(SOCKET)
        s.sendall(payload)
        raw = s.makefile("rb").readline(LIMIT + 1)
    if len(raw) > LIMIT:
        raise RuntimeError("Response too large")
    result = json.loads(raw)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Parent control service unavailable"))
    return result
