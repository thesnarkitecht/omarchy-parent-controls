"""Policy validation and parent authentication. No UI or privileged side effects."""
import hashlib
import hmac
import ipaddress
import os
import re
from urllib.parse import urlsplit

# Optional educational applications; everyday native apps are selected separately.
CATALOG = {
    "math": {"name": "Math Match", "binary": "/usr/local/bin/sparkle-math", "package": None},
    "tuxpaint": {"name": "Tux Paint", "binary": "/usr/bin/tuxpaint", "package": "tuxpaint"},
    "gcompris": {"name": "GCompris", "binary": "/usr/bin/gcompris-qt", "package": "gcompris-qt"},
    "supertux": {"name": "SuperTux", "binary": "/usr/bin/supertux2", "package": "supertux"},
    "calculator": {"name": "Calculator", "binary": "/usr/bin/gnome-calculator", "package": "gnome-calculator"},
}

def origin(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Enter an HTTPS website address.")
    if any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("Invalid characters in website address.")
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username is not None or u.password is not None:
        raise ValueError("Only HTTPS websites without embedded credentials are allowed.")
    host = u.hostname.encode("idna").decode("ascii").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses are not allowed.")
    if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host):
        raise ValueError("Use a public website hostname, without wildcards.")
    if host.endswith((".local", ".localhost", ".internal", ".test", ".invalid")):
        raise ValueError("Local network addresses are not allowed.")
    if u.port not in (None, 443):
        raise ValueError("Only the standard HTTPS port is allowed.")
    return "https://" + host

def approved_url(url, origins):
    try:
        return origin(url) in origins
    except (ValueError, UnicodeError):
        return False

def validate_policy(value):
    if not isinstance(value, dict) or set(value) != {"native", "webapps"}:
        raise ValueError("Policy must contain native and webapps lists.")
    native, webapps = value["native"], value["webapps"]
    if not isinstance(native, list) or any(not isinstance(x, str) or x not in CATALOG for x in native):
        raise ValueError("Unknown native app.")
    if len(native) != len(set(native)):
        raise ValueError("Duplicate native apps.")
    if not isinstance(webapps, list) or len(webapps) > 32:
        raise ValueError("At most 32 webapps are supported.")
    result, ids = [], set()
    for app in webapps:
        if not isinstance(app, dict) or set(app) != {"id", "name", "url", "origins"}:
            raise ValueError("Invalid webapp fields.")
        key, name = app["id"], app["name"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", key) or key in ids:
            raise ValueError("Webapp IDs must be unique lowercase names.")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(c) < 32 for c in name):
            raise ValueError("App name must be 1–60 characters.")
        start = origin(app["url"])
        raw = app["origins"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
            raise ValueError("Each app needs 1–32 approved website origins.")
        origins = sorted(set(origin(x) for x in raw))
        if start not in origins:
            raise ValueError("The starting website must be approved.")
        ids.add(key)
        result.append({"id": key, "name": name.strip(), "url": app["url"], "origins": origins})
    return {"native": sorted(native), "webapps": result}

def pin_record(pin):
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{8,12}", pin):
        raise ValueError("Choose an 8–12 digit parent PIN.")
    salt = os.urandom(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64*1024*1024)
    return {"salt": salt.hex(), "hash": digest.hex()}

def verify_pin(pin, record):
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{8,12}", pin):
        return False
    digest = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(record["salt"]), n=32768, r=8, p=1, maxmem=64*1024*1024)
    return hmac.compare_digest(digest.hex(), record["hash"])
