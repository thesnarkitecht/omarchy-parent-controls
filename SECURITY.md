# Security model

## Intended protection

The controlled user knows their normal login password, can use a terminal, and can ask Hermes to perform tasks. They do not know the parent PIN. Controls are intended to stop routine browser launches, package installations, and requests to the managed Hermes desktop to remove restrictions.

The root broker authenticates mutations with a salted scrypt PIN hash and persisted exponential retry delays. It accepts structured policy operations, never a caller-supplied shell command. PINs travel through stdin and a local Unix socket, not command-line arguments. Policy, launcher code and authentication helpers are root-owned. The dedicated sudo PAM stack checks the parent PIN.

While enabled, executable ACLs deny the child UID access to known browsers, installers, other agents and the raw Hermes Desktop binary. Read-only launcher overrides hide unwanted entries. Bind mounts mark common writable directories noexec/nosuid/nodev. A package-manager hook reapplies the policy after package changes.

Approved Chromium webapps run under a separate locked service account with managed exact-host URL rules, no extensions, no developer tools and a profile the child cannot modify. The child can read its downloaded files. Approved hosts form one combined browser allowlist, not separate isolation per webapp.

The standard Hermes Desktop runs as another locked service account. Its unit has no capabilities, no privilege elevation, read-only system paths, an isolated home, and write access to Projects, Documents and Downloads. Its outgoing network is limited to the configured model IP/port and local backend ports. This limits its embedded browser and subprocesses; it does not replace the upstream agent.

## Explicit limits

- This has not received an independent security audit and is not a formal application allowlist or an adversarial sandbox.
- General terminal networking is allowed. Hostname blocks can be bypassed by alternate domains, direct addressing, proxies or encrypted DNS. The list cannot cover every browser mirror. Download blocking is an extra guardrail, not the primary protection.
- Shell/Python scripts, dynamic code, alternate runtimes and advanced kernel mechanisms are not comprehensively prevented by noexec mounts or a command denylist. Do not promise that a determined programmer cannot assemble another browsing route.
- Network isolation applies to the **managed Hermes Desktop and its descendants**. An arbitrary program or Hermes CLI run directly in the child's terminal uses that user's normal network access. It still lacks the parent PIN and remains subject to root-owned executable restrictions.
- The model server is trusted. A local proxy or a model service that executes tools remotely can weaken the intended isolation. The plugin does not control remote machines.
- The parent panel runs in the child's desktop session. It is not a trusted secure-attention screen and cannot protect a PIN from malicious session-level software. Use it for practical family controls, not hostile multi-user administration.
- Parents can disable the mode with their PIN. Root, trusted recovery media, another privileged account, or physical boot access can change the policy.
- This is not a content filter, screen-time manager, child-monitoring service, or guarantee about approved websites. No browsing activity is sent to the plugin author.

Report suspected bypasses privately to the repository owner. Do not include a parent PIN, credentials, personal files or browser profiles in reports.

The terminal Hermes runtime is installed from a pinned, checksum-verified copy of the official upstream installer. Its browser installation is disabled. Source, native libraries and dependencies are root-owned outside the child home; a symlink exposes the command without making home executable. The official launcher uses an upstream-supported shared payload layout and the child’s existing data directory. Installer binaries bundled in this runtime are included in the controlled-mode denylist. Hermes CLI still runs with the child’s ordinary terminal networking and permissions; this change does not give it the separate managed Desktop network sandbox.
