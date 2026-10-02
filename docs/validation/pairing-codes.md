# Temporary pairing-code refinement

The laptop now displays a four-group code after parent-PIN authorization. Parent Pocket 0.2.1 accepts it directly on either iPhone or Simulator. A QR of the same code is optional; normal setup no longer prints or asks for enrollment JSON.

The code has 80 bits of random entropy, expires in five minutes, and is consumed once. The hosted inbox keeps only domain-separated lookup hashes and authenticated ciphertext. A fresh code invalidates older unused codes for the laptop. Root-broker expiry is independent of the hosted inbox, and the app verifies an authenticated laptop status before saving the pairing. Established phone credentials continue after the code expires. The inbox is implemented by the Render adapter; the optional Cloudflare adapter still requires the legacy QR path.

Validated on 2026-10-02:

- Host parent-control suite: 147 tests run, 146 passed and one Linux-only test skipped. Includes pending enrollment expiry, activation, replacement and existing-phone preservation.
- Relay suite: 9 passed, including actual HTTP concurrent redemption, single-use tombstones, expiry, browser-origin rejection and rate limiting, plus existing WebSocket behavior.
- Python-generated enrollment decrypted and validated by Swift CryptoKit; wrong/expired/short codes rejected.
- iPhone Simulator build succeeded. Xcode launched the updated app on iPhone 18 Pro. Device Hub UI inspection timed out, so Simulator interaction itself has not been accepted as tested. A rendered SwiftUI pairing preview was visually reviewed separately.

The public installer remains alpha.6; the source changes belong to the unreleased alpha.7. Existing live pairings remain compatible. Physical-laptop and iPhone acceptance remains outstanding.
