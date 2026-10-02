> This copy is bundled with Omarchy Parent Controls 0.5. Its canonical installer and live approval settings are described in ../FAMILY.md. Use the plugin’s --voice-pairing option; the standalone setup notes below describe the underlying speech engine.

# Omarchy Voice

Local wake-word and hotkey transcription with immediate, bounded desktop control. Laya runs on a separate home server. **All desktop actions execute on the Omarchy computer that heard the request.** No confirmation dialogs or spoken approval steps.

## Install on an Omarchy computer

Requirements: Arch Linux / Omarchy, a microphone, Python 3.11+, and a parent-managed account. The companion host project produces a pairing folder with `policy.json`, `host.crt`, and `device.token`. Transfer only that computer's folder; never copy the host private key or full server configuration.

From this project folder, in a parent's terminal:

```sh
sudo bash scripts/install.sh /path/to/this-computers-pairing
```

Then, as the girl's logged-in desktop user:

```sh
python scripts/setup-desktop.py
school-voice doctor
school-voice show
```

`install.sh` installs into `/opt/school-voice`, keeps policy in `/etc/school-voice`, downloads the Whisper, keyword-spotting, and voice-activity models once, and adds an application launcher. It does not change parent-control policy, firewall rules, sudo rules, Omarchy package files, or existing shortcuts. It requires parent-admin installation because the child's writable home may be mounted with `noexec`.

`setup-desktop.py` detects Lua or legacy Hyprland config, refuses shortcut collisions, backs up the existing bindings file, validates using `hyprctl reload` and `hyprctl configerrors`, and rolls back on failure. It adds an XDG autostart entry. The hotkey also starts the process on demand if desktop autostart is unavailable.

The sample policy uses current Lua-based Omarchy. Set `hyprland` to `legacy` before installation on an older machine. Maximize and restore require current Lua dispatchers; older desktops reject those requests rather than using a race-prone active-window fallback.

## Use

| Shortcut | What it does |
|---|---|
| “Hey Laya” | Wake locally, capture the command, then act after a short pause |
| “Hey Laya, dictate …” | Copy dictated text without contacting the host |
| “Hey Laya, stop listening” | Mute the microphone until resumed manually |
| Super + Alt + M | Mute/resume all microphone use; remembers mute across restarts |
| Super + Alt + V | Start/finish a voice command |
| Super + Alt + D | Start/finish dictation; transcript goes to the clipboard |
| Escape while the window is focused | Cancel |

Wake mode keeps the microphone open **locally** for keyword detection. A persistent tray icon shows the actual state. If the desktop has no system tray, the window stays visible. Muting closes the microphone, blocks recording hotkeys, and persists across restarts. Resume with the button or Super+Alt+M; a muted microphone cannot hear an unmute command.

After “Hey Laya,” a short ready chime sounds. Speak naturally; voice activity detection finishes after about 0.9 seconds of silence. The app does not ask for confirmation. A wake with no command times out after four seconds. A wake command longer than 15 seconds is discarded. Done/error tones provide feedback. Hotkey recording still supports pressing again to finish.

A one-second rolling RAM buffer preserves words spoken immediately after the wake phrase. Before activation, audio is processed only for detection, not transcribed or sent anywhere. No real audio files, cloud transcription, or transcript history are created. The last transcript remains visible until canceled or replaced; dictated text stays on the clipboard until replaced.

The login-session lock state is checked about every two seconds and before command execution. Locking stops the microphone and cancels unfinished work. Unlocking resumes wake listening unless muted. If the login session cannot be verified, listening stays off. A failed microphone/model does not silently fall back to another device or remote service; the app shows an error and waits for manual Resume.

Examples:

- “Open math,” “open calculator,” “open writing.”
- “Switch to math,” “go to workspace two.”
- “Turn the volume down,” “mute,” “unmute.”
- “Pause the music,” “resume the video.”
- “Close this window,” “make this bigger,” “restore this window.”
- “Could you bring up my math game?”

Commands and wake phrases are English in this release. Familiar phrases use complete-utterance matching locally. Other phrases are narrowed by local language checks and sent to Laya, which chooses one candidate or `unknown`. Negated, multi-action, unsupported, and unrelated requests are rejected. This intentionally favors doing nothing over an unsupported guess, without asking for confirmation. Rephrase or use the mouse if a request is not understood.

Dictation is **copy to clipboard**, not automatic typing into another app. Paste where intended. This prevents a misfocused terminal or website from receiving executable text. Dictation has no Laya/network dependency.

## Parent policy

Edit `/etc/school-voice/policy.json` as an administrator. The app reloads it before every action. Set `enabled` to `false` to disable voice and dictation. Set `wake_word.enabled` to `false` to keep hotkeys while disabling hands-free listening. Wake and master-policy changes stop listening at the next two-second policy check; action permissions are still rechecked immediately before execution. Remove an action, workspace, or app to revoke it. File and parent-directory ownership are checked; writable user policy overrides are not supported.

