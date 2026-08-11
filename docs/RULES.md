# Signal Hunt — game rules

> Languages: **English** · [Русский](RULES.ru.md) · [Español](RULES.es.md) · [Français](RULES.fr.md) · [中文](RULES.zh.md)
> Complete guide: [English](GUIDE.md)
> Terminology: [localization glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) (Signal Hunt section)

## 1. Objective

Identify the condition detected in a real AIMarket federation snapshot, express calibrated
confidence and earn the highest reproducible score. There is no hidden human judge.

Signal Hunt is **also an educational lab**: each round is a live practical on federation
telemetry, evidence cost, probabilistic scoring and cryptographic commitments — not a
toy simulation with fixtures.

## 1.1 Educational value

Playing a round trains concrete skills that map to the AIMarket / AICOM stack:

| Skill | What the lab forces you to practice |
|---|---|
| Reading live federation state | Manifest, sources, prices, peer roster, latency probes, provenance — measured, never invented |
| Evidence discipline | Opening fewer blocks preserves score; more data is a real cost |
| Calibrated confidence | Brier skill rewards honesty; overconfidence is punished |
| Cryptographic verification | Answer commitments and independent recomputation of the verdict |
| Detector literacy | Named thresholds (isolation, disappearance, peer churn, latency weather, concentration, …) in declared order |
| Federation dynamics | Growth, peer join/leave, latency weather and price shifts change which diagnoses appear |
| Honest public proof | Opt-in hero relay carries only signed, verified orbits |

Treat the product as a **game + laboratory course**: entertainment keeps attention;
reproducible math and live Hub data are the curriculum.

## 2. A round

- The default round window is 1,800 seconds (30 minutes) and is configurable by the operator
  via `SIGNAL_HUNT_ROUND_SECONDS`.
- One immutable round is derived from a canonical observation state hash.
- Each session may submit once per round. A repeated request returns the stored verdict.
- The public mission card stays **sealed**: it discloses only severity (`anomaly` / `calm`)
  and baseline depth until a verdict exists. The detector class is revealed with the answer.
- Four diagnosis options are shown. Their order may use remotely discovered signed VRF
  entropy; an unavailable remote call is recorded explicitly.
- The correct answer is committed before any player action.

## 3. Detector precedence

The first matching condition wins in this exact order:

1. **Federation isolated:** external capability count equals zero.
2. **Source disappearance:** a previously observed source carrying a historical median of
   at least three capabilities is absent.
3. **Peer churn:** the Hub peers endpoint is available and the measured federation roster
   changed — an established peer (seen in at least two prior snapshots) left, and/or a new
   peer appeared after at least two historical snapshots. Capability-source disappearance
   is a different signal and wins first when both apply.
4. **Catalogue contraction:** at least three fewer external capabilities and at least 15%
   below the historical median.
5. **Catalogue expansion:** at least three more external capabilities and at least 15%
   above the historical median.
6. **Price shift:** absolute median-price change is at least `$0.001` and relative change
   is at least 20%.
7. **Latency weather:** at least one peer has a **successfully measured** probe RTT above
   `500 ms`. Failed or skipped probes store `latency_ms = null` and never invent weather.
8. **Source concentration:** with at least two sources, the largest carries at least 60%
   of external capabilities.
9. **Stable:** none of the declared thresholds above was crossed.

Missing history cannot satisfy a historical threshold and is never replaced with a
synthetic baseline. Peer RTT is measured by probing each peer's `/.well-known/ai-market.json`
during the observation (capped); it is not inferred from Hub crawl metadata.

## 4. Evidence

Six evidence blocks may be opened before submission:

- **Distribution:** external total and each source's capability count/share.
- **Change:** current total, historical samples and measured median.
- **Pricing:** current price aggregates and historical medians when available.
- **Roster:** federation peers (url, name, capabilities), join/leave vs history.
- **Latency:** measured peer RTT samples, threshold (`500 ms`), slow count.
- **Provenance:** Hub URL, timestamps, state hash, signer key and source request statuses.

Each distinct opened block reduces the score multiplier by 0.05. Opening all six gives
an evidence factor of 0.70 (the lower bound). Reopening a block does not add a
second penalty.

## 5. Confidence

Confidence is the probability assigned to the selected diagnosis. With four options it
must be from 0.25 through 1.00. The remaining probability is divided equally between the
other three options:

```text
r = (1 − confidence) / (K − 1)
```

where `K=4` in v1. The returned probabilities always sum to one.

## 6. Score

For option probabilities `pᵢ` and one-hot outcome `oᵢ`, the multiclass Brier score is:

```text
Brier = Σ(pᵢ − oᵢ)²
baseline = 1 − 1/K
skill = max(0, 1 − Brier / baseline)
evidence_factor = max(0.70, 1 − 0.05 × opened_evidence)
base_score = round(1000 × skill × evidence_factor)
```

Optional **second lock** (follow-up micro-question on the same measured field):

```text
follow_up_bonus = 150 if follow-up answered correctly else 0
combined = base_score + follow_up_bonus
```

**PRIME window:** the first 15 minutes of each UTC hour. Rounds created while PRIME is
active lock `×1.5` for that round:

```text
round_score = round(combined × (1.5 if prime_locked else 1.0))
```

A correct answer with well-calibrated confidence scores highly. A wrong high-confidence
answer is punished more than a cautious wrong answer. Uniform 25% guessing has zero skill.
The verdict returns Brier, baseline, skill, evidence count, evidence factor, follow-up
bonus, PRIME multiplier and every assigned probability so the calculation can be replayed.

