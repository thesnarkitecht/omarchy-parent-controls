# Curl installer and service CLI — 0.5.0-alpha.6

Validated October 2, 2026 in the isolated Omarchy ARM VM used for alpha.4.

- 125 parent-controls tests passed on Linux; 124 passed on macOS with the Linux-only bootstrap test skipped.
- Installed the generated alpha.5 archive over alpha.4. PIN, policy and account files remained byte-for-byte unchanged. Controlled mode stayed on.
- Repeated installation with controls off, then ran the restart command. Controls stayed off and the policy service stayed inactive.
- `omarchy-parent-controls version` works as the child. Child execution of the privileged update command without authentication was denied by sudo. The updater, wrapper and version metadata are not child-writable.
- The restart command uses fixed service names and only restarts optional workers when already active. Checked the broker, policy and audio socket were active with controls on.
- Unit tests cover numeric prerelease selection, stable-channel behavior, draft rejection, no downgrades, read-only checks, checksum failure, repository mismatch, archive traversal/symlink/hardlink/device rejection, fixed privilege elevation, saved account selection and installation error reporting.

The release checksum is delivered by the same GitHub repository as the archive, not an independent signing authority. CLI updates take a private settings backup before executing the installer. Installation is not transactional; a failure can require rerunning the update after resolving the reported error. Voice session restarts require logout/login. No physical school computer was modified.

## Interactive public-download check

The alpha.5 public installer authenticated successfully through the child's terminal and installed the controls, but cleanup then failed on root-owned `__pycache__` files in its temporary source tree. Alpha.6 disables bytecode writes during privileged installation (`python3 -I -B`) to avoid leaving those files behind.

The corrected alpha.6 release passed both public-download paths in a child-account pseudo-terminal, using real parent-PIN authentication:

1. Ran the exact README curl command against the published GitHub `bootstrap.sh` and archive. Installation and temporary-directory cleanup both exited successfully.
2. Set only the VM's installed-version marker to alpha.5 to exercise the newer-release branch. Ran the installed `omarchy-parent-controls update` as the child. It requested the PIN, discovered alpha.6 through GitHub, verified/extracted the public archive, created a root-private settings backup and installed it successfully. This exercises the update path; it is not a fresh-machine installation test.
3. Verified version alpha.6, the already-current read-only check, active required services, preserved controlled mode and unchanged PIN/policy/account files. The temporary test PIN and authentication counters were restored to their original values.
4. Reran all 125 Linux parent-controls tests successfully against alpha.6; macOS passed 124 with the expected Linux-only skip.

The isolated VM had no production Laya pairing, so automatic upgrades of an already-paired voice installation remain unverified on a live target. The earlier alpha.4 voice/audio validation is documented separately in FAMILY-VALIDATION.md.
