# Free remote parent access

Checked against the providers' published plans on 2026-10-02. No manual router port forwarding is required for these hosted mesh-network options. Both devices need outbound connectivity; restrictive networks may use a relay and still must permit that traffic.

| Option | Published free allowance | Fit for Parent Controls |
| --- | --- | --- |
| [Tailscale Personal](https://tailscale.com/pricing) | $0, up to 6 users, unlimited user devices; personal, non-commercial use | Works with the current pairing and private HTTPS Serve design. Best fit for a family's computers. |
| [NetBird Free](https://netbird.io/pricing) | €0, up to 5 users and 100 machines | A viable alternative, but requires changes to endpoint pairing and private HTTPS exposure. It is not currently integrated. |
| [ZeroTier Personal](https://www.zerotier.com/pricing/) | $0, 10 devices, one network, one administrator; personal, non-commercial use | Enough for a small family network, but also needs different endpoint pairing and HTTPS setup. It is not currently integrated. |

Tailscale's paid plans are not required just to reach the girls' personal schoolwork machines. Use the Personal plan for eligible family use. A custom-domain login may initially enter a business trial; [Tailscale documents how personal users can opt out](https://tailscale.com/pricing). An organization-managed school deployment should check its own plan eligibility.

The current parent app and broker intentionally validate HTTPS `.ts.net` endpoints, and the HTTP relay listens only on localhost. Installing NetBird or ZeroTier alone therefore will not make the current app use them. Supporting either needs a reviewed HTTPS endpoint design and corresponding changes in both the iOS app and broker; do not work around this by exposing the relay publicly or disabling certificate checks.

Connectivity references: [Tailscale Serve without port forwarding](https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-team), [NetBird outbound-only connectivity](https://docs.netbird.io/about-netbird/ports-and-firewalls), [ZeroTier router guidance](https://docs.zerotier.com/routertips/).

Self-hosted control servers can avoid a vendor subscription, but the server still needs hosting and reliable public reachability. Free software alone does not guarantee a zero-cost, no-port-forwarding deployment. No accounts, subscriptions, routers or existing network settings were changed by this comparison.
