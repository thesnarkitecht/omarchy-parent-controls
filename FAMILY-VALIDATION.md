# Family controls validation — 2026-10-02

Source versions: Parent Controls **0.5.0-alpha.4**, bundled voice **0.3.1**. Tested in a cloned Try Omarchy VM running **Omarchy 4.0.3-1**, Arch Linux ARM64, kernel **7.2.6**, systemd, Hyprland, Chromium and PipeWire. The original VM and school computers were not modified.

## Linux checks completed

| Check | Result |
| --- | --- |
| Parent-controls suite | 113 passed, including the Linux release/bootstrap test |
| Integrated voice suite | 64 passed |
| Release installation | Built source archive upgraded the existing VM with `--skip-apps --with-hermes`; parent widget loaded; Hyprland reported no config errors |
| Reboot persistence | Control broker, policy service and audio socket active after reboot; child restrictions, Hermes isolation and audio checks passed again |
| Hermes kernel sandbox | Parent policy, home and session sockets hidden; system files read-only; no capabilities or privilege elevation; nested user namespaces denied; executable projects, Python venv, Git and actual Hermes `--version` worked |
| Child account | Ordinary HTTPS and development remained available; direct restricted browser/package-manager execution, passwordless sudo, downloaded native executables and policy tampering denied |
| Managed Chromium | Approved demo rendered; unapproved navigation displayed Chromium's blocked-page screen |
| Browser playback | Actual managed Chromium stream reached the desktop audio service; two seconds of non-silent PCM observed in memory on its output monitor |
| Browser microphone | Real Chromium permission prompt; one-time permission created an active `Chromium input` stream under `omarchy-kids` against the VM capture source |
| Audio proxy | Real worker namespace with `/run/user` hidden enumerated one output and one non-monitor input; synthetic 440 Hz playback/capture round trip passed before and after reboot |
| Local dictation | Production Recorder → Whisper → Qt dictation toggle → Wayland clipboard passed using synthesized speech and a temporary PipeWire source; the Laya callback was forbidden and never invoked |
| Wake and desktop actions | Production WakeListener emitted armed → awake → audio for synthesized “Hey Laya”; local transcription and candidate filtering selected Calculator. The action adapter opened, focused, maximized, restored and closed Calculator and switched workspaces |
| Managed web-app voice targeting | Focus/maximize/restore passed against a real Wayland Chromium window using its approved system service identity |
| Parent approval service | Real Unix broker and systemd HTTP relay passed child request → approval, rejected child phone enrollment, rejected wrong tokens and remote disabling, rejected unrestricted YouTube/playlist approvals, and added/removed one individual video |
| Launcher updates | Running Quickshell discovered additions/removals and restored normal entries after controlled overlay changes |

**177 automated cases passed on Linux.** Live integration checks above are additional. Logs and a compact evidence record are summarized in [vm-validation.json](docs/validation/vm-validation.json). GUI screenshots were captured from the running guest, not from mockups.

The VM ran without host graphics or audio access. Hyprland used software rendering; QEMU provided virtual sound devices with no physical microphone/speaker backend. Synthesized speech exercised the actual PipeWire capture and local models. These results establish Linux transport and integration behavior, not microphone quality or audible sound on the girls' computers.

The wake/action probe supplied the sole locally permitted action directly to the action adapter after inspecting the candidate set. It did not contact Laya or exercise the complete speech-to-Laya network path. The Qt dictation probe used a test policy and the real unlocked login-session check. Physical keyboard hotkeys, tray lifecycle, and lock/unlock still need device acceptance.

## Issues found and corrected

- PortAudio's ALSA path delivered about half the expected input frames in this VM, distorting dictation. Linux wake and dictation now use bounded 16 kHz mono capture through `parec`, resolving the current desktop input explicitly. The same synthesized sentence then transcribed correctly through live capture and the Qt clipboard flow. No recording is saved by the product.
- Chromium app mode generated URL-based Wayland classes despite `--class`, preventing voice focus/window actions. Managed web-app targets now require membership in their exact root-managed systemd service, rechecked against the live window PID.
- The audio diagnostic mistook a speaker monitor for a microphone under current `pactl` JSON. It now handles both named and indexed monitor schemas.
- A sandbox unit test incorrectly rejected Arch's resolved DNS file under `/run`. It now checks that only that file is mounted read-only into `/etc/resolv.conf`; the actual sandbox still hides `/run`.

## Remaining acceptance work

- Physical speakers/microphones, children's voices, room noise, false wake-ups, feedback and latency; continuous browser audio plus dictation on real hardware.
- Physical voice hotkeys, tray behavior, lock/unlock and voice setup using an actual Laya pairing. The Laya host and network command path were not exercised in this VM run.
- Tailscale Serve and a physical iPhone across networks. The local approval service passed; this was not a remote-phone connectivity test.
- Hermes provider setup, interactive conversations and broader coding workloads beyond shell execution, venv, Git and version startup.
- Actual YouTube playback and visible revocation through mpv/yt-dlp. Approval enforcement passed, but video playback was not exercised.
- Remote Math Match progress, APNs notifications and general computer/browser-agent tasks remain unimplemented.

Earlier evidence from the unchanged companion projects remains available: nine Laya tests, eleven Swift pairing/protocol checks, the unsigned arm64 iOS build, and [five small live text-routing cases](docs/validation/app-selection-validation.json). Those were not rerun for alpha.4. No model was custom-trained, GitHub release published, or TestFlight/App Store build submitted.