## 7. Engagement rules (plain language)

These loops use the same measured Hub data. Nothing is invented for drama.

### 7.1 Second lock (dual move)

After choosing a diagnosis you may answer one optional micro-question built from the same
observation, for example:

- which source leads the field,
- whether median effective price moved up / down / flat versus history,
- which band holds the external capability count,
- which measured peer is slowest right now (`latency_weather`),
- whether the peer roster joined / left / both / held (`peer_churn`).

Skip is allowed. A correct second lock adds **+150** to `base_score` **before** PRIME.
Diagnosis correct **and** follow-up correct in the same round unlocks **Dual Lock**.

### 7.2 PRIME window

Every UTC hour, minutes **0–14** are PRIME (`×1.5`).

- The multiplier is **locked when the round is created**.
- Submitting later in a PRIME-born round still gets `×1.5`.
- A round born outside PRIME stays `×1.0` even if you submit during a later hot window.

### 7.3 Daily streak and shield

Playing on calendar UTC days builds a **daily return streak**. One **shield** can cover a
single missed day so the streak survives one gap. At three alive days you can earn
**Streak Keeper**. The UI shows whether the streak is alive and whether the shield is still
available.

### 7.4 Live presence

The round card shows how many sessions were recently active and how many already solved
**this** round. These are real aggregate counts from the game database, not simulated
crowds.

### 7.5 Weekly season passport

Each ISO week has its own passport:

| Target | Unlock |
|---|---|
| 3 distinct correct diagnoses | Season Polyglot |
| 3,000 weekly score | Season Hunter |
| 3 correct PRIME-window verdicts | PRIME Runner |

Progress resets with the ISO week. A separate **weekly leaderboard** ranks score earned
inside the current week.

### 7.6 Cliffhanger

After a verdict the client shows when the next sealed field window opens. It is a reminder
tied to the real round expiry — not a fake teaser about invented anomalies.

### 7.7 Perfect Orbit broadcast

Score ≥ 950 (Perfect Orbit territory) can be sent to the signed hero feed with one tap
after you enable the public hero relay. Late opt-in still works: solve privately, enable
relay, then broadcast. Auto hero events for opt-in milestones / score ≥ 900 still apply as
in §11.

## 8. Status constellation

Status is a pure function of cumulative persisted score:

| Status | Minimum score |
|---|---:|
| Stargazer | 0 |
| Pathfinder | 500 |
| Signal Analyst | 1,500 |
| Void Navigator | 3,500 |
| Constellation Keeper | 7,500 |
| Federation Oracle | 15,000 |

Crossing a threshold creates one idempotent status record. Status cannot be purchased.

## 9. Relics and badges

| Badge | Exact predicate |
|---|---|
| First Contact | Complete at least one verified round |
| Calibrated Mind | Current verdict Brier ≤ 0.08 |
| Deep Scan | Correct answer after opening all six evidence blocks |
| Clean Vector | Correct answer with round score ≥ 800 |
| Signal Instinct | Correct answer, no evidence, confidence ≥ 75% |
| Triple Lock | Best correct-answer streak reaches three |
| Seasoned Observer | Complete at least five verified rounds |
| Perfect Orbit | Correct answer with round score ≥ 950 |
| Dual Lock | Correct diagnosis and correct follow-up in one round |
| Streak Keeper | Calendar-day return streak reaches three (one missed-day shield) |
| Season Polyglot | ≥ 3 distinct correct diagnoses in the current ISO week |
| Season Hunter | ≥ 3,000 weekly score in the current ISO week |
| PRIME Runner | ≥ 3 correct PRIME-window verdicts in the current ISO week |

Each badge is stored once per session and cannot be minted again by replaying a request.
Badges and statuses are cosmetic records: not money, tokens, NFTs, transferable property
or promises of external value.

## 10. Leaderboard

The public leaderboard contains call sign, verified cumulative score, completed rounds,
correct count, rank and status. Ranking order is cumulative score, correct count, lower
mean Brier, then earlier last-played time. Session tokens and private evidence are absent.

A separate **weekly** board ranks score accumulated inside the current ISO week.

## 11. Hero announcements

Public sharing is off by default. When a player explicitly opts in, future rounds that
unlock a new reward **or** score ≥ 900 may create one hero event. One round creates at
most one event, even when several rewards unlock together.

Players may also one-tap **broadcast** a Perfect Orbit / score ≥ 950 after enabling the
hero relay (including late opt-in after a private strong verdict).

The feed is signed over exact canonical JSON bytes with the persistent Ed25519 provider
key. DIOSCURI rejects stale, future-dated, modified or wrong-key feeds. Its first poll
records history without posting it; later Discord/X deliveries are idempotent per sink.

## 12. Fair play

- Do not automate submissions or create sessions to manipulate rankings.
- Do not exploit leaked session tokens or interfere with another player's browser.
- Do not present a locally modified client or database as the public deployment.
- Independent verification, source review and self-hosting are encouraged.
- Operators may remove abusive public call signs or exclude automated traffic, but must
  not alter stored verdict mathematics to favour a player.

## 13. Independent verification

After a verdict, verify the answer commitment:

```text
SHA256(round_id:answer_code:answer_salt) == answer_commitment
```

Then recompute the option probabilities, Brier score, skill, evidence factor, follow-up
bonus, PRIME multiplier and rounded score from the returned operands. A mismatch is a
protocol defect and should be reported with the round ID and state hash—never with a
session token.
