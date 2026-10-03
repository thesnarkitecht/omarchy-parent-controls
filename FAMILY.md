# Parent Controls, now with voice and Videos

This is the **0.5.0-alpha.7 preview release**. It includes URL-first approvals, a managed Hermes coding sandbox, encrypted remote parent controls, and temporary pairing codes. Physical school-machine and iPhone acceptance remains pending.

## What belongs where

- **This repository**: the Omarchy plugin, the privileged approval broker, the private remote relay, Videos, child requests, and the integrated voice module in `voice/`.
- **Parent Pocket**: a separate native iOS project for parents, supplied separately. It connects to the plugin on each school computer; its source is not included here.
- **Laya Control**: the separate decision service on the shared host, supplied separately; its source is not included here. It suggests bounded actions; it cannot execute desktop commands or approve requests.

## The parent experience

Open Parent Pocket and unlock with Face ID, Touch ID, or the device passcode. Choose a paired school computer. Requests show exactly what the child wants and their optional reason. **Allow** or **Not now** takes effect without an additional confirmation dialog. The app shows success only after the computer acknowledges the change.

In Controls, tap **Paste a link · allow an app**. Paste the web-app URL; its name is optional. The page explains that approval covers the exact hostname, and the pasted page becomes its starting page. Bare hostnames gain `https://`; insecure schemes, embedded credentials and local addresses are rejected. Repeat pastes update the name without duplicating the same starting URL. No app installation is triggered by a website approval.

The Videos tab lets a parent add or remove individual YouTube video links. Video titles are optional too. The Controls tab also manages voice and wake-word settings. Pairing credentials stay in the iPhone Keychain, are excluded from migration to another device, and never go to Laya. The app locks when backgrounded.

The app refreshes while open and supports pull to refresh. **Background push notifications are not implemented.** The school computer must be awake and reachable; requests are not queued as delayed remote commands. Child requests themselves persist on the computer until reviewed.

## The girls' experience

Videos is an app on their normal Omarchy desktop. Its entire library consists of individual parent-approved video IDs. There is no discovery feed, recommendations, channel approval, playlist approval, next-video autoplay, or general browser inside the app. Playback opens a dedicated player, and the app checks approval immediately before playing and every two seconds afterward. Revocation or loss of the approval service stops playback. Availability depends on YouTube and the installed player/extractor; restricted, removed or unsupported videos may not play.

The request form supports a video, an exact HTTPS website, or an already installed supported school app. Children can select a school app by name. Requests grant no access until approved. A website approval allows the **exact hostname** shown, not just one page; redirects and login hosts need separate approval. App approvals do not install software.

Voice uses local wake detection and transcription: **“Hey Laya” → sentence → approved app/action**. The microphone indicator, mute button, voice dictation and hotkeys remain. Voice uses the plugin's live approvals rather than a second app list. “Help me write a story” can select Text Editor; “I want to practice math” can select Math Match when installed and approved. Microphone permission can be turned off by the parent remotely, and the child can always mute it locally.

## Install on a school computer

Use a supervised test computer first; this new integrated release has not been run on physical Omarchy hardware. The earlier parent-controls version has separate VM validation, which does not validate these new features.

From the reviewed `omarchy-parent-controls` source directory:

```bash
bash install.sh
```

Existing parent settings survive. The installer includes Videos, `mpv`, `yt-dlp`, QR-code support and bubblewrap. The outbound connector is installed and is enabled when a parent pairs a phone after relay activation.

To install and approve terminal Hermes on a machine that does not have it yet, use `bash install.sh --with-hermes`. You can combine this with the voice-pairing option below. The program runtime is installed from the pinned, checksum-verified upstream installer under root ownership.

For voice, first create the machine's Laya enrollment with the separate Laya Control project's `scripts/pair.py`, using the included voice policy example. The pairing script now grants the bounded `choice_0` through `choice_47` decision slots needed for a changing approved-app catalog. Existing Laya server enrollments need those slots added by the parent, then the service restarted. Those slots only return choices; they never execute code.

```bash
bash install.sh --voice-pairing /path/to/this-computers-laya-pairing
```

Then open the lock icon → **Voice, videos & requests** and enable voice. If installation ran outside a graphical login, run the printed desktop setup command as the child at their next login. The installer preserves existing Laya credentials on upgrades and backs up the old standalone voice policy before switching its app catalog to Parent Controls.

Math Match remains its own project. If installed at `/usr/local/bin/sparkle-math`, it appears in the child's school-app request picker and can be approved for launching and voice access. This release does not change or remotely display its progress data.

## Terminal and Hermes coding

