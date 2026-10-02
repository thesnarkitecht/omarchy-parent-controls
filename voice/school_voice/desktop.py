from __future__ import annotations

import json
import os
import re
import subprocess
from .policy import catalog, load, trusted_file
from pathlib import Path


def run(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=4, check=True,
                            env={**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin"})
    return result.stdout.strip()


class Desktop:
    def __init__(self, loader=load, runner=run, launcher=None):
        self.loader, self.run = loader, runner
        self.launcher = launcher or self._launch

    @staticmethod
    def _launch(argv):
        trusted_file(Path(argv[0]))
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env={**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin"})

    def active(self) -> dict:
        try:
            return json.loads(self.run(["/usr/bin/hyprctl", "-j", "activewindow"]))
        except (OSError, ValueError, subprocess.SubprocessError):
            return {}

    def clients(self) -> list:
        result = json.loads(self.run(["/usr/bin/hyprctl", "-j", "clients"]))
        if not isinstance(result, list):
            raise ValueError("Cannot read desktop windows")
        return result

    def dispatch(self, policy, lua, legacy):
        args = [lua] if policy["hyprland"] == "lua" else legacy
        reply = self.run(["/usr/bin/hyprctl", "dispatch", *args])
        if reply.lower() != "ok":
            raise ValueError("Hyprland did not accept the action: " + reply[:160])

    @staticmethod
    def matches(app, window):
        if 'unit' not in app:
            return window.get('class') in app['classes']
        # Wayland Chromium app windows ignore --class and derive app_id from
        # their URL. Bind voice targeting to the root-managed systemd service,
        # not a guessed class or a title another window could share.
        pid, unit = window.get('pid'), app['unit']
        if type(pid) is not int or pid <= 0 or not re.fullmatch(r'omarchy-kids-webapp-[a-z0-9-]+\.service', unit):
            return False
        try:
            return '0::/system.slice/' + unit in Path(f'/proc/{pid}/cgroup').read_text().splitlines()
        except OSError:
            return False

    def checked_target(self, policy, target):
        address = target.get("address", "")
        if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            raise ValueError("Choose an approved application window first")
        for window in self.clients():
            if window.get("address") == address and window.get("pid") == target.get("pid") and window.get("class") == target.get("class") and any(self.matches(app, window) for app in policy['apps'].values()):
                return address
        raise ValueError("That window has changed or is not approved for voice control")

    def execute(self, action: str, target: dict) -> str:
        # Reload on every execution: a parent's revocation takes effect immediately.
        p = self.loader()
        if action not in catalog(p):
            raise ValueError("That action is not approved")
        if action.startswith("open_"):
            app = p["apps"][action[5:]]
            self.launcher(list(app["argv"]))
        elif action.startswith("focus_"):
            app = p["apps"][action[6:]]
            window = next((w for w in self.clients() if self.matches(app, w)), None)
            if not window:
                raise ValueError("That app isn't open. Say “open " + app["aliases"][0] + "”.")
            address = self.checked_target(p, window)
            self.dispatch(p, f'hl.dsp.focus({{ window = "address:{address}" }})', ["focuswindow", "address:" + address])
        elif action.startswith("workspace_"):
            n = int(action[10:])
            self.dispatch(p, f'hl.dsp.focus({{ workspace = "{n}" }})', ["workspace", str(n)])
        elif action in ("close_window", "maximize", "restore"):
            address = self.checked_target(p, target)
            if action == "close_window":
                self.dispatch(p, f'hl.dsp.window.close({{ window = "address:{address}" }})', ["closewindow", "address:" + address])
            elif p["hyprland"] == "lua":
                state = "set" if action == "maximize" else "unset"
                self.dispatch(p, f'hl.dsp.window.fullscreen({{ window = "address:{address}", mode = "maximized", action = "{state}" }})', [])
            else:
                # Legacy fullscreen only targets active windows; refuse instead of racing focus.
                raise ValueError("Maximize and restore require the current Lua-based Hyprland")
        elif action in ("volume_up", "volume_down"):
            self.run(["/usr/bin/wpctl", "set-volume", "-l", "0.80", "@DEFAULT_AUDIO_SINK@", "5%+" if action == "volume_up" else "5%-"])
        elif action in ("mute", "unmute"):
            self.run(["/usr/bin/wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if action == "mute" else "0"])
        elif action in ("media_pause", "media_play"):
            self.run(["/usr/bin/playerctl", "pause" if action == "media_pause" else "play"])
        else:
            raise ValueError("Unsupported action")
        return catalog(p)[action]
