# Signal Hunt — complete guide

> Languages: **English** · [Русский](GUIDE.ru.md) · [Español](GUIDE.es.md) · [Français](GUIDE.fr.md) · [中文](GUIDE.zh.md)
> Game rules: [English](RULES.md) · [Русский](RULES.ru.md) · [Español](RULES.es.md) · [Français](RULES.fr.md) · [中文](RULES.zh.md)

## 1. What Signal Hunt is

Signal Hunt is a federation-native investigation game **and an educational laboratory**.
Each round is generated from a real snapshot of an ordinary AIMarket Hub: its indexed
external capabilities, source distribution, effective prices, signed identity and recent
stored history. The player examines evidence, chooses a diagnosis and declares confidence.

Think of it as a **lab course wrapped in a game**: the loop is entertaining, but the
material is live federation literacy — reading Hub telemetry, paying for evidence,
calibrating confidence with Brier scoring, verifying cryptographic commitments and
watching how federation growth, peer join/leave and latency weather change which
diagnoses appear.

The product is not a simulation dashboard. If the Hub cannot be observed, the game
returns an unavailable state instead of substituting a fixture. Missing history or price
data remains explicitly missing.

### Educational outcomes

After several rounds a careful player should be able to:

1. Explain a Hub observation from measured sources rather than from narrative speculation.
2. Trade off evidence cost against score using the published evidence factor.
3. State confidence that survives Brier scoring instead of bluffing certainty.
4. Recompute a verdict from salt, commitment and returned operands.
5. Relate detector classes (isolation, disappearance, peer churn, latency weather,
   concentration, …) to real catalogue, roster and latency dynamics as the federation
   grows.

## 2. What runs on the game server

The production deployment contains PostgreSQL, an ordinary AIMarket Hub, the Signal
Hunt engine and Caddy TLS ingress. A one-shot bootstrap registers five local capabilities:

| Capability | Purpose |
|---|---|
| `signal.case@v1` | Return the current immutable investigation |
| `signal.evidence@v1` | Reveal one committed evidence block |
| `signal.submit@v1` | Verify a diagnosis and compute its score |
| `signal.leaderboard@v1` | Return rankings derived from persisted verdicts |
| `signal.heroes@v1` | Return opt-in, signed hero milestones |

General randomness and analytics are not reimplemented locally. The engine discovers a
remote `sortes.draw@v1` through its Hub when available and stores the route, source Hub,
receipt nonce and result hash. Failure is recorded as unavailable and never presented as
a successful remote call.

## 3. Player journey

1. **Observe.** The landing shows the measured Hub, source Hubs, capability counts,
   manifest latency, observation ID and state hash.
2. **Investigate.** Six evidence blocks are available: distribution, historical change,
   effective pricing, peer roster, latency surface and provenance.
3. **Commit.** Select one of four diagnoses, optionally answer the second-lock follow-up,
   and assign 25–100% confidence.
4. **Verify.** The server reveals the answer salt, checks the pre-round commitment,
   applies follow-up bonus and any locked PRIME multiplier, then stores one immutable
   verdict plus a cliffhanger for the next field window.
5. **Progress.** Verified points determine status; daily streak, weekly season passport
   and explicit predicates unlock cosmetic relics. Strong orbits can one-tap broadcast
   into the signed hero feed after opt-in. Nothing is minted and no financial value is
   implied.

See [the complete rules](RULES.md) for formulas, thresholds, badge predicates and the
plain-language engagement section (§7).

## 4. Truth and provenance model

Every observation stores the upstream generation time, local observation time, Hub URL,
Hub signer key, per-source counts, price aggregates, source request status and a canonical
state hash. A round references that immutable observation rather than reading newer data
when evidence is opened.

The correct diagnosis is selected by declared deterministic thresholds. Before the round
is exposed, the engine generates a random salt and publishes:

```text
SHA256(round_id:answer_code:answer_salt)
```

The salt and answer are released only in the verdict. Any reviewer can recompute the
commitment and all score operands from the response.

## 5. Identity, privacy and public heroes

Play is anonymous by default. The browser receives an opaque signed session token and
stores it on that device. No wallet, email or social login is required. The database does
not store raw IP addresses in game tables.

A call sign may be changed. Public hero sharing is disabled by default and applies only
to future milestones after explicit opt-in. The signed feed contains the call sign,
aggregate verified statistics, reward codes and proof references; it excludes session
tokens, IP addresses and private evidence.

DIOSCURI pulls this feed and pins Signal Hunt's Ed25519 provider key out of band. Discord
and X delivery state is persisted independently, so retrying one platform does not
duplicate the other. The game never stores social-network credentials.

## 6. HTTP API

| Method | Route | Authentication |
|---|---|---|
| `POST` | `/api/v1/session` | none |
| `GET`, `PUT` | `/api/v1/profile` | bearer session |
| `GET` | `/api/v1/rounds/live` | bearer session |
| `GET` | `/api/v1/rounds/{id}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/evidence/{evidence}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/submit` | bearer session |
| `POST` | `/api/v1/rounds/{id}/broadcast` | bearer session |
| `GET` | `/api/v1/leaderboard` | public |
| `GET` | `/api/v1/leaderboard/weekly` | public |
| `GET` | `/api/v1/heroes/feed` | public, signed payload |
| `GET` | `/provider/public-key` | public |
| `POST` | `/provider/invoke` | AIMarket provider surface |

## 7. Local development

Run an AIMarket Hub first, then install the backend and start the interface:

```bash
cd signal-hunt
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
SIGNAL_HUNT_HUB_URL=http://127.0.0.1:9183 .venv/bin/python -m signal_hunt.main
```

```bash
cd signal-hunt/frontend
npm ci
npm run dev
```

The page intentionally fails closed when the configured Hub cannot supply a valid live
manifest.

## 8. Production deployment

1. Point a DNS A/AAAA record at the new server and open TCP 80/443 plus UDP 443.
2. Copy `.env.example` to `.env`.
3. Generate independent random values for `AIMARKET_ADMIN_TOKEN` and
   `POSTGRES_PASSWORD`.
4. Verify every seed public key out of band; do not trust a key merely because the same
   endpoint advertised it.
5. Run `scripts/deploy.sh`.
6. From a trusted operator machine, use `scripts/register-upstream.sh` to announce,
   approve and crawl the new Hub from an existing Hub.
7. Run `scripts/verify.sh https://<signal-hunt-domain>`.

Caddy is the only service exposing public ports. Hub and provider signing keys live on
persistent volumes and must be backed up with PostgreSQL and game state.

## 9. Operations and failure semantics

- `503 federation_unavailable` means no valid live round could be produced.
- A `null` baseline means insufficient measured history, not zero change.
- `federation_assist.status=unavailable` is an honest degraded path; it does not invalidate
  the detector or claim that a remote VRF ran.
- Repeating the same submission returns the stored verdict and creates no extra reward.
- Losing a signing key changes identity and requires explicit trust recovery.
- DIOSCURI relay errors are visible in its `/health` response and do not block play.

## 10. Verification and contribution

```bash
cd signal-hunt && pytest -q
cd frontend && npm run build
```

The repository GitHub Actions run the Signal Hunt pytest suite, the frontend
typecheck/build, and a `docker compose config` check against `env.ci`. The
DIOSCURI signature contract for the hero feed is covered in the DIOSCURI package
tests (`dioscuri/test/signal-hunt-heroes.test.ts`) inside the aicom monorepo.
Contributions are accepted under the [MIT License](../LICENSE).
Changes to scoring, detector precedence or reward thresholds must update all five rulesets
and their tests in the same pull request.
