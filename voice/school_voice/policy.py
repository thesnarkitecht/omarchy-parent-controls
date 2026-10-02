from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

POLICY = Path("/etc/school-voice/policy.json")
ID = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
FIXED = {
    "volume_up": "Turn the sound up by five percent",
    "volume_down": "Turn the sound down by five percent",
    "mute": "Mute the speakers",
    "unmute": "Unmute the speakers",
    "media_pause": "Pause playing music or video",
    "media_play": "Resume playing music or video",
    "close_window": "Close the previously active approved application window",
    "maximize": "Make the previously active approved application fill the workspace",
    "restore": "Restore the previously active approved application to normal size",
}


def trusted_file(path: Path) -> Path:
    """Check the full resolved chain, not only the leaf. No user-supplied policy path."""
    path = path.resolve(strict=True)
    for entry in (path, *path.parents):
        info = entry.stat()
        if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError(f"Parent-managed file must be root-owned and not writable by others: {entry}")
    if not path.is_file():
        raise ValueError("Expected a regular parent-managed file")
    return path


def validate(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported voice policy")
    if data.get("hyprland") not in ("lua", "legacy"):
        raise ValueError("Set hyprland to lua or legacy")
    server = data.get("server", {})
    url = urlsplit(server.get("url", ""))
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("Laya needs an HTTPS origin, without credentials, path or query")
    if server.get('transport', 'https') not in ('https', 'relay'):
        raise ValueError('Unknown Laya connection type')
    if server.get('transport') == 'relay':
        if url.port not in (None, 443):
            raise ValueError('Managed connections use HTTPS port 443')
        for key, pattern in [('channel', r'[0-9a-f]{64}'), ('device_id', r'[0-9a-f]{32}'), ('relay_token', r'[A-Za-z0-9_-]{43}')]:
            if not isinstance(server.get(key), str) or not re.fullmatch(pattern, server[key]):
                raise ValueError('Pair this voice device again')
    for key in ("ca_file", "token_file"):
        if not isinstance(server.get(key), str) or not server[key].startswith("/etc/school-voice/"):
            raise ValueError(f"{key} must be in /etc/school-voice")
    if not isinstance(data.get("whisper_model"), str) or not data["whisper_model"].startswith("/opt/school-voice/models/"):
        raise ValueError("Whisper model must be installed by the parent")
    apps = data.get("apps")
    if not isinstance(apps, dict) or not 0 <= len(apps) <= 48:
        raise ValueError("Approve at most forty-eight apps")
    for name, app in apps.items():
        if not ID.fullmatch(name) or not isinstance(app, dict):
            raise ValueError("Invalid app id")
        argv = app.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(s, str) and s and "\0" not in s for s in argv) or not argv[0].startswith("/"):
            raise ValueError("App command must be a fixed absolute executable and argument list")
        if not isinstance(app.get("label"), str) or not 1 <= len(app["label"]) <= 80:
            raise ValueError("App needs a short label")
        if 'purpose' in app and (not isinstance(app['purpose'], str) or not 1 <= len(app['purpose']) <= 70):
            raise ValueError('App purpose must be a short parent-managed description')
        if not isinstance(app.get("classes"), list) or not app["classes"] or not all(isinstance(c, str) and 0 < len(c) <= 128 for c in app["classes"]):
            raise ValueError("App needs exact Hyprland window classes")
        if 'unit' in app and (not isinstance(app['unit'], str) or not re.fullmatch(r'omarchy-kids-webapp-[a-z0-9-]+\.service', app['unit'])):
            raise ValueError('Invalid managed web-app service')
        if not isinstance(app.get("aliases"), list) or not app["aliases"] or not all(isinstance(a, str) and 0 < len(a) <= 80 for a in app["aliases"]):
            raise ValueError("App needs spoken aliases")
    if not isinstance(data.get("actions"), list) or not all(x in FIXED for x in data["actions"]):
        raise ValueError("Unknown desktop action")
    if not isinstance(data.get("workspaces"), list) or not all(type(x) is int and 1 <= x <= 10 for x in data["workspaces"]):
        raise ValueError("Workspaces must be integers from 1 to 10")
    if type(data.get("enabled", True)) is not bool:
        raise ValueError("enabled must be boolean")
    wake = data.get("wake_word", {"enabled": False})
    if not isinstance(wake, dict) or type(wake.get("enabled")) is not bool:
        raise ValueError("wake_word.enabled must be boolean")
    if wake["enabled"]:
        if not isinstance(wake.get("phrase"), str) or not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+){1,3}", wake["phrase"]):
            raise ValueError("Choose a wake phrase of two to four English words")
        if not isinstance(wake.get("model_dir"), str) or not wake["model_dir"].startswith("/opt/school-voice/models/"):
            raise ValueError("Wake models must be installed by a parent")
        for key, default, low, high in (("threshold", .3, .1, .9), ("silence_seconds", .9, .5, 2)):
            value = wake.get(key, default)
            if type(value) not in (int, float) or not low <= value <= high:
                raise ValueError("Invalid wake-word " + key)
    return data


def load() -> dict:
    data = validate(json.loads(trusted_file(POLICY).read_text()))
    if data.get('parent_controls') is True:
        from .parent_controls import merge
        data = validate(merge(data))
    if not data.get("enabled", True):
        raise ValueError("Voice control is turned off by a parent")
    return data


def catalog(policy: dict) -> dict[str, str]:
    result = {a: FIXED[a] for a in policy["actions"]}
    for key, app in policy["apps"].items():
        result["open_" + key] = "Open " + app["label"] + (' for ' + app['purpose'] if app.get('purpose') else '')
        result["focus_" + key] = "Switch to the open " + app["label"] + " window"
    for n in policy["workspaces"]:
        result[f"workspace_{n}"] = f"Switch to desktop workspace {n}"
    return result