`apps` provides a stable ID, spoken aliases, an absolute executable plus fixed arguments, and exact Hyprland window classes. Use `hyprctl -j clients` to inspect classes on the actual machine. Commands cannot supply their own arguments. Existing OS permissions still apply to launches. Use the same approved apps as the parental-controls project, and remove an app from both policies when revoking it.

The host also has a per-device action allowlist. If adding an app, update both the local policy and that device's action IDs in the host `server.json`, then restart the host. Removals on the client take effect immediately. Workspace IDs are restricted to the parent's list. Volume increases cap at 80%; this is a software volume limit, not a calibrated hearing-safety guarantee.

Closing, maximizing, or restoring targets the approved app window captured before recording. The address, process ID, and window class are checked again before execution. It cannot close a terminal or parent window unless a parent explicitly adds that class. Closing happens immediately, as requested; an application's own unsaved-document dialog may still appear.

## Wake phrase and sensitivity

The default parent policy uses `wake_word.phrase: "Hey Laya"`. The local Sherpa-ONNX model supports configurable English phrases without training a new model. Choose two to four words; longer distinctive phrases generally separate better than short common names. Changing the phrase reloads the detector. If the computers share a room, use different phrases on each to reduce simultaneous activation. This is **not speaker identification**; anyone or a nearby recording saying the phrase may activate it.

`threshold` defaults to `0.3` (higher means harder to trigger). `silence_seconds` defaults to `0.9` and can be set between 0.5 and 2 seconds for a slower speaker. Adjust only after trying the actual microphones, room, and voices. These values are recognition settings, not security permissions. A detected wake grants no additional desktop access.

The wake model and Silero VAD are downloaded from pinned upstream release URLs with SHA-256 checks. Model files live under the root-owned model directory. Runtime detection is CPU-only and offline. [Sherpa-ONNX keyword spotting](https://k2-fsa.github.io/sherpa/onnx/kws/index.html) describes the configurable keyword model; upstream code and model licenses remain applicable.

## Pairing and network

The client connects only to the configured HTTPS origin. It validates the host certificate and SAN hostname/IP, rejects redirects, ignores environment proxy settings, uses a different token per computer, and checks request IDs. Laya has no remote-execution endpoint. Its response is a single action ID, which is checked against both the transcript's candidates and current local permissions.

Allow the school computers to reach this host's TCP 43125 in the existing firewall policy. Nothing needs an inbound port on the child machines. No firewall changes are automated. A change of host IP or an expired certificate requires re-pairing. Use a stable LAN address or local DNS name.

## Troubleshooting

- **No window:** run `school-voice serve` in a terminal for startup errors. The launcher uses a private per-user Unix socket and permits only one instance.
- **No microphone:** check the desktop's default input device, then `school-voice doctor`. The first recording loads Whisper and can take longer.
- **Laya unavailable:** exact phrases and dictation still work. Check the host is awake, its service is running, the certificate matches its address, and the firewall permits TCP 43125.
- **App not found:** correct its fixed executable path or remove it from the parent policy. This installer does not install learning apps.
- **Can't control an app window:** check its class with `hyprctl -j clients`; the voice window is never a target.
- **Shortcut conflict:** no bindings are changed. Choose different shortcuts in your existing user bindings file, preserving the `/usr/local/bin/school-voice toggle` and `dictate` commands.

## Updates and removal

To update code, use **Quit School Voice** from the tray menu, then run as a parent:

```sh
sudo /opt/school-voice/venv/bin/python -m pip install --upgrade .
sudo /opt/school-voice/venv/bin/python scripts/download-wake-model.py
# Only for a 0.1 policy with no wake_word section:
sudo /opt/school-voice/venv/bin/python scripts/enable-wake.py
```

As the desktop user, rerun `python scripts/setup-desktop.py` to add the mute shortcut, then `school-voice show`. The hotkey installer preserves its existing V/D bindings. The migration backs up the parent policy and leaves the approved action list intact.

The policy and model directory are preserved. Do not rerun the first-install script over an existing policy.

To remove, stop the voice process, remove the three marked School Voice bindings and `~/.config/autostart/school-voice.desktop`, then remove `/opt/school-voice`, `/etc/school-voice`, `/usr/local/bin/school-voice`, and `/usr/share/applications/school-voice.desktop` as a parent. Remove the matching device from the host config and restart it. This app never owns or removes schoolwork or Math Match progress.

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

The TLS tests need OpenSSL and permission to bind localhost ports. Qt tests use fake microphone and desktop adapters; they do not operate the developer's computer. Production execution uses a root-owned fixed policy, Python isolated mode, and never runs the voice process as root.

Integration references: [Hyprland dispatchers](https://wiki.hypr.land/configuring/core/dispatchers/), [hyprctl](https://wiki.hypr.land/configuring/core/advanced-configuration/using-hyprctl/), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [sounddevice](https://python-sounddevice.readthedocs.io/en/latest/).
