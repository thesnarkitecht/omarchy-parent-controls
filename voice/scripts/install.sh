#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) -ne 0 ]]; then
  echo "Run in a parent's terminal: sudo bash scripts/install.sh /path/to/device-pairing" >&2
  exit 1
fi
if [[ $# -ne 1 || ! -f "$1/policy.json" || ! -f "$1/host.crt" || ! -f "$1/device.token" ]]; then
  echo "Provide the device pairing directory created on the Laya host." >&2
  exit 1
fi
source_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
pairing_dir=$(cd -- "$1" && pwd)
if [[ ! -f /etc/arch-release ]]; then
  echo "This installer is for Arch Linux / Omarchy." >&2
  exit 1
fi
if [[ -e /etc/school-voice/policy.json ]]; then
  echo "An installation exists. Preserve its parent policy; follow README update instructions." >&2
  exit 1
fi
pacman -S --needed --noconfirm python python-pip portaudio libxcb libxkbcommon libxkbcommon-x11 xcb-util-cursor playerctl wireplumber
install -d -m 0755 /opt/school-voice /etc/school-voice
python -m venv /opt/school-voice/venv
/opt/school-voice/venv/bin/python -m pip install "$source_dir"
install -m 0644 "$pairing_dir/policy.json" /etc/school-voice/policy.json
install -m 0644 "$pairing_dir/host.crt" /etc/school-voice/host.crt
# A device token is a restricted client credential, never the server's private key.
install -m 0644 "$pairing_dir/device.token" /etc/school-voice/device.token
/opt/school-voice/venv/bin/python -I -c 'from school_voice.policy import load; load()'
/opt/school-voice/venv/bin/python "$source_dir/scripts/download-model.py"
/opt/school-voice/venv/bin/python "$source_dir/scripts/download-wake-model.py"
cat > /usr/local/bin/school-voice <<'WRAPPER'
#!/bin/sh
exec /opt/school-voice/venv/bin/python -I -m school_voice.cli "$@"
WRAPPER
chmod 0755 /usr/local/bin/school-voice
install -m 0644 "$source_dir/packaging/school-voice.desktop" /usr/share/applications/school-voice.desktop
echo "Installed. As the girl's logged-in desktop user, run: python scripts/setup-desktop.py"
echo "Then run: school-voice doctor"
echo "The installer did not change parental controls or firewall rules."
