# Web-app playback, microphone and dictation

The previous web-app launcher hid `/run/user` and exposed only the Wayland display socket. Chromium's Pulse client therefore could not reach the desktop audio service, affecting both playback and microphone input. This is a source-level cause found in the launcher; the physical computers were not connected for diagnosis here.

The audio fix adds a private, socket-activated local transport. Approved Chromium web apps receive an explicit `PULSE_SERVER` pointing to one mounted audio endpoint. The bridge runs as the configured desktop account and connects to that account's normal Pulse-compatible audio service (PipeWire on standard Omarchy). The listening socket is created under a root-owned directory, is accessible only to the browser worker, and every accepted connection is checked against that worker's kernel UID.

The browser still cannot access the rest of `/run/user`, the desktop session bus or the native PipeWire graph socket. Parent-control policy and credentials are unchanged. Only local Unix sockets are used; there is no audio TCP listener. Socket permissions and desktop configuration are not made world-accessible. A dedicated root-owned client configuration disables shared-memory/FD transport so playback and microphone data pass through the bounded byte relay. Samples are never written to disk or logged by the bridge.

The endpoint carries both playback and capture. It is not a playback-only filter. Websites remain subject to Chromium's existing microphone permission prompts; the fix does not automatically grant every website microphone access. The worker has audio-service access, including the normal Pulse control surface, so this is not a per-site audio security boundary. No such endpoint is added to the sandboxed Hermes CLI.

School Voice dictation continues to run as the child and use the normal local audio service. Its microphone device, mute state, wake word, transcription and clipboard behavior are not redirected through the browser bridge. Since alpha.4 it captures through the desktop PulseAudio service directly, avoiding the ALSA sample loss reproduced in the VM. The regression suite includes the full simulated dictation hotkey → recording → local transcription → clipboard flow, without a model request or desktop command.

## Apply the update

From the repository checkout on each Omarchy machine:

```bash
git pull --ff-only
bash install.sh --skip-apps
```

The parent PIN authorizes the update. The installer adds the audio service/socket and client configuration; re-open web apps after updating so they receive the new environment. This does not require changing router settings or restarting the entire desktop's audio service.

## Verify on the machine

While the child is logged in:

```bash
systemctl --user status pipewire pipewire-pulse wireplumber
systemctl status omarchy-kids-audio.socket
sudo python3 tests/integration_audio.py
```

The diagnostic checks real sink/source enumeration from the browser worker with `/run/user` hidden. It reads metadata only. Then play a known audio clip in an approved web app, allow a microphone prompt in a trusted approved site, and try **Super+Alt+D** for dictation. Verify the correct input/output devices and that neither the desktop nor the site is muted. A site may require clicking Play before autoplay is allowed.

If audio remains unavailable, inspect `sudo journalctl -u omarchy-kids-audio.service -n 50 --no-pager` and `sudo tail -n 50 /var/log/omarchy-kids-webapps.log`. These logs can distinguish a stopped desktop audio service from connection, device or browser errors. If the desktop audio service is not running, restore that service before retesting. Keep microphone permission prompts enabled.

## Validation limits

The alpha.4 Omarchy VM run verified the actual systemd bridge, Chromium playback, Chromium's microphone permission flow and a synthetic playback/capture round trip. It also verified live local dictation and clipboard delivery after fixing the ALSA capture issue. See [the VM report](../FAMILY-VALIDATION.md) for the exact scope and remaining hardware checks.

For a synthetic transport test that neither records a real microphone nor plays through real speakers, run:

```bash
sudo python3 tests/integration_audio_stream.py
```

This creates a temporary virtual sink, verifies a 440 Hz tone through the worker's production audio socket, and removes the sink. It leaves desktop default devices unchanged.
