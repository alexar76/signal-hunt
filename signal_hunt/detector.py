from __future__ import annotations

import hashlib
import json
import math
import secrets
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any


from .engagement import build_follow_up, prime_window
from .thresholds import (
    LATENCY_WEATHER_MS,
    PEER_JOIN_MIN_HISTORY,
    PEER_LEAVE_MIN_SIGHTINGS,
)


DIAGNOSES = (
    "federation_isolated",
    "source_disappearance",
    "peer_churn",
    "catalog_contraction",
    "catalog_expansion",
    "price_shift",
    "latency_weather",
    "source_concentration",
    "stable",
)

# Ordered evidence ids — deep_scan and RULES count must match this length.
EVIDENCE_ORDER = (
    "distribution",
    "change",
    "pricing",
    "roster",
    "latency",
    "provenance",
)


def _median(values: list[float]) -> float | None:
    finite: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            finite.append(number)
    return statistics.median(finite) if finite else None


def _source_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    return {
        str(row["id"]): int(row["capabilities"])
        for row in snapshot.get("sources", [])
        if row.get("id") and isinstance(row.get("capabilities"), int)
    }


def _peer_url(peer: dict[str, Any]) -> str:
    return str(peer.get("url") or "").rstrip("/")


def _peer_roster(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roster: dict[str, dict[str, Any]] = {}
    for peer in snapshot.get("peers") or []:
        if not isinstance(peer, dict):
            continue
        url = _peer_url(peer)
        if not url:
            continue
        roster[url] = peer
    return roster


def _peers_endpoint_ok(snapshot: dict[str, Any]) -> bool:
    meta = (snapshot.get("sources_status") or {}).get("peers") or {}
    return meta.get("status") == "ok"


def _latest_history(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated = [row for row in history if isinstance(row, dict)]
    if not dated:
        return None
    return max(dated, key=lambda row: str(row.get("observed_at") or ""))


def _source_leader(snapshot: dict[str, Any]) -> tuple[str | None, float | None]:
    sources = snapshot.get("sources") or []
    if len(sources) < 2:
        return None, None
    try:
        external = int(snapshot["capabilities"]["external"])
    except (KeyError, TypeError, ValueError):
        return None, None
    if external <= 0:
        return None, None
    leader = max(sources, key=lambda row: int(row.get("capabilities") or 0))
    ident = str(leader.get("id") or "") or None
    share = leader.get("share")
    if not isinstance(share, (int, float)):
        try:
            share = int(leader.get("capabilities") or 0) / external
        except (TypeError, ValueError, ZeroDivisionError):
            return ident, None
    return ident, float(share)


def detect(
    current: dict[str, Any], history: list[dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    external = int(current["capabilities"]["external"])
    counts = _source_counts(current)
    historical_totals = [
        int(row["capabilities"]["external"])
        for row in history
        if isinstance(row.get("capabilities", {}).get("external"), int)
    ]
    baseline_total = _median(historical_totals)

    if external == 0:
        return "federation_isolated", {"external_capabilities": 0}

    historical_sources: dict[str, list[int]] = {}
    for snapshot in history:
        for source, count in _source_counts(snapshot).items():
            historical_sources.setdefault(source, []).append(count)
    disappeared = sorted(
        (
            {"source_hub": source, "baseline_capabilities": int(statistics.median(values))}
            for source, values in historical_sources.items()
            if source not in counts and statistics.median(values) >= 3
        ),
        key=lambda row: (-row["baseline_capabilities"], row["source_hub"]),
    )
    if disappeared:
        return "source_disappearance", disappeared[0]

    # Peer roster churn — distinct from capability-source disappearance.
    if _peers_endpoint_ok(current):
        current_peers = _peer_roster(current)
        sightings: dict[str, list[int]] = {}
        names: dict[str, str] = {}
        for snapshot in history:
            if not _peers_endpoint_ok(snapshot):
                continue
            for url, peer in _peer_roster(snapshot).items():
                caps = peer.get("capabilities_count")
                sightings.setdefault(url, []).append(
                    int(caps) if isinstance(caps, (int, float)) else 0
                )
                names[url] = str(peer.get("name") or url)
        left = sorted(
            (
                {
                    "peer_url": url,
                    "peer_name": names.get(url, url),
                    "sightings": len(values),
                    "baseline_capabilities": int(statistics.median(values)),
                }
                for url, values in sightings.items()
                if url not in current_peers and len(values) >= PEER_LEAVE_MIN_SIGHTINGS
            ),
            key=lambda row: (-row["baseline_capabilities"], row["peer_url"]),
        )
        joined: list[dict[str, Any]] = []
        if len(history) >= PEER_JOIN_MIN_HISTORY:
            historical_urls = set(sightings)
            joined = sorted(
                (
                    {
                        "peer_url": url,
                        "peer_name": str(peer.get("name") or url),
                        "capabilities_count": peer.get("capabilities_count"),
                    }
                    for url, peer in current_peers.items()
                    if url not in historical_urls
                ),
                key=lambda row: (
                    -(int(row["capabilities_count"]) if isinstance(row["capabilities_count"], int) else -1),
                    row["peer_url"],
                ),
            )
        if left or joined:
            return "peer_churn", {
                "joined": joined,
                "left": left,
                "joined_count": len(joined),
                "left_count": len(left),
                "peer_count": len(current_peers),
                "history_depth": len(history),
            }

    if baseline_total is not None and baseline_total > 0:
        relative = (external - baseline_total) / baseline_total
        absolute = external - baseline_total
        if absolute <= -3 and relative <= -0.15:
            return "catalog_contraction", {
                "current": external,
                "baseline_median": baseline_total,
                "change": int(absolute),
                "change_pct": round(relative * 100, 2),
                "sample_size": len(historical_totals),
            }
        if absolute >= 3 and relative >= 0.15:
            return "catalog_expansion", {
                "current": external,
                "baseline_median": baseline_total,
                "change": int(absolute),
                "change_pct": round(relative * 100, 2),
                "sample_size": len(historical_totals),
            }

    current_price = current.get("prices", {}).get("median_usd")
    old_prices = [
        row.get("prices", {}).get("median_usd")
        for row in history
        if isinstance(row.get("prices", {}).get("median_usd"), (int, float))
    ]
    baseline_price = _median(old_prices)
    if isinstance(current_price, (int, float)) and baseline_price not in (None, 0):
        delta = float(current_price) - float(baseline_price)
        relative = delta / float(baseline_price)
        if abs(delta) >= 0.001 and abs(relative) >= 0.20:
            return "price_shift", {
                "current_median_usd": current_price,
                "baseline_median_usd": baseline_price,
                "change_usd": round(delta, 8),
                "change_pct": round(relative * 100, 2),
                "sample_size": len(old_prices),
            }

    # Latency weather — only successful probes; null latency never invents "slow".
    measured = [
        peer for peer in (current.get("peers") or [])
        if isinstance(peer, dict) and isinstance(peer.get("latency_ms"), (int, float))
    ]
    slow = [
        peer for peer in measured
        if float(peer["latency_ms"]) > LATENCY_WEATHER_MS
    ]
    if slow:
        ranked = sorted(slow, key=lambda row: (-float(row["latency_ms"]), _peer_url(row)))
        top = ranked[0]
        return "latency_weather", {
            "threshold_ms": LATENCY_WEATHER_MS,
            "slow_count": len(slow),
            "measured_count": len(measured),
            "max_ms": round(float(top["latency_ms"]), 2),
            "slowest_peer_url": _peer_url(top),
            "slowest_peer_name": str(top.get("name") or _peer_url(top)),
            "offenders": [
                {
                    "peer_url": _peer_url(peer),
                    "peer_name": str(peer.get("name") or _peer_url(peer)),
                    "latency_ms": round(float(peer["latency_ms"]), 2),
                }
                for peer in ranked[:5]
            ],
        }

    sources = current.get("sources") or []
    leader_id, share = _source_leader(current)
    if leader_id and share is not None and share >= 0.60:
        prev = _latest_history(history)
        prev_id, prev_share = _source_leader(prev) if prev is not None else (None, None)
        already = (
            prev_id == leader_id
            and prev_share is not None
            and prev_share >= 0.60
        )
        if not already:
            leader = max(sources, key=lambda row: int(row.get("capabilities") or 0))
            return "source_concentration", {
                "source_hub": leader["id"],
                "capabilities": leader["capabilities"],
                "external_total": external,
                "share_pct": round(share * 100, 2),
                "source_count": len(sources),
            }

    return "stable", {
        "external_capabilities": external,
        "source_count": len(sources),
        "peer_count": len(_peer_roster(current)),
        "baseline_median": baseline_total,
        "sample_size": len(historical_totals),
    }


def evidence_blocks(
    current: dict[str, Any], history: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    historical_totals = [
        row.get("capabilities", {}).get("external")
        for row in history
        if isinstance(row.get("capabilities", {}).get("external"), int)
    ]
    historical_prices = [
        row.get("prices", {}).get("median_usd")
        for row in history
        if isinstance(row.get("prices", {}).get("median_usd"), (int, float))
    ]
    current_peers = _peer_roster(current)
    historical_peer_urls: set[str] = set()
    for snapshot in history:
        if _peers_endpoint_ok(snapshot):
            historical_peer_urls.update(_peer_roster(snapshot))
    peer_rows = []
    for url, peer in sorted(current_peers.items()):
        row = {
            "url": url,
            "name": peer.get("name") or url,
            "capabilities_count": peer.get("capabilities_count"),
            "latency_ms": peer.get("latency_ms"),
            "probe_status": peer.get("probe_status"),
            "roster": "returning" if url in historical_peer_urls else (
                "new" if history else "observed"
            ),
        }
        peer_rows.append(row)
    left_urls = sorted(historical_peer_urls - set(current_peers))
    measured = [
        peer for peer in (current.get("peers") or [])
        if isinstance(peer, dict) and isinstance(peer.get("latency_ms"), (int, float))
    ]
    blocks = {
        "distribution": {
            "kind": "source_distribution",
            "external_capabilities": current["capabilities"]["external"],
            "sources": current["sources"],
        },
        "change": {
            "kind": "historical_change",
            "current_external": current["capabilities"]["external"],
            "historical_external": historical_totals,
            "baseline_median": _median(historical_totals),
            "sample_size": len(historical_totals),
        },
        "pricing": {
            "kind": "effective_pricing",
            "current": current["prices"],
            "historical_medians_usd": historical_prices,
            "baseline_median_usd": _median(historical_prices),
        },
        "roster": {
            "kind": "peer_roster",
            "peers_endpoint": (current.get("sources_status") or {}).get("peers", {}).get("status"),
            "peer_count": len(peer_rows),
            "joined_count": sum(1 for row in peer_rows if row["roster"] == "new"),
            "left_count": len(left_urls),
            "left_peer_urls": left_urls[:12],
            "peers": peer_rows,
        },
        "latency": {
            "kind": "latency_surface",
            "threshold_ms": LATENCY_WEATHER_MS,
            "measured_count": len(measured),
            "max_ms": (
                round(max(float(p["latency_ms"]) for p in measured), 2) if measured else None
            ),
            "median_ms": _median([float(p["latency_ms"]) for p in measured]),
            "slow_count": sum(
                1 for p in measured if float(p["latency_ms"]) > LATENCY_WEATHER_MS
            ),
            "peers": [
                {
                    "url": _peer_url(peer),
                    "name": peer.get("name") or _peer_url(peer),
                    "latency_ms": round(float(peer["latency_ms"]), 2),
                    "probe_status": peer.get("probe_status"),
                }
                for peer in sorted(
                    measured,
                    key=lambda row: (-float(row["latency_ms"]), _peer_url(row)),
                )[:12]
            ],
        },
        "provenance": {
            "kind": "provenance",
            "hub_url": current["hub_url"],
            "hub_generated_at": current.get("hub_generated_at"),
            "observed_at": current["observed_at"],
            "state_hash": current["state_hash"],
            "signer_public_key": current.get("signer_public_key"),
            "source_status": current["sources_status"],
        },
    }
    # Preserve declared order for API consumers and deep_scan counting.
    return {key: blocks[key] for key in EVIDENCE_ORDER}


def _options(round_seed: str, diagnosis: str, external_entropy: dict[str, Any] | None) -> list[str]:
    entropy = (
        str(external_entropy.get("result_hash"))
        if external_entropy and external_entropy.get("status") == "ok"
        else round_seed
    )
    keyed = sorted(
        DIAGNOSES,
        key=lambda value: hashlib.sha256(f"{round_seed}:{value}".encode()).hexdigest(),
    )
    distractors = [value for value in keyed if value != diagnosis][:3]
    selected = [diagnosis, *distractors]
    return sorted(
        selected,
        key=lambda value: hashlib.sha256(f"option:{entropy}:{value}".encode()).hexdigest(),
    )


def build_round(
    current: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    round_seconds: int = 3600,
    now: datetime | None = None,
    salt: str | None = None,
    external_entropy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    bucket = int(now.timestamp()) // max(round_seconds, 60)
    diagnosis, signal = detect(current, history)
    round_seed = hashlib.sha256(
        f"{current['state_hash']}:{diagnosis}".encode()
    ).hexdigest()
    # Identity is the measured field, not the clock — a stable hash must not
    # mint a new puzzle every bucket with the same diagnosis.
    round_id = f"sig_{hashlib.sha256(current['state_hash'].encode()).hexdigest()[:16]}"
    answer_salt = salt or secrets.token_hex(24)
    commitment = hashlib.sha256(
        f"{round_id}:{diagnosis}:{answer_salt}".encode()
    ).hexdigest()
    expires = datetime.fromtimestamp((bucket + 1) * max(round_seconds, 60), tz=UTC)
    evidence = evidence_blocks(current, history)
    severity = "calm" if diagnosis == "stable" else "anomaly"
    follow_up, follow_reveal = build_follow_up(
        current,
        history,
        diagnosis=diagnosis,
        round_seed=round_seed,
        diagnosis_params=signal if isinstance(signal, dict) else None,
    )
    prime = prime_window(now)
    # Public mission card stays sealed: naming the detector class next to the MCQ
    # spoiled the investigation. Reveal travels only with a submitted verdict.
    public_payload = {
        "id": round_id,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "observation": {
            "id": current["observation_id"],
            "state_hash": current["state_hash"],
            "observed_at": current["observed_at"],
            "hub_url": current["hub_url"],
            "hub_name": current["hub_name"],
            "capabilities": current["capabilities"],
            "source_count": len(current["sources"]),
            "sources": current["sources"],
            "peer_count": len(_peer_roster(current)),
            # Roster identity only — measured RTT stays behind the latency evidence block.
            "peers": [
                {
                    "url": _peer_url(peer),
                    "name": peer.get("name") or _peer_url(peer),
                    "capabilities_count": peer.get("capabilities_count"),
                }
                for peer in (current.get("peers") or [])
                if isinstance(peer, dict) and _peer_url(peer)
            ],
            "latency": {
                "measured_count": int(
                    (current.get("latency") or {}).get("measured_count")
                    or sum(
                        1 for peer in (current.get("peers") or [])
                        if isinstance(peer, dict) and isinstance(peer.get("latency_ms"), (int, float))
                    )
                ),
            },
            "sources_status": current["sources_status"],
        },
        "signal": {
            "sealed": True,
            "severity": severity,
            "history_depth": len(history),
        },
        "follow_up": follow_up,
        "prime": {
            "active": prime["active"],
            "multiplier": prime["multiplier"],
            "ends_at": prime["ends_at"],
            "next_starts_at": prime["next_starts_at"],
        },
        "options": _options(round_seed, diagnosis, external_entropy),
        "evidence": [
            {"id": key, "kind": value["kind"]} for key, value in evidence.items()
        ],
        "answer_commitment": commitment,
        "federation_assist": external_entropy or {
            "status": "unavailable",
            "reason": "not_requested",
            "capability_id": "sortes.draw@v1",
        },
        # Stored in the immutable round record, removed from every public round response.
        # Keeping the evidence with the round prevents later snapshots from changing clues.
        "_evidence_payload": evidence,
        "_signal_reveal": {"code": diagnosis, "params": signal, "severity": severity},
        "_follow_up_reveal": follow_reveal,
    }
    return {
        "id": round_id,
        "state_hash": current["state_hash"],
        "created_at": public_payload["created_at"],
        "expires_at": public_payload["expires_at"],
        "diagnosis_code": diagnosis,
        "answer_salt": answer_salt,
        "answer_commitment": commitment,
        "payload": public_payload,
        "evidence_payload": evidence,
    }


def score_answer(
    *, selected: str, answer: str, confidence: float, option_count: int, evidence_count: int
) -> dict[str, Any]:
    if option_count < 2:
        raise ValueError("option_count must be at least 2")
    minimum = 1 / option_count
    if not minimum <= confidence <= 1:
        raise ValueError(f"confidence must be between {minimum:.4f} and 1")
    rest = (1 - confidence) / (option_count - 1)
    # The Brier sum needs all options, not all global diagnosis classes. Non-selected
    # options have `rest`; one of them is the true answer when the selection is wrong.
    if selected == answer:
        brier = (confidence - 1) ** 2 + (option_count - 1) * rest**2
    else:
        brier = confidence**2 + (rest - 1) ** 2 + (option_count - 2) * rest**2
    baseline = 1 - 1 / option_count
    skill = max(0.0, 1 - brier / baseline)
    evidence_factor = max(0.70, 1 - 0.05 * evidence_count)
    score = round(1000 * skill * evidence_factor)
    return {
        "brier": round(brier, 8),
        "brier_baseline": round(baseline, 8),
        "skill": round(skill, 8),
        "evidence_count": evidence_count,
        "evidence_factor": round(evidence_factor, 8),
        "score": score,
        "selected_probability": confidence,
        "remaining_probability_each": round(rest, 8),
        "probability_sum": round(confidence + rest * (option_count - 1), 8),
        "option_count": option_count,
        "correct": selected == answer,
    }


def verify_commitment(round_id: str, answer: str, salt: str, commitment: str) -> bool:
    actual = hashlib.sha256(f"{round_id}:{answer}:{salt}".encode()).hexdigest()
    return secrets.compare_digest(actual, commitment)
