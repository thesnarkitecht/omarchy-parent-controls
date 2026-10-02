# Automatic remote parent access

The new default is the managed encrypted relay in [`relay/`](../relay/README.md). The selected interim provider is Render Free, with an included `onrender.com` address and managed HTTPS. The optional Cloudflare adapter remains available. No VPN, custom domain, router forwarding, or server administration is required. A maintainer deploys it once; each laptop connects outward automatically after pairing. The parent app needs the corresponding protocol-v2 build.

**Relay deployed and verified on 2026-10-02:** `https://parent-pocket-relay.onrender.com`. The alpha.7 installer includes this verified origin and temporary pairing codes. Use Parent Pocket 0.2.1 or later on the iPhone or Simulator. Older alpha.6 installations need `omarchy-parent-controls update` first.

After activation: open the laptop lock icon → **Pair parent phone** → enter the parent PIN → enter the displayed code in Parent Pocket. The iPhone Simulator uses the same code field; no camera, JSON, or URL is required. Codes expire after five minutes and are single-use. A new code invalidates older unused codes on that laptop. `omarchy-parent-controls pair` does the same from a terminal. `omarchy-parent-controls unpair` revokes all phones; `omarchy-parent-controls resume` provides a PIN-authorized local recovery command.

The encrypted relay carries only bounded parent operations and Laya suggestion requests. Laya audio capture and transcription stay on the laptop; actions are checked and executed on the laptop. Local dictation continues without the relay. The laptop and the Laya host must be awake for their respective remote functions. Offline commands are never queued for later execution.

Render manages the host and public certificates. Its free service may take about a minute to wake after an idle period; the devices reconnect automatically. This still needs ordinary software updates, an active account, and available free-plan quota; it is not an unlimited or guaranteed-uptime service. Nothing enables a paid plan automatically. See [Render’s free-service limits](https://render.com/docs/free).

Existing direct HTTPS pairing remains compatible, including private Tailscale Serve origins. That is an advanced alternative and requires its own certificate and network setup. ProtonVPN port forwarding is not used. Never disable TLS checks or expose the root broker as a general network service.

See the [relay protocol and deployment guide](../relay/README.md) for credential boundaries, provider-visible metadata, tests, and activation.
