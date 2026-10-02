# Family controls validation — 2026-10-02

Source versions: Omarchy Parent Controls **0.5.0-alpha.2**, bundled voice **0.3.0**, Parent Pocket **0.1.1**. The prior standalone voice 0.2 bundle remains an older deliverable; use the integrated family bundle for this work.

## Checks completed

| Check | Result |
| --- | --- |
| Parent-controls Python suite | 103 cases: 102 passed, 1 Linux-only bootstrap case skipped on macOS |
| Integrated voice suite | 55 passed, including HTTPS certificate/redirect checks, bounded choice mapping, live approval replacement, wake-word behavior and parent disable |
| Laya service suite | 9 passed |
| Swift pairing and cross-language protocol checks | 11 passed; decodes a real Python-generated status reply |
| Real HTTP remote-approval flow | Child request → parent approval → removal passed against a persisted temporary Store; only the Linux Unix-socket transport was substituted |
| URL-first approval over real local HTTP | 5 checks passed: paste-only website, repeat rename without duplicate, rejected bad token, removal, paste-only individual video; temporary Store and substituted Linux Unix transport |
| Managed Hermes sandbox policy | 8 new host-independent cases passed: exact mount/env scope, namespace flags, safe argv, runtime access, root/wrong-account rejection, missing-sandbox failure and storage trust; actual Linux isolation still pending |
| Live Laya text routing | 4 natural task prompts chose the intended approved app; an unsupported install request was rejected locally without sending it to the model |
| Native iOS build | Xcode 27, arm64 iOS target, unsigned application build succeeded |
| Python and shell syntax | Passed for changed Python modules and installers |
| Omarchy QML syntax | Controls.qml and BarWidget.qml parsed with Qt qmlformat |
| Visual review | SwiftUI parent Requests/Library/Controls rendered with AppKit hosting, plus the Qt child library; sample data only |

**166 Python cases passed**, one platform-specific case skipped. The Swift and live-flow checks are additional. The integration tests do not authenticate to, modify, or enroll any real family's computer. Six new approval tests exercise optional names, URL normalization, exact-origin scope, duplicate handling, rejected schemes/credentials/local hosts, parent authentication and extra-field rejection. Current loopback TLS tests were rerun after granting this coding environment network permission; no socket failures were skipped.

Authorization tests cover wrong/revoked phone tokens, non-root pairing attempts, wrong-account child requests, expired requests, duplicate and conflicting reviews, mutation replay IDs, exact video-link parsing, playlist/channel rejection, website origin approval, immediate catalog removal on revocation, uninstalled native applications, and missing broker behavior. Relay tests cover browser Origin rejection, missing authorization, chunked/oversized/extra-field requests and secret-free responses. Video tests verify the fixed player argv and the stop trigger on revocation or broker failure; they do not run a Linux player.

The live routing evidence is in [app-selection-validation.json](docs/validation/app-selection-validation.json). Early probes with bare app names were imperfect: a writing request returned unknown, and raw model output guessed an app for an unsupported instruction. The final pipeline supplies parent-managed task descriptions and enforces an independent local filter. Its small five-case result is a regression check, **not** evidence of broad language accuracy or a reason to give the model more authority. No model was custom-trained.

## Not yet verified on target devices

- Installation and upgrade on actual Omarchy machines, including restricted runtime compatibility, real Hyprland window classes, Wayland/PipeWire access, tray indicators, lock/unlock, reboot persistence and voice hotkey restoration across control-mode changes.
- Real children's voices, microphone hardware, room noise, false wake-ups, latency and speaker feedback. The preceding standalone voice release has generated-speech tests; those do not replace target-device testing.
- Real YouTube playback through mpv/yt-dlp, unavailable/age-restricted videos, player controls and visible revocation during playback.
- Actual Tailscale Serve/tailnet access rules and the Linux root-broker socket credentials. The service is not exposed publicly and has not been enabled on a school computer by this task.
- iPhone installation/signing, camera QR scanning, Face ID/passcode lifecycle, Keychain persistence, device switching and connectivity loss on a physical phone. Simulator services were unavailable in this sandbox. The unsigned device build succeeded; the preview images are source renders, not simulator screenshots.
- The actual Hermes CLI namespace on Linux, interactive startup/provider setup, compiler/package workflows, user-namespace kernel compatibility and hiding real desktop/admin sockets. The new implementation and `tests/integration_hermes_sandbox.py` are included, but a policy-builder unit test does not prove kernel isolation. Run this and the existing interactive Hermes acceptance check before relying on the sandbox.
- APNs notifications, general computer/browser-agent tasks and remote Math Match progress. These are not implemented by this release.

No GitHub release, TestFlight upload or App Store submission was performed. Keep the alpha label until the hardware checks pass.

The captured HTTP approval results are in [remote-approval-validation.json](docs/validation/remote-approval-validation.json) and [url-approval-validation.json](docs/validation/url-approval-validation.json). Parent Pocket previews and its build evidence refer to the separately delivered companion project.
