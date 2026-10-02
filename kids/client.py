import json
import socket

SOCKET = "/run/omarchy-kids-control/control.sock"
LIMIT = 65536
RESPONSE_LIMIT = 1024 * 1024

def request(action, timeout=110, **fields):
    payload = json.dumps({"action": action, **fields}).encode() + b"\n"
    if len(payload) > LIMIT:
        raise ValueError("Request too large")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(SOCKET)
        s.sendall(payload)
        raw = s.makefile("rb").readline(RESPONSE_LIMIT + 1)
    if len(raw) > RESPONSE_LIMIT:
        raise RuntimeError("Response too large")
    result = json.loads(raw)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Parent control service unavailable"))
    return result
