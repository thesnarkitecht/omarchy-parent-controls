# Parent Controls, now with voice and Little Screen

This is the **0.5.0-alpha.3 source preview**. It extends the existing Omarchy Parent Controls project with URL-first approvals and a managed Hermes coding sandbox. No school computers were changed, and no release was published to GitHub.

## What belongs where

- **This repository**: the Omarchy plugin, the privileged approval broker, the private remote relay, Little Screen, child requests, and the integrated voice module in `voice/`.
- **Parent Pocket**: a separate native iOS project for parents, supplied separately. It connects to the plugin on each school computer; its source is not included here.
- **Laya Control**: the separate decision service on the shared host, supplied separately; its source is not included here. It suggests bounded actions; it cannot execute desktop commands or approve requests.

## The parent experience

Open Parent Pocket and unlock with Face ID, Touch ID, or the device passcode. Choose a paired school computer. Requests show exactly what the child wants and their optional reason. **Allow** or **Not now** takes effect without an additional confirmation dialog. The app shows success only after the computer acknowledges the change.

In Controls, tap **Paste a link · allow an app**. Paste the web-app URL; its name is optional. The page explains that approval covers the exact hostname, and the pasted page becomes its starting page. Bare hostnames gain `https://`; insecure schemes, embedded credentials and local addresses are rejected. Repeat pastes update the name without duplicating the same starting URL. No app installation is triggered by a website approval.

The Little Screen tab lets a parent add or remove individual YouTube video links. Video titles are optional too. The Controls tab also manages voice and wake-word settings. Pairing credentials stay in the iPhone Keychain, are excluded from migration to another device, and never go to Laya. The app locks when backgrounded.

The app refreshes while open and supports pull to refresh. **Background push notifications are not implemented.** The school computer must be awake and reachable; requests are not queued as delayed remote commands. Child requests themselves persist on the computer until reviewed.

## The girls' experience

Little Screen is an app on their normal Omarchy desktop. Its entire library consists of individual parent-approved video IDs. There is no discovery feed, recommendations, channel approval, playlist approval, next-video autoplay, or general browser inside the app. Playback opens a dedicated player, and the app checks approval immediately before playing and every two seconds afterward. Revocation or loss of the approval service stops playback. Availability depends on YouTube and the installed player/extractor; restricted, removed or unsupported videos may not play.

The request form supports a video, an exact HTTPS website, or an already installed supported school app. Children can select a school app by name. Requests grant no access until approved. A website approval allows the **exact hostname** shown, not just one page; redirects and login hosts need separate approval. App approvals do not install software.

Voice uses local wake detection and transcription: **“Hey Laya” → sentence → approved app/action**. The microphone indicator, mute button, voice dictation and hotkeys remain. Voice uses the plugin's live approvals rather than a second app list. “Help me write a story” can select Text Editor; “I want to practice math” can select Math Match when installed and approved. Microphone permission can be turned off by the parent remotely, and the child can always mute it locally.

## Install on a school computer

Use a supervised test computer first; this new integrated release has not been run on physical Omarchy hardware. The earlier parent-controls version has separate VM validation, which does not validate these new features.

From the reviewed `omarchy-parent-controls` source directory:

```bash
bash install.sh
```

Existing parent settings survive. The installer includes Little Screen, `mpv`, `yt-dlp`, QR-code support and bubblewrap. The remote relay is installed but **not enabled or exposed automatically**.

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

For a family using personal computers, Tailscale has a free Personal plan; no paid subscription or router port forwarding is required for this design. See [the free-options comparison](docs/REMOTE-ACCESS.md) for current limits and alternatives. The current app supports Tailscale endpoints; NetBird and ZeroTier are alternatives to evaluate, not implemented replacements.

1. Install and connect Tailscale on the phone and school computer using your own tailnet. Restrict access to the school's HTTPS service to parent devices with your tailnet access policy. Enable HTTPS certificates for that tailnet.
2. On the school computer, start the private loopback relay and expose it through **Tailscale Serve**:

   ```bash
   sudo systemctl enable --now omarchy-kids-remote.service
   sudo tailscale serve --bg http://127.0.0.1:43127
   ```

   Check `tailscale serve status` first if you already use Serve on this machine; preserve any existing routing. Use private Serve, **not public Funnel**. No router port-forwarding is needed. [Tailscale Serve documentation](https://tailscale.com/docs/reference/tailscale-cli/serve).

3. Copy the HTTPS `.ts.net` origin shown by Serve into the pairing command:

   ```bash
   sudo /usr/local/lib/omarchy-kids/run pair_parent \
     --endpoint https://YOUR-COMPUTER.YOUR-TAILNET.ts.net \
     --name "School laptop" --qr
   ```

   The existing parent PIN authorizes sudo. Scan the QR from Parent Pocket, or paste its pairing JSON. Treat that code as a parent credential. The computer stores only its token hash. Never send it to a child, Laya, an agent, or a public repository.

4. Open `ParentPocket.xcodeproj` from the separate Parent Pocket project in Xcode, choose your signing team and a unique bundle identifier, and run it on your iPhone. An unsigned arm64 iOS build succeeded here; installation on a real phone requires your Apple signing setup. Nothing has been submitted to TestFlight or the App Store.

To revoke **all paired parent phones for one computer**, run:

```bash
sudo /usr/local/lib/omarchy-kids/run pair_parent --revoke-all
```

Pair again afterward. Removing the Parent Controls plugin also revokes its phone tokens. Its remote relay is stopped during removal. Voice then fails closed because its approval broker is gone; downloaded models and family files are retained.

## Implementation limits

The model is an interpreter, not a security boundary. Local checks reject disallowed commands, re-read approvals before desktop execution, and keep privileged parent operations out of the voice vocabulary. Initial live Laya probes showed that labels need task descriptions and that raw model predictions can be wrong; the final bounded pipeline passed the included five text cases. That is a small regression check, not a child-speech accuracy benchmark.

This release does **not** add a general screenshot-driven browser/computer agent or custom model training. Those need separate task-specific evaluation. The new managed Hermes sandbox is implemented but still needs Linux target validation. Little Screen is a restricted app, not a machine-wide guarantee against arbitrary code or every alternate video client.

## Validation

See `FAMILY-VALIDATION.md`. The screenshots are real renders of the SwiftUI and Qt source with explicitly labeled sample data, not screenshots from a deployed school computer or physical iPhone.

## Sound and microphones in web apps

The alpha.3 launcher includes a dedicated local audio connection for both playback and microphone input. Chromium retains its normal site microphone permissions. Local dictation remains separate and unchanged. Apply the updated installer and reopen web apps; see [audio diagnostics](docs/WEBAPP-AUDIO.md). Physical microphone/speaker validation is still pending.
