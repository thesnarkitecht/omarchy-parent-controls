# Parent Controls for Omarchy

Keep the normal Omarchy desktop, with parent-approved webapps and a private parent PIN for administration.

**Community beta, validated on an Omarchy 4 ARM VM.** Start with a supervised installation and check your child's workflow before relying on it. Fresh-machine and x86_64 testing are still needed. This is an independent plugin, not an official or security-audited Omarchy product.

## What children can use

- Terminal, Files, a text editor, calculator, document/image/media viewers and archives.
- Installed themes, tiling, screenshots, sound, displays, Wi-Fi and Bluetooth.
- Chromium webapps for the exact HTTPS sites a parent approves. Downloads go to the child's Downloads folder.
- The installed, unmodified Hermes Desktop, when configured with a supported local model endpoint.

Normal terminal network requests work. Known browser-download hosts are blocked. General browsers, other AI launchers, communication apps and system package installers are hidden or denied. Runtime commands (`mise`, `uv`/`uvx`, `pip`/`pipx`, `npm`/`npx`, `pnpm`, and `yarn`) are allowed, including after upgrading older denylist settings. Downloaded native executables cannot run from the common writable directories covered by the policy.

This is a set of practical guardrails for young children who know their login password. A terminal with networking remains powerful. Read [SECURITY.md](SECURITY.md) for the limits.

## Requirements

- Omarchy 4 on Arch Linux with systemd, a standard `/home/NAME` desktop account, and working administrator access for initial setup.
- One controlled desktop account per computer. Existing PIN and website approvals survive updates.
- Python, PySide6, Chromium, nftables and ACL tools; the installer installs these through pacman. First installation also installs Calculator, Papers, File Roller and Text Editor unless `--skip-apps` is supplied. Updates preserve the existing app set.
- Managed Hermes currently requires a root-owned upstream desktop binary and an existing local model server reachable by a fixed IP/port. Cloud-provider-only Hermes setups are not supported by this release.

## Install from a reviewed release

The version-pinned installer verifies the archive's SHA-256 before extracting it:

```bash
curl -fsSL https://github.com/thesnarkitecht/omarchy-parent-controls/releases/download/v0.4.0-beta.3/bootstrap.sh | bash
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

Existing `~/.hermes` settings, credentials and conversations are preserved. The previous CLI launcher is backed up before replacing it. Open a fresh terminal and run `hermes`; if no provider has been configured yet, run `hermes model`. The CLI runs as the logged-in user, never as root.

If you select Hermes later, turn controls off, then use **Parent tools → Install or repair Hermes**. The terminal requests the parent PIN through sudo. This does not change the chosen agent. Return to controlled mode afterward. The same repair is available as `sudo python3 -I /usr/local/lib/omarchy-kids/hermes_install.py`. Program updates require parent authorization; Hermes cannot rewrite its system-owned runtime. Removing parental controls retains the installed Hermes command and family data.
