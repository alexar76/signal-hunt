"""Engagement layer: follow-up, PRIME windows, streaks, season, presence helpers.

All answers stay grounded in measured observation data — no invented telemetry.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any


PRIME_WINDOW_SECONDS = 900  # first 15 minutes of each UTC hour
PRIME_MULTIPLIER = 1.5
FOLLOW_UP_BONUS = 150
PRESENCE_WINDOW_SECONDS = 900


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def prime_window(now: datetime | None = None) -> dict[str, Any]:
    """UTC hourly hot window: minutes 0–14 are PRIME."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    prime_end = hour_start + timedelta(seconds=PRIME_WINDOW_SECONDS)
    active = hour_start <= now < prime_end
    if active:
        next_start = hour_start + timedelta(hours=1)
        ends_at = prime_end
    else:
        next_start = hour_start + timedelta(hours=1)
        ends_at = None
    return {
        "active": active,
        "multiplier": PRIME_MULTIPLIER if active else 1.0,
        "ends_at": _iso(ends_at) if ends_at else None,
        "next_starts_at": _iso(next_start),
        "window_seconds": PRIME_WINDOW_SECONDS,
    }


def week_id(now: datetime | None = None) -> str:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _pick_follow_up_kind(diagnosis: str, current: dict[str, Any], history: list[dict[str, Any]]) -> str:
    sources = current.get("sources") or []
    peers = [row for row in (current.get("peers") or []) if isinstance(row, dict) and row.get("url")]
    measured = [
        row for row in peers
        if isinstance(row.get("latency_ms"), (int, float))
    ]
    has_price = isinstance(current.get("prices", {}).get("median_usd"), (int, float))
    hist_prices = [
        row.get("prices", {}).get("median_usd")
        for row in history
        if isinstance(row.get("prices", {}).get("median_usd"), (int, float))
    ]
    if diagnosis == "latency_weather" and measured:
        return "slowest_peer"
    if diagnosis == "peer_churn" and peers:
        return "roster_event"
    if diagnosis in {"source_concentration", "source_disappearance"} and len(sources) >= 2:
        return "leading_source"
    if diagnosis == "price_shift" and has_price and hist_prices:
        return "price_direction"
    if measured:
        return "slowest_peer"
    if len(sources) >= 2:
        return "leading_source"
    if has_price and hist_prices:
        return "price_direction"
    return "external_band"


def _order_ids(seed: str, values: list[str]) -> list[str]:
    return sorted(
        values,
        key=lambda value: hashlib.sha256(f"fu:{seed}:{value}".encode()).hexdigest(),
    )


