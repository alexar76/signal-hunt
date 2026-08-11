from __future__ import annotations

from datetime import UTC, date, datetime

from signal_hunt.engagement import (
    FOLLOW_UP_BONUS,
    PRIME_MULTIPLIER,
    apply_score_modifiers,
    build_follow_up,
    daily_streak_state,
    prime_window,
    score_follow_up,
    season_progress,
    week_id,
)


def test_prime_window_first_quarter_hour():
    hot = prime_window(datetime(2026, 8, 10, 12, 7, tzinfo=UTC))
    cold = prime_window(datetime(2026, 8, 10, 12, 20, tzinfo=UTC))
    assert hot["active"] is True
    assert hot["multiplier"] == PRIME_MULTIPLIER
    assert cold["active"] is False
    assert cold["multiplier"] == 1.0


def test_follow_up_leading_source_and_bonus():
    current = {
        "capabilities": {"external": 53},
        "prices": {"median_usd": 0.01},
        "sources": [
            {"id": "https://oracles", "capabilities": 42},
            {"id": "https://iot", "capabilities": 11},
        ],
    }
    public, reveal = build_follow_up(
        current, [], diagnosis="source_concentration", round_seed="round-1"
    )
    assert public["kind"] == "leading_source"
    assert reveal["answer"] == "https://oracles"
    assert reveal["answer"] in public["options"]
    hit = score_follow_up(selected=reveal["answer"], answer=reveal["answer"])
    miss = score_follow_up(selected="https://iot", answer=reveal["answer"])
    skip = score_follow_up(selected=None, answer=reveal["answer"])
    assert hit["bonus"] == FOLLOW_UP_BONUS and hit["correct"] is True
    assert miss["bonus"] == 0 and miss["correct"] is False
    assert skip["answered"] is False and skip["bonus"] == 0


def test_score_modifiers_stack_follow_up_then_prime():
    modified = apply_score_modifiers(800, follow_up_bonus=150, prime_active=True)
    assert modified["base_score"] == 800
    assert modified["score"] == round((800 + 150) * 1.5)


def test_daily_streak_with_one_day_shield():
    today = date(2026, 8, 10)
    days = [date(2026, 8, 7), date(2026, 8, 8), date(2026, 8, 10)]
    state = daily_streak_state(days, today=today)
    assert state["played_today"] is True
    assert state["shield_used"] is True
    assert state["daily_streak"] == 3
    assert state["alive"] is True


def test_follow_up_slowest_peer_for_latency_weather():
    current = {
        "capabilities": {"external": 30},
        "prices": {"median_usd": 0.01},
        "sources": [{"id": "https://a", "capabilities": 20}, {"id": "https://b", "capabilities": 10}],
        "peers": [
            {"url": "https://fast.example", "name": "fast", "latency_ms": 100},
            {"url": "https://slow.example", "name": "slow", "latency_ms": 900},
        ],
    }
    public, reveal = build_follow_up(
        current, [], diagnosis="latency_weather", round_seed="lat-1"
    )
    assert public["kind"] == "slowest_peer"
    assert reveal["answer"] == "https://slow.example"
    assert reveal["answer"] in public["options"]


def test_follow_up_roster_event_for_peer_churn():
    history = [
        {"peers": [{"url": "https://alpha.example", "name": "alpha"}]},
        {"peers": [{"url": "https://alpha.example", "name": "alpha"}]},
    ]
    current = {
        "capabilities": {"external": 30},
        "prices": {},
        "sources": [{"id": "https://a", "capabilities": 30}],
        "peers": [
            {"url": "https://alpha.example", "name": "alpha"},
            {"url": "https://beta.example", "name": "beta"},
        ],
    }
    public, reveal = build_follow_up(
        current,
        history,
        diagnosis="peer_churn",
        round_seed="peer-1",
        diagnosis_params={
            "joined": [{"peer_url": "https://beta.example"}],
            "left": [],
            "joined_count": 1,
            "left_count": 0,
        },
    )
    assert public["kind"] == "roster_event"
    assert reveal["answer"] == "joined"


def test_follow_up_roster_event_both_and_left():
    history = [
        {
            "peers": [
                {"url": "https://alpha.example"},
                {"url": "https://beta.example"},
            ],
        },
        {
            "peers": [
                {"url": "https://alpha.example"},
                {"url": "https://beta.example"},
            ],
        },
    ]
    current = {
        "capabilities": {"external": 10},
        "prices": {},
        "sources": [{"id": "https://a", "capabilities": 10}],
        "peers": [{"url": "https://gamma.example"}],
    }
    public, reveal = build_follow_up(
        current,
        history,
        diagnosis="peer_churn",
        round_seed="peer-both",
        diagnosis_params={
            "joined": [{"peer_url": "https://gamma.example"}],
            "left": [
                {"peer_url": "https://alpha.example"},
                {"peer_url": "https://beta.example"},
            ],
            "joined_count": 1,
            "left_count": 2,
        },
    )
    assert public["kind"] == "roster_event"
    assert reveal["answer"] == "both"
    assert "both" in public["options"]

    left_only = {
        "capabilities": {"external": 10},
        "prices": {},
        "sources": [{"id": "https://a", "capabilities": 10}],
        "peers": [{"url": "https://alpha.example"}],
    }
    _public, reveal_left = build_follow_up(
        left_only,
        history,
        diagnosis="peer_churn",
        round_seed="peer-left",
        diagnosis_params={
            "joined": [],
            "left": [{"peer_url": "https://beta.example"}],
            "joined_count": 0,
            "left_count": 1,
        },
    )
    assert reveal_left["answer"] == "left"


def test_follow_up_roster_gates_match_detector_without_params():
    """Single-sighting disappearances must not count as leave (detector gates)."""
    history = [{"peers": [{"url": "https://alpha.example"}]}]
    current = {
        "capabilities": {"external": 10},
        "prices": {},
        "sources": [{"id": "https://a", "capabilities": 10}],
        "peers": [{"url": "https://beta.example"}],
    }
    _public, reveal = build_follow_up(
        current, history, diagnosis="peer_churn", round_seed="gated"
    )
    assert reveal["kind"] == "roster_event"
    assert reveal["answer"] == "stable"
    assert reveal["joined_count"] == 0
    assert reveal["left_count"] == 0
