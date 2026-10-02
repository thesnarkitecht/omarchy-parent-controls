# Security model

## Intended protection

The controlled user knows their normal login password, can use a terminal, and can ask Hermes to perform tasks. They do not know the parent PIN. Controls are intended to stop routine browser launches, package installations, and requests to the managed Hermes desktop to remove restrictions.

The root broker authenticates mutations with a salted scrypt PIN hash and persisted exponential retry delays. It accepts structured policy operations, never a caller-supplied shell command. PINs travel through stdin and a local Unix socket, not command-line arguments. Policy, launcher code and authentication helpers are root-owned. The dedicated sudo PAM stack checks the parent PIN.

While enabled, executable ACLs deny the child UID access to known browsers, system installers, other agents and the raw Hermes Desktop binary. Read-only launcher overrides hide unwanted entries. Bind mounts mark common writable directories noexec/nosuid/nodev. A package-manager hook reapplies the policy after package changes.

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

## Managed terminal Hermes (0.5.0-alpha.2)

The terminal runtime comes from a pinned, checksum-verified official upstream installer, with browser installation disabled. The managed `hermes` command always enters a bubblewrap namespace before starting upstream code. Missing bubblewrap, unsupported user namespaces or mount failures stop it; there is no unsandboxed fallback. The launcher refuses root and other accounts. This implementation still needs the included Linux acceptance check on target hardware.

The namespace has read-only system programs and Hermes runtime, a private process namespace, no capabilities, no privilege elevation, disabled nested user namespaces, a new terminal session, fresh `/tmp` and `/run`, and an explicit environment. It does not mount the real home, parent policy/PIN storage, broker socket, system/session D-Bus, Wayland, X11, SSH-agent socket, or host service-manager sockets. Agent-generated commands inherit the namespace. Ordinary system files needed for DNS, accounts and TLS are mounted individually; `/etc` as a whole is not exposed. Provider keys explicitly passed from the child environment and the agent's own configuration remain available to Hermes; parent credentials must never be placed there.

Writable persistent mounts are `/workspace` from `/var/lib/omarchy-coding/UID` and the agent's `.hermes` state from `/var/lib/omarchy-hermes-state/UID`. Their parent directories are root-owned and not writable by the child; leaf directories are private and child-owned. The child cannot replace a leaf with a symlink. Existing `~/.hermes` is left untouched and is not automatically imported. Root-owned runtime updates still require parent authorization.

Projects are deliberately executable, so compilers, virtual environments, package scripts and the normal terminal remain useful. `~/Projects/Workspace` links to the coding directory when that name is free. This is an explicit exception to common-directory `noexec` guardrails. It does not grant administrative rights.

**Scope:** the managed CLI has filesystem/process isolation, but shares normal terminal networking, including reachable LAN/localhost TCP services. This is different from the managed Desktop's network restriction. Do not put unauthenticated administration behind a network endpoint. Ordinary terminals can run arbitrary child-account code, including manually invoking another runtime outside this wrapper. The plugin cannot guarantee every independently launched agent is sandboxed, or that an unrestricted terminal cannot bypass content filtering. A VM or a much narrower terminal policy would be needed for that stronger requirement. Both managed and independent child processes still lack root authority and the parent PIN. The existing warning about entering a PIN in a potentially compromised desktop session applies.

Bubblewrap's own [security guidance](https://github.com/containers/bubblewrap#security) describes why the filesystem/socket policy, new session and namespace configuration matter; bubblewrap alone is not a complete policy.
