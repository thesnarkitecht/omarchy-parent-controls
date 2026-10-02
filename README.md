# Parent Controls for Omarchy

**0.5.0-alpha.4 — source preview.** Validates Linux sandbox isolation and web-app audio in an Omarchy VM, fixes local voice capture and Wayland web-app targeting, and includes URL-first approvals, a sandbox launcher for terminal Hermes, executable coding workspaces, integrated voice, child requests, the parent-iPhone API and Little Screen. See [the family setup guide](FAMILY.md) and [new validation](FAMILY-VALIDATION.md). Parent Pocket and the Laya host service remain separate projects. This source update does not publish a new release or deploy to school computers; Physical school-machine and iPhone testing remains pending.

Keep the normal Omarchy desktop, with parent-approved webapps and a private parent PIN for administration.

**The earlier 0.4 beta was validated on an Omarchy 4 ARM VM. The new 0.5 features have not been validated on that VM.** Start with a supervised installation and check your child's workflow before relying on it. Fresh-machine and x86_64 testing are still needed. This is an independent plugin, not an official or security-audited Omarchy product.

## What children can use

- Terminal, Files, a text editor, calculator, document/image/media viewers and archives.
- Installed themes, tiling, screenshots, sound, displays, Wi-Fi and Bluetooth.
- Chromium webapps for the exact HTTPS sites a parent approves. Downloads go to the child's Downloads folder.
- The installed, unmodified Hermes Desktop, when configured with a supported local model endpoint.

Normal terminal network requests work. Known browser-download hosts are blocked. General browsers, other AI launchers, communication apps and system package installers are hidden or denied. Runtime commands (`mise`, `uv`/`uvx`, `pip`/`pipx`, `npm`/`npx`, `pnpm`, and `yarn`) are allowed, including after upgrading older denylist settings. Downloaded native executables cannot run from the common writable directories covered by the policy.

This is a set of practical guardrails for young children who know their login password. A terminal with networking remains powerful. Read [SECURITY.md](SECURITY.md) for the limits.

Web-app speaker and microphone access use a dedicated local audio connection while School Voice dictation stays on the normal desktop audio service. See [audio setup and diagnostics](docs/WEBAPP-AUDIO.md).

Remote parent access can use the free Tailscale Personal plan for eligible family use. [Compare free options](docs/REMOTE-ACCESS.md), including NetBird and ZeroTier.

## Requirements

- Omarchy 4 on Arch Linux with systemd, a standard `/home/NAME` desktop account, and working administrator access for initial setup.
- One controlled desktop account per computer. Existing PIN and website approvals survive updates.
- Python, PySide6, Chromium, nftables and ACL tools; the installer installs these through pacman. First installation also installs Calculator, Papers, File Roller and Text Editor unless `--skip-apps` is supplied. Updates preserve the existing app set.
- Managed Hermes **Desktop** requires a root-owned upstream desktop binary and a local model server at a fixed IP/port. The separate terminal Hermes supports provider configuration within its sandbox and requires bubblewrap with unprivileged user namespaces. The installer installs bubblewrap.

## Install from a reviewed release

The version-pinned installer verifies the archive's SHA-256 before extracting it:

```bash
# This development version is not published. From the reviewed source:
bash install.sh
```

Download and extract the published release, verify its SHA-256 checksum, and run:

```bash
bash install.sh
```

Initial installation asks for the existing administrator password, then an 8–12 digit parent PIN. The child login password continues to unlock the desktop but no longer authorizes sudo. Setup removes privileged group membership and locks direct root-password login. The parent PIN is required for sudo even while controlled mode is off.

For an existing local Hermes installation, supply its real ELF executable and model endpoint:

```bash
bash install.sh --hermes-binary /opt/hermes-desktop/Hermes --model-host 192.168.1.10 --model-port 11434
```

The path/address above are examples; use your actual installation. Existing managed Desktop configuration is preserved on upgrade. The separate terminal Hermes integration uses the official upstream installer as described below.

The release builder produces `bootstrap.sh` with an embedded archive checksum. This checks the downloaded archive against the release bootstrap; it is not an independent cryptographic signature. Installing only the QML plugin does **not** install the privileged controls.

## Parent controls

Open the **lock icon** in the bar. Turn controlled mode off/on, add or remove a webapp, or change the PIN. Each change asks for the PIN. Turning mode off restores the normal app/menu access and refreshes the launcher so all previously visible installed apps reappear; Parents stays available for quickly turning it back on. Switching modes never installs or uninstalls applications. Approved webapps appear in the launcher immediately after approval, in either mode.

Use **Edit** to add related sites to an existing webapp. For example, `https://x.ai` and `https://grok.com` are separate approvals; include both to follow the Grok button. Approved sites may open new windows, while other destinations remain blocked. **Clear data…** requires the parent PIN and resets that webapp’s history, cookies and cache, signing it out.

