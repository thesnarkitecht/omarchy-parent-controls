# Managed Parent Pocket relay

Cloudflare Workers + SQLite Durable Objects provide a stable `workers.dev` address with managed TLS. No domain, VPS, VPN, inbound laptop port, or per-laptop tunnel is needed. Both endpoints make outbound WebSocket connections. Idle device sockets use Durable Object hibernation. The Workers Free plan has hard quotas; this is not an unlimited service or an uptime guarantee.

The source is ready for deployment. **It is not activated while `../remote-service.json` has a null endpoint.** No temporary preview URL is used as a permanent service.

## One-time maintainer setup

Use Node 22 or later and pnpm 11. Install dependencies using the committed lockfile:

```sh
pnpm install --frozen-lockfile
pnpm test
pnpm exec wrangler login
pnpm exec wrangler deploy
```

Keep the account on the Free plan unless its owner explicitly chooses otherwise. Use the resulting HTTPS `workers.dev` origin with `python3 scripts/activate.py https://YOUR-WORKER.YOUR-ACCOUNT.workers.dev`. Activation checks the deployed health response before recording the public address in the laptop release. This address is public configuration, not a credential. Build/publish the parent-controls release only after deployment and the live acceptance checks pass.

Each laptop's first **Pair parent phone** automatically creates its own connection credentials, starts the hardened system service, and displays the parent QR. Subsequent pairing reuses the connection. Service restarts and network changes reconnect with bounded randomized backoff. Updates preserve credentials and restart the connector. Unpairing revokes broker tokens and rotates relay access. No family member enters server addresses in normal setup.

The iPhone app must include protocol v2 support from the separate Parent Pocket project. Laya's separate project supports the same relay with `scripts/pair.py --relay HTTPS_ORIGIN ...`; transfer each generated voice enrollment only to its matching laptop. Laya inference still runs on the existing Laya computer, which must remain awake. Local dictation and local commands do not depend on the relay.

## Security and protocol

- Device address: SHA-256 of a random 256-bit device token. Device upgrade requires the corresponding bearer token. Parent relay capability is independent and cannot impersonate the device.
- QR contains a phone-specific parent token, phone ID, public relay origin, device channel, and limited relay capability. It does not contain the device token, parent PIN, or fleet administrator credentials.
- AES-256-GCM encrypts command bodies and replies. HKDF-SHA256 derives separate request/response keys from the decoded phone token, using the UTF-8 phone ID as salt and `parent-pocket/v2/request` or `/response` as info. AAD is `parent-pocket/v2/PHONE/REQUEST_ID/DIRECTION`. Encoding is unpadded base64url of 12-byte random nonce + ciphertext + 16-byte tag.
- Only the root broker stores parent message keys; the unprivileged connector receives routing credentials through systemd `LoadCredential`. The broker authenticates and validates the existing fixed parent operations. There is no remote shell or arbitrary URL forwarding.
- Cloudflare sees IPs, channels, timing, ciphertext lengths, and routing capabilities. It cannot decrypt or forge a successful device response without endpoint keys. Availability still depends on Cloudflare and the network. Endpoint compromise is outside this protection.
- Relay storage contains only a hash of the parent routing capability. No messages, transcripts, policy, progress, or screen images are persisted there. Application logging is disabled; provider infrastructure may still retain its own operational metadata.
- At most eight phone sockets per device, one outstanding request per phone socket, bounded frames and message rates. Connection attempts are rate limited per source IP. Public self-enrollment can still be abused to consume free quotas; monitor provider usage before expanding beyond a small trusted deployment.
- Pending actions are not queued while a device is offline. Parent request timestamps and existing idempotency receipts guard against stale/replayed changes. Voice requests expire after 15 seconds and return only an action from the submitted, enrolled allowlist.
- No background iOS push notifications or local-network/Bluetooth discovery are implemented in this change. Both local and remote use the same managed connection.

## Validation

`pnpm test` checks routing and rejection logic. `pnpm dev` starts the real local Workers runtime. `python3 test/integration.py` then exercises real sockets, broker encryption, offline behavior, reconnection, and revocation with disposable credentials. Swift/Python interoperability is additionally checked by Parent Pocket's `Tests/SealedChecks.swift`. Local runtime checks do not replace a deployed TLS round trip or physical-device acceptance.

References: [WebSocket hibernation](https://developers.cloudflare.com/durable-objects/best-practices/websockets/), [free-plan quotas](https://developers.cloudflare.com/durable-objects/platform/pricing/).
