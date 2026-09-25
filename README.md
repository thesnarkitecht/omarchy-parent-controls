# Parent Controls for Omarchy

Keep the normal Omarchy desktop, with parent-approved webapps and a private parent PIN for administration.

**Community beta, validated on an Omarchy 4 ARM VM.** Start with a supervised installation and check your child's workflow before relying on it. Fresh-machine and x86_64 testing are still needed. This is an independent plugin, not an official or security-audited Omarchy product.

## What children can use

- Terminal, Files, a text editor, calculator, document/image/media viewers and archives.
- Installed themes, tiling, screenshots, sound, displays, Wi-Fi and Bluetooth.
- Chromium webapps for the exact HTTPS sites a parent approves. Downloads go to the child's Downloads folder.
- The installed, unmodified Hermes Desktop, when configured with a supported local model endpoint.

Normal terminal network requests work. Known browser-download hosts are blocked. General browsers, other AI launchers, communication apps and package installers are hidden or denied. Downloaded native executables cannot run from the common writable directories covered by the policy.

This is a set of practical guardrails for young children who know their login password. A terminal with networking remains powerful. Read [SECURITY.md](SECURITY.md) for the limits.

## Requirements

- Omarchy 4 on Arch Linux with systemd, a standard `/home/NAME` desktop account, and working administrator access for initial setup.
- One controlled desktop account per computer. Existing PIN and website approvals survive updates.
- Python, PySide6, Chromium, nftables and ACL tools; the installer installs these through pacman. First installation also installs Calculator, Papers, File Roller and Text Editor unless `--skip-apps` is supplied. Updates preserve the existing app set.
- Managed Hermes currently requires a root-owned upstream desktop binary and an existing local model server reachable by a fixed IP/port. Cloud-provider-only Hermes setups are not supported by this release.

## Install from a reviewed release

The version-pinned installer verifies the archive's SHA-256 before extracting it:

```bash
curl -fsSL https://github.com/thesnarkitecht/omarchy-parent-controls/releases/download/v0.4.0-beta.2/bootstrap.sh | bash
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

The path/address above are examples; use your actual installation. This plugin does not download a replacement Hermes build. Existing managed configuration is preserved on upgrade.

The release builder produces `bootstrap.sh` with an embedded archive checksum. This checks the downloaded archive against the release bootstrap; it is not an independent cryptographic signature. Installing only the QML plugin does **not** install the privileged controls.

## Parent controls

Open **Parents** in the bar. Turn controlled mode off/on, add or remove a webapp, or change the PIN. Each change asks for the PIN. Turning mode off restores the normal app/menu access and refreshes the launcher so all previously visible installed apps reappear; Parents stays available for quickly turning it back on. Switching modes never installs or uninstalls applications. Approved webapps appear in the launcher immediately after approval, in either mode.

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
