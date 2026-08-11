# AICOM Signal Hunt — product and acceptance specification

Status: implementation contract, v1.0<br>
Language of record: Russian<br>
Product directory: `signal-hunt/`

## 1. Product identity

**Public name:** AICOM Signal Hunt<br>
**Hub identity:** Signal Hunt Hub<br>
**Definition:** a federation-native investigation game **and educational laboratory** in
which a person explains a real, measured change in the AIMarket federation and receives a
reproducible verdict. Each round is a practical on live Hub telemetry, evidence cost,
Brier-calibrated confidence and cryptographic commitments — not a fixture-driven tutorial.

Signal Hunt is **not** a new kind of Hub. Signal Hunt Hub is an ordinary AIMarket Hub
running the same `aimarket-hub` implementation and protocol as every other node. The
game is a first-party capability provider registered on that Hub.

Signal Hunt is **not ARGUS Agent Arena**. The existing Agent Arena gamifies an agent's
own economic activity, streaks and achievements. Signal Hunt is a human-facing live
investigation of federation state. The word `arena` is intentionally absent from the
product name, package name, API namespace and Hub identity.

## 2. Product promise

> The federation emitted a signal. Find the cause and prove it before the others.

Every playable statement must be derived from a real signed Hub manifest, Hub peer
catalogue or Hub live-statistics response. The game must never invent a capability,
Hub, price, latency, invocation, failure, player or score.

The entertainment loop is a technical detective story:

1. **Scan:** the player sees a measured symptom, its observation time and provenance.
2. **Investigate:** the player opens exact evidence, paying only an in-game score cost.
3. **Commit:** the player selects a diagnosis and states confidence.
4. **Verify:** the server evaluates the answer with deterministic math and reveals the
   precommitted answer salt.
5. **Share:** the player can share a compact, factual result containing the round ID,
   observation hash and score — never fabricated impact.

## 3. Truth policy — non-negotiable

### 3.1 Allowed runtime data

- `GET /ai-market/v2/manifest` from Signal Hunt Hub;
- `GET /.well-known/ai-market.json` from Signal Hunt Hub;
- `GET /ai-market/v2/federation/peers` from Signal Hunt Hub;
- `GET /ai-market/v2/stats/live` from Signal Hunt Hub;
- `GET /ai-market/v2/search` and `POST /ai-market/v2/invoke` on Signal Hunt Hub
  for a discovered remote capability, with route and result hash recorded;
- later versions may add signed LOGOS/MOMUS responses, provided their provenance is
  stored beside the observation.

### 3.2 Forbidden runtime behaviour

- seeded/demo anomalies;
- placeholder Hubs, capabilities, prices, traffic or latencies;
- random diagnoses presented as measured facts;
- converting missing metrics to zero;
- projecting cumulative settlement as daily/monthly volume;
- an LLM deciding whether an answer is correct;
- awarding points merely for opening the page;
- showing `LIVE` when the current manifest fetch failed.

If mandatory evidence cannot be obtained, the round is not playable. The UI must show
the exact degraded state and the failed source. A real zero remains `0`; missing data is
`—`/`null` and never silently coerced.

### 3.3 Test fixtures

Synthetic fixtures are allowed only inside automated tests. They must never be bundled
into the production image as a fallback data source.

## 4. Deployment boundary

One new server runs four isolated services:

| Service | Responsibility | May be delegated through federation? |
|---|---|---|
| Signal Hunt Hub | Standard discovery, routing, signing and federation | No — it is the new peer itself |
| Game Engine | Round state, evidence access, submissions, scoring | No — authoritative game state must be local |
| SQLite volume | Snapshots, sessions, rounds, evidence views, verdicts | No — local source of game truth |
| Caddy edge | TLS and path routing | No — public ingress for this server |

Analysis, oracle computation and AI explanation are not reimplemented locally. The
Game Engine discovers and invokes suitable remote capabilities through Signal Hunt
Hub. The only permanently local capabilities are those that own game state:

- `signal.case@v1` — current committed investigation;
- `signal.evidence@v1` — reveal one measured evidence block;
- `signal.submit@v1` — accept one hypothesis and score it once;
- `signal.leaderboard@v1` — aggregate verified local submissions.
- `signal.heroes@v1` — opt-in milestones from verified submissions for social relays.

In v1 the first real cross-Hub dependency is `sortes.draw@v1`. The game discovers it
through `/search`, invokes it through Signal Hunt Hub with a round-bound `alpha`, and
uses the returned ECVRF result hash to order the answer options. The remote oracle
never chooses the correct answer. If the route or payment is unavailable, the assist is
recorded as unavailable and the deterministic local ordering is used explicitly.

## 5. Federation requirements

### 5.1 Outbound discovery

Signal Hunt Hub receives one or more HTTPS well-known seed URLs. First-contact
capabilities are indexed only when the seed public key is operator-pinned or the peer
is explicitly approved. HTTPS reachability alone is not trust.

### 5.2 Inbound discovery

