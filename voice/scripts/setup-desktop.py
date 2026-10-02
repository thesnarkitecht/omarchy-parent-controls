"""Run as the logged-in child user, after parent installation. Never replaces bindings."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

if os.getuid() == 0:
    raise SystemExit("Run this as the logged-in Omarchy desktop user, not root.")
hypr = Path.home() / ".config/hypr"
lua = (hypr / "bindings.lua").exists()
target = hypr / ("bindings.lua" if lua else "bindings.conf")
if not target.is_file():
    raise SystemExit("No existing Omarchy bindings file found; refusing to guess.")
binds = json.loads(subprocess.check_output(["hyprctl", "-j", "binds"], text=True))
for bind in binds:
    key = str(bind.get("key", "")).upper()
    if bind.get("modmask") == 72 and key in ("V", "D", "M"):
        command = {"V": "toggle", "D": "dictate", "M": "mute"}[key]
        if bind.get("arg") != "/usr/local/bin/school-voice " + command:
            raise SystemExit("A School Voice shortcut (SUPER+ALT+V/D/M) is already in use. No bindings changed.")
policy = json.loads(Path("/etc/school-voice/policy.json").read_text())
if policy["hyprland"] != ("lua" if lua else "legacy"):
    raise SystemExit("Ask a parent to set policy.json hyprland to match this desktop (lua or legacy).")
if lua:
    lines = '\n-- School Voice\no.bind("SUPER + ALT + V", "Voice control", "/usr/local/bin/school-voice toggle")\no.bind("SUPER + ALT + D", "Voice dictation", "/usr/local/bin/school-voice dictate")\no.bind("SUPER + ALT + M", "Mute microphone", "/usr/local/bin/school-voice mute")\n'
else:
    lines = '\n# School Voice\nbindd = SUPER ALT, V, Voice control, exec, /usr/local/bin/school-voice toggle\nbindd = SUPER ALT, D, Voice dictation, exec, /usr/local/bin/school-voice dictate\nbindd = SUPER ALT, M, Mute microphone, exec, /usr/local/bin/school-voice mute\n'
before = target.read_text()
backup = target.with_name(target.name + f".school-voice-{time.time_ns()}.bak")
shutil.copy2(target, backup)
new_lines = [line for line in lines.splitlines() if line and line not in before.splitlines()]
target.write_text(before + "\n" + "\n".join(new_lines) + "\n")
try:
    subprocess.run(["hyprctl", "reload"], check=True, capture_output=True)
    errors = subprocess.check_output(["hyprctl", "configerrors"], text=True).strip()
    if errors and errors.lower() not in ("ok", "no errors", "no errors found"):
        raise ValueError(errors)
except Exception:
    target.write_text(before)
    subprocess.run(["hyprctl", "reload"], check=False)
    raise SystemExit("Hyprland rejected the change; original bindings restored.")
autostart = Path.home() / ".config/autostart"
autostart.mkdir(parents=True, exist_ok=True)
(autostart / "school-voice.desktop").write_text('[Desktop Entry]\nType=Application\nName=School Voice\nExec=/usr/local/bin/school-voice serve\nX-GNOME-Autostart-enabled=true\n')
print("Say Hey Laya for hands-free control. Voice: SUPER+ALT+V. Dictation: SUPER+ALT+D. Mute/resume: SUPER+ALT+M.")
print("Original bindings saved at", backup)