The normal keyboard shortcuts stay loaded. Browser shortcuts open the approved-app launcher, webapp shortcuts pass through the approved-site check, and unavailable app shortcuts show a parent-approval notice. Turning controls off restores their original actions.

**Parent tools**, available with controls off and PIN approval, opens Omarchy’s agent picker or Windows VM setup/launcher. Agent selection does not install every agent: Omarchy installs only what the parent explicitly chooses. The selected default is captured when controls are turned on; the plugin no longer forces the agent shortcut to Hermes Desktop. When Hermes is selected, installing/upgrading the plugin prepares its official CLI in a root-owned runtime outside the child’s home. Other home-installed agent runtimes can still be affected by the executable restrictions. Windows uses the stock Omarchy installer, with its privileged actions routed through the parent-PIN sudo prompt. Shut Windows down before enabling controls; the Windows guest needs its own parental controls.

Add `https://ollama.com` as a first webapp if desired. Approval is by exact HTTPS host: a redirect or login hosted elsewhere needs a separate approved origin. All approved sites share Chromium's managed allowlist. Site approval does not make the site's own content child-safe.

Controls are designed to persist across reboot. The child user manager and display manager wait for the persisted policy; a failed policy or missing controlled launcher mount prevents that session starting instead of silently opening an unrestricted desktop.

## Remove or recover

From the terminal, enter the parent PIN for:

```bash
sudo python3 -I /usr/local/lib/omarchy-kids/remove.py
```

Removal restores the original administrator groups, root-password state, desktop configuration, command ACLs and hosts entries. It leaves installed applications, documents, webapp data, and private PIN/policy/recovery backups for reinstall. Locked service accounts remain to preserve ownership of downloaded files. It never deletes family files.

First installation starts a 15-minute recovery timer before changing authentication. Successful setup verifies PIN authentication and cancels it. If setup fails, keep the machine running so recovery can restore administrator access.

If the PIN is lost or the desktop cannot start, boot trusted recovery media, mount the installation, enter it with `arch-chroot`, and run the same removal command with `--recovery` as root. Physical recovery access can also bypass the controls; protect boot settings if that matters for your family.

## Development and release

```bash
python3 -m unittest discover -s tests -v
python3 packaging/build_release.py --repository OWNER/omarchy-parent-controls --output /tmp/parent-controls-release
```

See [VALIDATION.md](VALIDATION.md) for release gates and recorded evidence. Publishing to GitHub and acceptance into the Omarchy marketplace are separate steps.

## Hermes in the terminal

If Hermes is the selected Omarchy agent, installation and upgrades automatically prepare its CLI using the official upstream shell installer, downloaded with curl and verified against a pinned SHA-256. It runs with `--skip-browser --non-interactive` and a pinned upstream commit. No additional browser or Desktop is installed. Program files and dependencies are under `/opt/omarchy-parent-controls-hermes`; `hermes` is exposed in `/usr/local/bin` and through a symlink in `~/.local/bin`, so the home-directory `noexec` restriction stays in place.

Use `bash install.sh --with-hermes` to install and approve Hermes when it is not already the selected agent. The managed command requires a sandbox for every invocation, including configuration and model setup; it never falls back to normal execution. It runs as the child, never as root. Run `hermes model` to configure a provider, then `hermes` to code.

Use `~/Projects/Workspace` for projects (the actual directory is `/var/lib/omarchy-coding/UID`). Shells, Git, compilers, package tooling and virtual environments can execute there. If that friendly name already exists, it is preserved; use the actual directory. Hermes mounts projects as `/workspace`, preserving a current subdirectory; starting elsewhere opens the workspace root. It cannot see the rest of the child's home or the desktop/admin sockets. Internet access remains available for providers and dependencies.

Agent settings and conversations now persist in `/var/lib/omarchy-hermes-state/UID`, mounted as `/home/agent/.hermes`. Existing `~/.hermes` and the prior CLI launcher are preserved, but the old state is not automatically imported into the sandbox. This separation avoids exposing unrelated home/session configuration. Normal terminals remain outside the Hermes sandbox; see [SECURITY.md](SECURITY.md) for that important scope limit.

After installation, run `python3 tests/integration_hermes_sandbox.py` from the reviewed source as the child, without sudo. It tests the actual namespace, privilege restrictions, hidden parent/session paths, executable project scripts, Python venv, Git and the upstream Hermes launcher. This check has not yet been run on a target machine for alpha.2.

If you select Hermes later, turn controls off, then use **Parent tools → Install or repair Hermes**. The terminal requests the parent PIN through sudo. This does not change the chosen agent. Return to controlled mode afterward. The same repair is available as `sudo python3 -I /usr/local/lib/omarchy-kids/hermes_install.py`. Program updates require parent authorization; Hermes cannot rewrite its system-owned runtime. Removing parental controls retains the installed Hermes command and family data.