The existing federation does not magically learn a new public hostname. Deployment
must produce the new Hub URL and Ed25519 public key. An operator then announces,
approves and crawls it on an existing trusted Hub. The provided registration script may
perform those admin calls only when an ephemeral upstream admin token is explicitly
supplied; the token is never persisted.

### 5.3 Routing invariants

- `source_hub` always identifies the capability owner;
- `routed_via` (when displayed) identifies the routing Hub separately;
- routed price is not replaced by base price;
- hop/loop protections remain the standard AIMarket Hub implementation;
- game code never calls a hard-coded oracle URL when the same action is available via
  Hub discovery/invoke.

## 6. Observation model

An observation is built from one successful manifest fetch plus optional supporting
endpoints. It contains:

- UTC observation time and upstream `generated_at`;
- Hub URL and signer public key;
- total/local/federated capability counts;
- exact capability identity set (`source_hub`, `product_id`, `capability_id`);
- per-source counts and shares;
- measured price distribution: minimum, median, p90 and maximum;
- peer roster identity from `/federation/peers` (URL, name, capabilities count);
- stored snapshot also keeps measured probe fields `probe_status` and `latency_ms`
  (RTT to each peer's `/.well-known/ai-market.json`, capped; `latency_ms` is null when
  the probe fails or is skipped) — these RTT fields are **not** exposed on the public
  mission card; players unlock them via the latency evidence block;
- public observation latency object exposes only `measured_count` (no free aggregates);
- full latency surface aggregates (`threshold_ms`, `max_ms`, `median_ms`, `slow_count`, …)
  ship inside the sealed latency evidence payload;
- settlement/invocation fields exactly as reported, with missing values preserved;
- elapsed request time only for requests actually performed;
- canonical SHA-256 state hash (includes peer URLs and successful peer latency samples).

The stored snapshot omits prompts, credentials, private payloads and payment secrets.

## 7. Detection mathematics

The detector compares the current observation with up to 20 prior observations. Its
priority order is deterministic:

1. `federation_isolated`: zero external capabilities;
2. `source_disappearance`: a previously observed source with at least three
   capabilities is now absent;
3. `peer_churn`: measured federation roster changed (established peer left and/or new
   peer joined). Leave requires ≥2 historical sightings; join requires history depth ≥2.
   Peers endpoint must be `ok` — unavailable roster never invents churn;
4. `catalog_contraction`: current external count is at least 3 and 15% below the
   historical median;
5. `catalog_expansion`: current external count is at least 3 and 15% above the
   historical median;
6. `price_shift`: median effective price moved at least 20% and $0.001;
7. `latency_weather`: at least one peer has a successfully probed RTT above 500 ms.
   `latency_ms` is null on failed/skipped probes and never fabricated;
8. `source_concentration`: at least two external sources exist and the largest owns at
   least 60% of external capabilities;
9. `stable`: no threshold above was met.

Historical medians, not a single preceding point, form the baseline. A missing baseline
does not become zero. Concentration can be evaluated from a first observation because
it is a cross-sectional fact.

Future statistical detectors may use median absolute deviation (MAD). They must declare
minimum sample size and must not emit a numeric z-score when MAD is zero.

## 8. Round integrity

A round is immutable after creation. It stores the observation state hash, diagnosis,
ordered options and evidence blocks. Before any player submits, the API publishes:

```text
answer_commitment = SHA256(round_id || ":" || answer_code || ":" || random_salt)
```

After a verdict the API reveals `answer_code` and `random_salt`; the client can
recompute the commitment. A submission is unique for `(round_id, session_id)` and is
idempotent: retries return the original verdict rather than awarding points again.
When the remote Sortes route succeeds, its capability ID, source Hub, routed price,
receipt nonce and result hash are stored in `federation_assist`; only the result hash is
used as option-order entropy.

## 9. Scoring mathematics

The player selects one of `n` diagnoses and reports confidence `c`, constrained to
`1/n ≤ c ≤ 1`. Probability `c` is assigned to the selected diagnosis and the remaining
mass is distributed uniformly across the other `n−1` diagnoses.

For outcome vector `y` and stated probability vector `p`:

```text
Brier = Σ(p_i − y_i)²
Brier_baseline = 1 − 1/n
skill = max(0, 1 − Brier / Brier_baseline)
evidence_factor = max(0.70, 1 − 0.05 × opened_evidence_count)
score = round(1000 × skill × evidence_factor)
```

Thus a confident correct diagnosis scores highest, unjustified confidence is punished,
uniform guessing scores zero, and opening evidence has a small bounded cost. The API
returns every operand so the client or reviewer can recompute the score.

### 9.1 Status and prize mathematics

Status is a pure function of cumulative persisted score:

| Status | Minimum score |
|---|---:|
| `stargazer` | 0 |
| `pathfinder` | 500 |
| `signal_analyst` | 1,500 |
| `void_navigator` | 3,500 |
| `constellation_keeper` | 7,500 |
| `federation_oracle` | 15,000 |

