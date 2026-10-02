# Managed Parent Pocket relay

The current deployment target is **Render Free**, which supplies a permanent `onrender.com` address and managed TLS. No domain, VPS, VPN, inbound laptop port, or per-laptop tunnel is needed. Both endpoints make outbound WebSocket connections. A single small Node service holds only disposable connection state, and devices reconnect after service restarts. No database or persistent disk is required.

**Live deployment:** `https://parent-pocket-relay.onrender.com`, verified on 2026-10-02. `../remote-service.json` now records this origin for source installs and the next laptop release. Public TLS acceptance passed for parent commands, disconnect/reconnect, revocation, and the voice/Laya client exchange. The published laptop installer remains alpha.6 until the alpha.7 release is prepared.

## One-time Render setup

[Deploy the free relay on Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fthesnarkitecht%2Fomarchy-parent-controls%2Ftree%2Fcodex%2Fmanaged-parent-relay)

The repository-root `render.yaml` selects the Free plan, managed Node runtime, locked dependencies and `/health` check. Sign in to Render and review that one free web service. No custom domain or Cloudflare account is needed. Once deployed, run `python3 scripts/activate.py https://YOUR-RELAY.onrender.com` from `relay/`. Activation verifies the public service identity before recording its origin in the next laptop release. Then complete live TLS acceptance and publish the installer.

Render's free service can sleep after 15 minutes without incoming traffic and take about a minute to wake. Normal device reconnection is automatic, but the first remote action after inactivity can fail and need a refresh. Do not promise instant availability. Free instance hours are shared across the workspace (750/month); bandwidth/build quotas also apply. No payment method is needed for an account without verification requirements; if Render requests card verification, the owner must handle it. If no payment method is present, excess usage suspends service rather than billing. Do not enable a paid plan automatically. See [Render's free-service limits](https://render.com/docs/free) and [billing FAQ](https://render.com/docs/faq).

The blueprint intentionally disables automatic deploys from this public template. Normal laptop service updates use the parent-controls CLI. Relay updates are an occasional maintainer deployment; managed hosting removes server administration, not software maintenance.

## Optional Cloudflare deployment

The original Workers/Durable Objects adapter remains available and uses the same encrypted protocol. Its `workers.dev` address also does **not** require buying a domain. With a Cloudflare account, use `pnpm install --frozen-lockfile`, `pnpm test`, `pnpm exec wrangler login`, `pnpm exec wrangler deploy`, then activate the resulting HTTPS origin. This provider is optional; Render does not depend on it.

Each laptop's first **Pair parent phone** automatically creates its own connection credentials, starts the hardened system service, and displays the parent QR. Subsequent pairing reuses the connection. Service restarts and network changes reconnect with bounded randomized backoff. Updates preserve credentials and restart the connector. Unpairing revokes broker tokens and rotates relay access. No family member enters server addresses in normal setup.

The iPhone app must include protocol v2 support from the separate Parent Pocket project. Laya's separate project supports the same relay with `scripts/pair.py --relay HTTPS_ORIGIN ...`; transfer each generated voice enrollment only to its matching laptop. Laya inference still runs on the existing Laya computer, which must remain awake. Local dictation and local commands do not depend on the relay.

## Security and protocol

- Device address: SHA-256 of a random 256-bit device token. Device upgrade requires the corresponding bearer token. Parent relay capability is independent and cannot impersonate the device.
- QR contains a phone-specific parent token, phone ID, public relay origin, device channel, and limited relay capability. It does not contain the device token, parent PIN, or fleet administrator credentials.
- AES-256-GCM encrypts command bodies and replies. HKDF-SHA256 derives separate request/response keys from the decoded phone token, using the UTF-8 phone ID as salt and `parent-pocket/v2/request` or `/response` as info. AAD is `parent-pocket/v2/PHONE/REQUEST_ID/DIRECTION`. Encoding is unpadded base64url of 12-byte random nonce + ciphertext + 16-byte tag.
- Only the root broker stores parent message keys; the unprivileged connector receives routing credentials through systemd `LoadCredential`. The broker authenticates and validates the existing fixed parent operations. There is no remote shell or arbitrary URL forwarding.
- The hosting provider sees IPs, channels, timing, ciphertext lengths, and routing capabilities. It cannot decrypt or forge a successful device response without endpoint keys. Availability still depends on the provider and the network. Endpoint compromise is outside this protection.
- The Render adapter keeps only connection state and a hash of the parent routing capability in memory. The optional Cloudflare adapter persists that capability hash in its Durable Object. No messages, transcripts, policy, progress, or screen images are persisted there. Application logging is disabled; provider infrastructure may still retain its own operational metadata.
- At most eight phone sockets per device, one outstanding request per phone socket, bounded frames and message rates. Connection attempts are rate limited per source IP; the Render adapter also limits active device rooms to 32 and caps socket output buffering. Public self-enrollment can still be abused to consume free quotas; monitor provider usage before expanding beyond a small trusted deployment.
- Pending actions are not queued while a device is offline. Parent request timestamps and existing idempotency receipts guard against stale/replayed changes. Voice requests expire after 15 seconds and return only an action from the submitted, enrolled allowlist.
- No background iOS push notifications or local-network/Bluetooth discovery are implemented in this change. Both local and remote use the same managed connection.

## Validation

`pnpm test` checks both adapters, including actual Node sockets, routing and rejection logic. `pnpm start` starts the Render runtime on port 8788; run `RELAY_TEST_URL=ws://127.0.0.1:8788 python test/integration.py` for the encrypted acceptance test. `pnpm dev` starts the real local Workers runtime. `python3 test/integration.py` then exercises real sockets, broker encryption, offline behavior, reconnection, and revocation with disposable credentials. Swift/Python interoperability is additionally checked by Parent Pocket's `Tests/SealedChecks.swift`. Local runtime checks do not replace a deployed TLS round trip or physical-device acceptance.

References: [WebSocket hibernation](https://developers.cloudflare.com/durable-objects/best-practices/websockets/), [free-plan quotas](https://developers.cloudflare.com/durable-objects/platform/pricing/).

The optional GitHub Actions template is in `ci/github-actions.yml.example`. Checks were run locally; automated relay CI is not enabled by this branch because the connected GitHub authorization cannot install workflows.
