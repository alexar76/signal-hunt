# Signal Hunt → DIOSCURI hero relay

## Trust boundary

Signal Hunt does not post to social networks and stores no Discord/X credential. It
publishes an opt-in public feed at `/api/v1/heroes/feed`. The payload contains only a
player-selected call sign, aggregate verified score/status, unlocked reward codes and a
round proof reference. It excludes session IDs, tokens, IPs and unopened evidence.

The exact payload bytes are base64url-encoded and signed with Signal Hunt's persistent
Ed25519 provider key. DIOSCURI verifies those bytes against an operator-pinned key; the
advertised key in the response is never trusted by itself.

## Enable the relay

1. Read `GET https://hunt.modelmarket.dev/provider/public-key` over the deployed route.
2. Verify the key against the Hub capability registration or another operator channel.
3. Configure DIOSCURI:

   ```dotenv
   SIGNAL_HUNT_HERO_FEED_URL=https://hunt.modelmarket.dev/api/v1/heroes/feed
   SIGNAL_HUNT_HERO_PUBKEY_B64=<verified-provider-public-key>
   SIGNAL_HUNT_PUBLIC_URL=https://hunt.modelmarket.dev
   SIGNAL_HUNT_HERO_POLL_MINUTES=5
   SIGNAL_HUNT_HERO_MAX_POSTS=3
   ```

4. Keep Discord enabled for Pollux. To add X, explicitly enable KERYX with
   `X_SYNDICATION=1` and its four OAuth credentials.

## Publication rules

- profile sharing is off by default and affects only future milestones;
- one signed round creates at most one hero event even if it unlocks several rewards;
- first DIOSCURI poll records existing events without posting historical spam;
- delivery state is persistent and per sink, so an X outage does not duplicate Discord;
- each cycle posts at most `SIGNAL_HUNT_HERO_MAX_POSTS` events;
- stale, future-dated, tampered or wrong-key feeds post nothing;
- an audit entry records every successful delivery;
- deleting an event upstream does not erase DIOSCURI's delivery record.

DIOSCURI `/health` reports `signalHuntHeroes.active`, `lastOkAt`, `lastError` and active
sinks. A non-empty error means the relay is degraded; it does not affect the game.
