# Mobile and Videos refinement — alpha.8

The phone app is displayed as Omarchy Parent Controls, version 0.3.0 build 5. Home, Requests, Videos, Web Apps and Settings apply to the selected computer; each paired computer has an editable child name and display name. The desktop panel only switches controlled mode with PIN approval. Pairing remains available through `omarchy-parent-controls pair`.

## Parent PIN

Phone setup creates an 8–12 digit PIN. Verification uses a random salt and PBKDF2-HMAC-SHA256 (210,000 rounds), with persisted increasing retry delays after five failures. Credentials and pending laptop PIN updates are in device-only Keychain storage. Optional Face ID/Touch ID uses biometric-only authentication and a biometry-current-set Keychain item, so enrolling different biometrics requires PIN unlock and re-enablement. The app locks when backgrounded and masks its content while inactive.

A root-authorized temporary laptop pairing grants a one-use, five-minute setup-PIN operation. It requires the encrypted connection and successful status activation. Existing paired phones cannot use setup-PIN; changing a PIN requires the current PIN. Keyed receipt fingerprints and a durable last-PIN receipt support retry after a lost response without storing raw PINs on the laptop. Remote operations cannot disable controlled mode or execute arbitrary commands.

Changing the app PIN attempts each known laptop. Offline laptops retain their previous PIN until the parent taps Retry PIN updates, with status shown separately for each computer. Previously paired laptops need a fresh pairing code to adopt the app PIN. The app never labels an unacknowledged update as successful. Face ID must be re-enabled after changing the PIN.

## Verification

- 157 laptop tests: 156 passed, one Linux-specific test skipped on macOS. New cases cover per-computer isolation, exact web-app editing, encrypted PIN authorization, expiring one-use setup, and retry after receipt expiry.
- All 157 tests also passed inside the Omarchy Linux VM. QML syntax validation passed. An X11 test display in that VM verified embedded mpv playback using a generated clip, and verified revoking approval kills playback. This checks rendering/control integration; live YouTube availability still depends on YouTube and yt-dlp.
- Swift PIN checks passed: persisted failed-attempt backoff and reset, deterministic derivation, different salts, input validation, and pending update record round-trip.
- iOS Simulator build passed. Source-rendered Home, Web Apps, Videos, Settings and laptop Videos layouts inspected.
- Physical iPhone biometric/Keychain acceptance and physical school-laptop playback remain necessary; a successful build is not an App Store release.
