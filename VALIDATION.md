# Release validation — 0.4.0-beta.2

Community beta tested September 25, 2026 on Arch Linux ARM, Omarchy 4.0.3, kernel 7.2.6. The existing desktop account is the controlled account. This is a supervised-rollout release, not a claim of comprehensive security or compatibility.

## Launcher update — beta.2

- 39 unit/package tests pass on the ARM VM, including readable atomic launcher publication, add/remove in both launcher directories, and refusing a controlled session when its overlay is missing.
- A running Quickshell desktop-entry provider discovered GitHub immediately after its application directory was replaced, observed removal, and found the approved webapp without a controlled overlay. Restarting the provider after restoring the original directory made the original installed editor visible again. This uses isolated test directories and Qt's offscreen platform, without changing real family approvals.
- An isolated Linux user/mount namespace reproduced the same-filesystem bind mount detection bug. The corrected code detected the mount and detached two stacked controlled layers, revealing the original app without installing, removing, or modifying it.
- Controlled-mode transitions reconnect the shell's launcher watches after changing mounts. Mode switches never install or uninstall packages. Upgrades no longer add optional everyday apps.
- Startup now orders the child's user manager after policy application, covering TTY/UWSM and lingering sessions as well as display-manager logins. The boot guard additionally verifies the controlled launcher mount. The new startup gate has unit and systemd dependency validation, and passed its read-only check against the VM’s actual active controlled mount; an actual reboot with beta.2 on the affected computer remains to be verified.

## Previous beta.1 validation on the VM

- All 32 unit/package tests, with no skips: PIN verification and rotation, persisted retry backoff, rejected malformed policies/URLs, exact-host browser rules, reversible hosts/NSS changes, reboot-aware mount tracking, busy-mount restoration, deterministic release generation, and actual bootstrap rejection of a modified archive before extraction.
- Packaged installer upgrade, removal and reinstall. Parent PIN and website approvals survived. Original administrator groups and authentication were restored during removal.
- Controlled mode off/on restored normal application access, retained the Parents toggle and kept the desktop running. Busy mounts retain their original permissions until they can detach safely.
- The actual recovery service restored administration when setup was marked unconfirmed. The recovery path restores authentication before attempting UI/filesystem cleanup.
- Child terminal HTTPS requests succeeded; known browser-download host lookups were blocked. Direct Chromium and package-manager execution, passwordless sudo, a copied native executable, and writes to root-owned policy were denied.
- The managed Hermes account could not connect to an arbitrary external HTTPS address. The unmodified Hermes agent returned a real response from the configured local model while running as that account.
- Both the unmodified Hermes Desktop and Ollama Chromium webapp rendered in the normal desktop. Ollama's icon was present. An actual Chromium window navigating to unapproved example.com displayed “This page is blocked.”
- Following a real reboot, the enabled policy and broker started, all terminal/download/execution/network guard checks passed again, and Hermes ran. The user closed Ollama during the early automated window check. A subsequent normal launcher invocation after login reopened Ollama and visually loaded the page, with both managed services active.
- Omarchy's plugin validator accepted the public namespace, `thesnarkitecht.kids-lockdown`.

## Evidence and limits

The VM retains acceptance logs in `/var/log/omarchy-parent-controls-*-check.log` and `/var/log/omarchy-kids-managed-desktop-check.log`. Local screenshots record the blocked browser and the post-reboot desktop. These logs and browser/model profiles are not bundled in the public release.

The beta.1 source bundle was installed on the development VM. Beta.2 launcher tests run against extracted release code without replacing the installed privileged service. The checksum bootstrap was tested with both valid and deliberately modified downloads.

A clean installation on a separate machine, x86_64 desktop compatibility, cloud-only Hermes providers, and an independent security audit remain unverified. Managed Hermes in this release requires an already installed root-owned desktop binary and a configured local model endpoint. General terminal networking remains enabled; see SECURITY.md for the resulting limits.
