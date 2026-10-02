# Managed relay and parent access validation

Validated on 2026-10-02. Source targets the **unreleased** `0.5.0-alpha.7`; the public installer remains alpha.6. No production hosted deployment or physical iPhone acceptance has occurred. `remote-service.json` intentionally has a null endpoint until account access and deployed TLS checks are complete.

## Passed

- Parent broker/installer tests: **142 passed in the isolated ARM Omarchy VM**. Host: 141 passed, one Linux-only bootstrap test skipped.
- Voice tests: **66 passed**, including encrypted transcript handling, strict TLS validation, existing dictation/wake/approval checks.
- Separate Laya service tests: **11 passed**, including encrypted suggestions, request expiry, replay rejection, device enrollment and action restrictions. The relay tests use a deterministic model stub; they do not establish new real-model speech accuracy.
- Relay routing tests: **5 passed**, including real sockets through the Render Node adapter; real Workers local runtime WebSocket acceptance also passed for authenticated encrypted approval, offline delivery rejection, reconnection using the same pairing, and immediate broker revocation.
- Python AES-GCM/HKDF response decrypted by Swift CryptoKit; Swift request decrypted and validated by Python. Wrong request IDs and altered packets are rejected.
- Parent Pocket iOS Simulator build succeeded in Xcode 27. Fifteen pairing/protocol checks passed; actual SwiftUI Controls render was reviewed using labeled sample data. Multiple laptops sharing one relay endpoint retain separate pairings.
- Installed source release in the isolated Omarchy VM. A connector running as `nobody` passed an encrypted request through the real local relay runtime to the installed root broker. Remote Pause and Resume succeeded; disabling controls was rejected. The connector could not read root parent state.
- Actual graphical Hyprland session produced **30 seconds** of counted unlocked desktop usage. This caught and fixed a loginctl property-query error that mocked tests did not detect.
- Paused state persisted and was enforced after VM reboot; root-authorized recovery resumed access. Separate live tests froze and resumed the same running child process without losing its state, denied paused PAM account login, and authenticated parent-PIN recovery using libpam.
- Removal succeeded, removed the PAM account gate and stopped the new services. Reinstallation succeeded with parent settings retained. Recovery removal restores admin authentication before attempting potentially failing pause cleanup.
- QML parsed with the Omarchy VM's `qmlformat`. Worker deployment bundle passed Wrangler dry-run with the Durable Object and rate-limit bindings.

## Reproduce the relevant checks

Run `python -m unittest discover -s tests -v` in the parent repo and its `voice/` directory with the appropriate dependencies. Laya has its own test directory. In `relay/`, run `pnpm install --frozen-lockfile`, `pnpm test`, and `pnpm dev`; with the local relay running, execute `python test/integration.py` using Python with cryptography and websockets installed.

`tests/integration_relay_vm.py --disposable-vm` is **only for the isolated test VM**. It temporarily pairs a test phone, pauses/resumes the desktop and restores its prior phone data. The test relay address `10.0.2.2:8787` is the VM-to-host development connection, not a production endpoint. Public transport remains TLS-only with system certificate verification.

## Remaining acceptance

Deploy under the owner's Render account (no custom domain needed), record its permanent verified HTTPS origin, and test actual remote TLS round trips before merging/publishing the new installer. Check physical-laptop wake/microphone behavior, real-network sleep/resume and Wi-Fi changes, real iPhone signing/QR/Face ID/Keychain, and the actual Laya host's model/service setup. Managed hosting removes server/certificate administration but still depends on network availability, provider quotas and ordinary software updates. Background push and direct Bluetooth/LAN discovery are not included.

The same encrypted Python broker acceptance script also passed against the Render Node runtime: authentication, encrypted approval, disconnect recovery, offline rejection and revocation. This was local acceptance; a deployed Render round trip is still pending account access.
