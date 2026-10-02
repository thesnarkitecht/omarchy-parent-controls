# Curl installer and service CLI — 0.5.0-alpha.5

Validated October 2, 2026 in the isolated Omarchy ARM VM used for alpha.4.

- 125 parent-controls tests passed on Linux; 124 passed on macOS with the Linux-only bootstrap test skipped.
- Installed the generated alpha.5 archive over alpha.4. PIN, policy and account files remained byte-for-byte unchanged. Controlled mode stayed on.
- Repeated installation with controls off, then ran the restart command. Controls stayed off and the policy service stayed inactive.
- `omarchy-parent-controls version` works as the child. Child execution of the privileged update command without authentication was denied by sudo. The updater, wrapper and version metadata are not child-writable.
- Restarted the broker, active policy/audio workers and active optional remote service through fixed service names. Checked the broker, policy and audio socket were active with controls on.
- Unit tests cover numeric prerelease selection, stable-channel behavior, draft rejection, no downgrades, read-only checks, checksum failure, repository mismatch, archive traversal/symlink/hardlink/device rejection, fixed privilege elevation, saved account selection and installation error reporting.

The release checksum is delivered by the same GitHub repository as the archive, not an independent signing authority. CLI updates take a private settings backup before executing the installer. Installation is not transactional; a failure can require rerunning the update after resolving the reported error. Voice session restarts require logout/login. No physical school computer was modified.