Badges are idempotent records keyed by `(session_id, badge_code)`. Their predicates are
declared in code and include first verified round, Brier ≤ 0.08, all six evidence blocks
plus a correct answer, ≥800/≥950 round score, a correct ≥75%-confidence answer without
opened evidence, three consecutive correct answers, and five completed rounds. A replay
cannot mint a second copy. These are cosmetic proofs of play, never money, tokens, NFTs
or a promise of external value.

## 10. Player identity and privacy

- Play is anonymous by default.
- The server issues an opaque signed session token; the browser stores it locally.
- A player chooses a pseudonym; no wallet, email or social login is required for v1.
- Handles are normalized, length-limited and never treated as HTML.
- Raw IP addresses are not stored in game tables.
- One session can submit once per round.
- Public leaderboard rows contain only handle, verified score aggregates and counts.
- Public hero sharing is disabled by default and requires an explicit profile opt-in.
- Enabling sharing is prospective: it never republishes earlier private milestones.
- The public hero feed excludes session IDs, tokens, IPs and private evidence.

### 10.1 DIOSCURI social relay

One verified submission can create at most one hero event containing any newly unlocked
rewards. Signal Hunt signs the exact feed payload bytes with its persistent Ed25519
provider key and holds no social credentials. DIOSCURI is a pull consumer: it pins the
key out of band, rejects stale/tampered/wrong-key feeds, suppresses historical backlog,
and records delivery separately for Discord and X. A platform failure is retried without
duplicating a platform that already accepted the event.

## 11. User experience requirements

### 11.1 First meaningful paint

The initial screen must immediately communicate:

- that this is Signal Hunt, not Agent Arena;
- whether telemetry is currently live;
- which Hub is being observed;
- the real capability and source counts;
- one clear action: start/open the investigation.

### 11.2 Investigation flow

- a code-native 3D federation field maps real source Hubs to nodes;
- node size is derived from capability count;
- labels and counts come from the current observation;
- unavailable data has a neutral visual state, never a fabricated numeric latency;
- keyboard, touch and reduced-motion modes are first-class;
- layouts must work at 320, 390, 768, 1280 and 1440 CSS pixels;
- EN, RU, ES, FR and ZH catalogues must have identical keys;
- all buttons have accessible names and visible focus;
- no horizontal page overflow at supported widths.

### 11.3 Error states

The UI distinguishes:

- Game Engine unavailable;
- Hub unavailable;
- Hub reachable but no trusted external capabilities indexed;
- supporting endpoint missing while manifest remains valid;
- already submitted;
- round superseded by a new observation.

## 12. API acceptance surface

Human API:

- `GET /health`
- `POST /api/v1/session`
- `GET /api/v1/profile`
- `PUT /api/v1/profile`
- `GET /api/v1/rounds/live`
- `GET /api/v1/rounds/{round_id}`
- `POST /api/v1/rounds/{round_id}/evidence/{evidence_id}`
- `POST /api/v1/rounds/{round_id}/submit`
- `GET /api/v1/leaderboard`
- `GET /api/v1/heroes/feed`

Provider API:

- `GET /provider/public-key`
- `POST /provider/invoke`

Every successful provider response is Ed25519-signed using the AIMarket
request-bound canonical form. The provider key persists on a dedicated volume.

## 13. Operational acceptance

Deployment is accepted only when all checks pass:

1. TLS endpoint returns a standard signed well-known document.
2. Signal Hunt Hub indexes at least one operator-approved external peer.
3. Its manifest exposes the five local Signal Hunt capabilities.
4. Invoking `signal.case@v1` through Signal Hunt Hub returns a signed result.
5. A round records either a real `sortes.draw@v1` cross-Hub invoke or an explicit
   unavailable reason; it never claims remote assistance without a result hash.
6. An existing upstream Hub lists Signal Hunt Hub as an approved peer.
7. That upstream manifest/search retains `source_hub` provenance for Signal Hunt tools.
8. The game page loads without fixture data and reports the same counts as its stored
   observation.
9. A second submission for the same session/round is idempotent.
10. Recomputed answer commitment and score match the API response.
11. Backend tests and frontend production build pass.
12. Reward predicates, tiers and streaks recompute from persisted submissions.
13. A private profile never appears in the hero feed; an opted-in new milestone does.
14. DIOSCURI refuses a modified or wrong-key feed and keeps per-sink delivery state.

## 14. Definition of done for v1

- ordinary separately deployable Hub with a production PostgreSQL state store;
- two-way operator-approved discovery workflow;
- live observation ingestion with no fallback fixtures;
- seven deterministic signal classes;
- immutable committed rounds and evidence trail;
- reproducible Brier-based scoring;
- anonymous sessions, deterministic status/reward progression and real leaderboard;
- opt-in signed hero feed with an idempotent DIOSCURI Discord/X relay;
- signed game capabilities available through the Hub;
- responsive multilingual production UI with real 3D data mapping;
- deployment, registration, verification and backup documentation;
- automated tests for detection, commitment, scoring, idempotency and API truth states.

Anything described as future work must remain visibly disabled and must not contribute
data, claims, score or status in v1.
