# Automatic remote parent access

The new default is the managed encrypted relay in [`relay/`](../relay/README.md). It uses Cloudflare Workers and hibernating Durable Objects on a permanent `workers.dev` address. No VPN, custom domain, router forwarding, or server administration is required. A maintainer deploys it once; each laptop connects outward automatically after pairing. The parent app needs the corresponding protocol-v2 build.

**Deployment is pending account access.** `remote-service.json` deliberately has no endpoint until a permanent deployment passes validation. The published alpha.6 release still uses the older direct HTTPS setup. Source changes alone do not activate a hosted service.

After activation: open the laptop lock icon → **Pair parent phone** → enter the parent PIN → scan with Parent Pocket. There is no URL to paste in normal pairing. `omarchy-parent-controls pair` does the same from a terminal. `omarchy-parent-controls unpair` revokes all phones; `omarchy-parent-controls resume` provides a PIN-authorized local recovery command.

The encrypted relay carries only bounded parent operations and Laya suggestion requests. Laya audio capture and transcription stay on the laptop; actions are checked and executed on the laptop. Local dictation continues without the relay. The laptop and the Laya host must be awake for their respective remote functions. Offline commands are never queued for later execution.

Cloudflare manages the host and public certificates. This still needs ordinary software updates, an active account, and available free-plan quota; it is not an unlimited or guaranteed-uptime service. Nothing enables a paid plan automatically. See [Cloudflare's published limits](https://developers.cloudflare.com/durable-objects/platform/pricing/).

Existing direct HTTPS pairing remains compatible, including private Tailscale Serve origins. That is an advanced alternative and requires its own certificate and network setup. ProtonVPN port forwarding is not used. Never disable TLS checks or expose the root broker as a general network service.

See the [relay protocol and deployment guide](../relay/README.md) for credential boundaries, provider-visible metadata, tests, and activation.