def build_follow_up(
    current: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    diagnosis: str,
    round_seed: str,
    diagnosis_params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (public_follow_up, private_reveal)."""
    kind = _pick_follow_up_kind(diagnosis, current, history)
    sources = list(current.get("sources") or [])
    peers = [
        row for row in (current.get("peers") or [])
        if isinstance(row, dict) and row.get("url")
    ]

    if kind == "slowest_peer" and peers:
        measured = [
            row for row in peers
            if isinstance(row.get("latency_ms"), (int, float))
        ]
        if measured:
            ranked = sorted(
                measured,
                key=lambda row: (-float(row["latency_ms"]), str(row.get("url") or "")),
            )
            answer = str(ranked[0]["url"])
            option_ids = _order_ids(
                round_seed,
                [str(row["url"]) for row in ranked[:3]],
            )
            if answer not in option_ids:
                option_ids = _order_ids(round_seed, [*option_ids[:2], answer])
            public = {
                "id": "follow_up",
                "kind": "slowest_peer",
                "prompt": "followUp.slowest_peer",
                "options": option_ids,
            }
            return public, {
                "kind": kind,
                "answer": answer,
                "latency_ms": round(float(ranked[0]["latency_ms"]), 2),
            }

    if kind == "roster_event":
        # Prefer sealed detector params so follow-up cannot disagree with peer_churn
        # (leave needs ≥2 sightings; join needs history depth ≥2).
        params = diagnosis_params if isinstance(diagnosis_params, dict) else {}
        if diagnosis == "peer_churn" and (
            "joined" in params or "left" in params
            or "joined_count" in params or "left_count" in params
        ):
            joined_n = int(params.get("joined_count") or len(params.get("joined") or []))
            left_n = int(params.get("left_count") or len(params.get("left") or []))
        else:
            from .thresholds import PEER_JOIN_MIN_HISTORY, PEER_LEAVE_MIN_SIGHTINGS

            sightings: dict[str, int] = {}
            for snapshot in history:
                for peer in snapshot.get("peers") or []:
                    if isinstance(peer, dict) and peer.get("url"):
                        url = str(peer["url"]).rstrip("/")
                        sightings[url] = sightings.get(url, 0) + 1
            cur_urls = {str(row["url"]).rstrip("/") for row in peers}
            left_n = sum(
                1
                for url, count in sightings.items()
                if url not in cur_urls and count >= PEER_LEAVE_MIN_SIGHTINGS
            )
            joined_n = 0
            if len(history) >= PEER_JOIN_MIN_HISTORY:
                joined_n = sum(1 for url in cur_urls if url not in sightings)
        if left_n and not joined_n:
            answer = "left"
        elif joined_n and not left_n:
            answer = "joined"
        elif joined_n and left_n:
            answer = "both"
        else:
            answer = "stable"
        public = {
            "id": "follow_up",
            "kind": "roster_event",
            "prompt": "followUp.roster_event",
            "options": _order_ids(round_seed, ["joined", "left", "both", "stable"]),
        }
        return public, {
            "kind": kind,
            "answer": answer,
            "joined_count": joined_n,
            "left_count": left_n,
        }

    if kind == "leading_source" and sources:
        ranked = sorted(
            sources,
            key=lambda row: (-int(row.get("capabilities") or 0), str(row.get("id") or "")),
        )
        leader = ranked[0]
        leader_caps = int(leader.get("capabilities") or 0)
        tied = [
            row for row in ranked
            if int(row.get("capabilities") or 0) == leader_caps
        ]
        answer = "tie" if len(tied) > 1 else str(leader["id"])
        option_ids = _order_ids(
            round_seed,
            [str(row["id"]) for row in ranked[:3]] + (["tie"] if answer == "tie" or len(ranked) >= 2 else []),
        )
        # Ensure answer is always among options.
        if answer not in option_ids:
            option_ids = _order_ids(round_seed, [*option_ids[:3], answer])
        public = {
            "id": "follow_up",
            "kind": "leading_source",
            "prompt": "followUp.leading_source",
            "options": option_ids,
        }
        return public, {"kind": kind, "answer": answer}

    if kind == "price_direction":
        import statistics

        current_price = float(current["prices"]["median_usd"])
        hist = [
            float(row["prices"]["median_usd"])
            for row in history
            if isinstance(row.get("prices", {}).get("median_usd"), (int, float))
        ]
        baseline = float(statistics.median(hist))
        if abs(current_price - baseline) < 1e-9:
            answer = "flat"
        elif current_price > baseline:
            answer = "up"
        else:
            answer = "down"
        public = {
            "id": "follow_up",
            "kind": "price_direction",
            "prompt": "followUp.price_direction",
            "options": _order_ids(round_seed, ["up", "down", "flat"]),
        }
        return public, {"kind": kind, "answer": answer, "baseline_median_usd": baseline}

    external = int(current["capabilities"]["external"])
    if external <= 10:
        answer = "0_10"
    elif external <= 50:
        answer = "11_50"
    else:
        answer = "51_plus"
    public = {
        "id": "follow_up",
        "kind": "external_band",
        "prompt": "followUp.external_band",
        "options": _order_ids(round_seed, ["0_10", "11_50", "51_plus"]),
    }
    return public, {"kind": "external_band", "answer": answer}


def score_follow_up(*, selected: str | None, answer: str) -> dict[str, Any]:
    if not selected:
        return {
            "answered": False,
            "correct": False,
            "bonus": 0,
            "answer": answer,
            "selected": None,
        }
    correct = selected == answer
    return {
        "answered": True,
        "correct": correct,
        "bonus": FOLLOW_UP_BONUS if correct else 0,
        "answer": answer,
        "selected": selected,
    }


def apply_score_modifiers(
    base_score: int,
    *,
    follow_up_bonus: int,
    prime_active: bool,
) -> dict[str, Any]:
    combined = int(base_score) + int(follow_up_bonus)
    multiplier = PRIME_MULTIPLIER if prime_active else 1.0
    final = round(combined * multiplier)
    return {
        "base_score": int(base_score),
        "follow_up_bonus": int(follow_up_bonus),
        "prime_active": bool(prime_active),
        "prime_multiplier": multiplier,
        "score": final,
    }


def utc_day(value: str | datetime | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(UTC).date()


def daily_streak_state(
    play_days: list[date],
    *,
    today: date | None = None,
    shield_available: bool = True,
) -> dict[str, Any]:
    """Calendar-day return streak with one missed-day shield per evaluation.

    Shield consumes a single gap of exactly one missed day when available.
    """
    today = today or datetime.now(UTC).date()
    days = sorted(set(play_days))
    if not days:
        end_of_day = datetime(today.year, today.month, today.day, tzinfo=UTC) + timedelta(days=1)
        return {
            "daily_streak": 0,
            "played_today": False,
            "shield_available": shield_available,
            "shield_used": False,
            "expires_at": _iso(end_of_day),
            "alive": False,
        }

    played_today = today in days
    cursor = today if played_today else today - timedelta(days=1)
    streak = 0
    shield_used = False
    shield_left = shield_available
    day = cursor
    day_set = set(days)
    # Walk backwards; allow one one-day gap if shield remains.
    while True:
        if day in day_set:
            streak += 1
            day -= timedelta(days=1)
            continue
        gap_day = day
        prev = gap_day - timedelta(days=1)
        if shield_left and prev in day_set:
            shield_left = False
            shield_used = True
            day = prev
            continue
        break

    alive = played_today or (today - timedelta(days=1)) in day_set or (
        shield_available and (today - timedelta(days=2)) in day_set
    )
    end_of_day = datetime(today.year, today.month, today.day, tzinfo=UTC) + timedelta(days=1)
    return {
        "daily_streak": streak,
        "played_today": played_today,
        "shield_available": shield_left,
        "shield_used": shield_used,
        "expires_at": _iso(end_of_day),
        "alive": alive and streak > 0,
    }


def season_progress(
    *,
    week: str,
    weekly_score: int,
    distinct_correct_diagnoses: list[str],
    prime_corrects: int,
) -> dict[str, Any]:
    codes = sorted(set(distinct_correct_diagnoses))
    badges: list[str] = []
    if len(codes) >= 3:
        badges.append("season_polyglot")
    if weekly_score >= 3_000:
        badges.append("season_hunter")
    if prime_corrects >= 3:
        badges.append("season_prime_runner")
    return {
        "week_id": week,
        "score": weekly_score,
        "distinct_diagnoses": codes,
        "prime_corrects": prime_corrects,
        "badges": badges,
        "targets": {
            "polyglot": 3,
            "hunter": 3_000,
            "prime_runner": 3,
        },
    }


def cliffhanger(*, expires_at: str, severity: str | None = None) -> dict[str, Any]:
    return {
        "next_opens_at": expires_at,
        "teaser": "cliffhanger.teaser",
        "preview_severity": severity,
    }