The girls keep ordinary terminals and runtime tools. Projects in **`~/Projects/Workspace`** can execute builds, package scripts and virtual environments. The actual storage is `/var/lib/omarchy-coding/UID`; if the friendly link name already exists, it is preserved. Project files persist across sessions and removal of controls.

The managed **`hermes`** command always starts inside a bubblewrap sandbox. It has its coding workspace, its own persistent agent configuration, read-only system tools/runtime and network access. It does not mount parent-control files, the parent broker socket, the real home, or desktop-session sockets. No root privileges or new privilege elevation are granted. If the sandbox cannot start, Hermes stops instead of running outside it. Commands it launches stay in that namespace.

Run `hermes model` to configure the agent's provider, then `hermes` to code. Its own settings live at `/var/lib/omarchy-hermes-state/UID`; old `~/.hermes` data is preserved separately and not automatically imported. Inside the sandbox, projects appear at `/workspace`. Starting Hermes from a project subdirectory preserves that location; starting elsewhere opens the workspace root.

This protects the **managed launcher**, while normal terminals retain child-account authority. A child can independently run code outside that launcher. Root-owned controls and parent authentication still protect administrative changes, but this is not a guarantee that all arbitrary agents run sandboxed or that terminal users cannot create another content-access route. Agent networking includes reachable LAN/localhost TCP services. See [SECURITY.md](SECURITY.md) for the precise boundary.

On a supervised Omarchy test installation, run `python3 tests/integration_hermes_sandbox.py` from the source as the child, without sudo. It checks real namespace isolation, no privilege elevation, hidden parent/session files, project execution, venv, Git and the Hermes launcher. **This Linux acceptance check has not yet been run for alpha.2.**

## Connect the parent iPhone

The new managed connection requires the protocol-v2 Parent Pocket build and an activated relay deployment. See [deployment status](docs/REMOTE-ACCESS.md); it is included in alpha.7.

1. On the laptop, open the lock icon and choose `omarchy-parent-controls pair`.
2. Enter the parent PIN. Type the displayed code into Parent Pocket on your iPhone or iPhone Simulator. Scanning its QR is optional.
3. The connection starts automatically and reconnects when the laptop comes online. No VPN, port forwarding, domain purchase, or per-laptop URL setup.

`omarchy-parent-controls pair` opens the same flow from a terminal. Keep the code private: it grants parent access. It has four groups of four characters, expires after five minutes, and can be claimed once. Generate a fresh code on the laptop if needed; doing so invalidates its older unused code. The root broker stores its token hash and derived encryption keys. The connector and hosted relay cannot decrypt parent commands.

The phone can approve pasted app URLs, approve individual videos, review child requests, change voice settings, see approximate daily/week unlocked desktop usage, and Pause/Resume access. Pause freezes running work in memory and blocks child login; it persists across reboot, although reboot itself does not preserve unsaved work. Screen time uses logind activity/idle/lock signals; it is approximate total desktop time, not per-app history or tamperproof accounting.

When the phone is unavailable, the parent can resume on the recovery console using the controlled username and parent PIN, or use `omarchy-parent-controls resume` from an available parent terminal. Removal resumes work and removes the account gate.

Revoke all phones with `omarchy-parent-controls unpair`, then pair again. The relay capability is rotated and the broker immediately stops accepting old phone tokens. Removing the plugin also stops the connector. The iPhone app still requires Apple signing/distribution; no App Store or TestFlight release has been published.

## Implementation limits

The model is an interpreter, not a security boundary. Local checks reject disallowed commands, re-read approvals before desktop execution, and keep privileged parent operations out of the voice vocabulary. Initial live Laya probes showed that labels need task descriptions and that raw model predictions can be wrong; the final bounded pipeline passed the included five text cases. That is a small regression check, not a child-speech accuracy benchmark.

This release does **not** add a general screenshot-driven browser/computer agent or custom model training. Those need separate task-specific evaluation. The managed Hermes sandbox has passed isolated ARM Omarchy VM checks; physical hardware acceptance remains pending. Videos is a restricted app, not a machine-wide guarantee against arbitrary code or every alternate video client.

## Validation

See [managed relay validation](docs/validation/managed-relay.md) for alpha.7 and `FAMILY-VALIDATION.md` for the earlier implementation. The screenshots are real renders of the SwiftUI and Qt source with explicitly labeled sample data, not screenshots from a deployed school computer or physical iPhone.

## Sound and microphones in web apps

The launcher includes a dedicated local audio connection for both playback and microphone input. Chromium retains its normal site microphone permissions. Local dictation uses a separate PulseAudio capture stream. VM testing found and fixed truncated audio through the previous ALSA capture path. Apply the updated installer and reopen web apps; see [audio diagnostics](docs/WEBAPP-AUDIO.md). Physical microphone/speaker validation is still pending.
