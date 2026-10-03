"""Progression badges — deep_scan tracks the declared evidence block count."""

from __future__ import annotations

from signal_hunt.detector import EVIDENCE_ORDER
from signal_hunt.progression import earned_badges


def _verdict(*, correct: bool, evidence_count: int, score: int = 500, brier: float = 0.2):
    return {
        "correct": correct,
        "score": score,
        "scoring": {
            "brier": brier,
            "evidence_count": evidence_count,
            "selected_probability": 0.8,
        },
        "follow_up": {"correct": False},
    }


def test_deep_scan_requires_all_declared_evidence_blocks():
    stats = {"rounds": 1, "best_streak": 0, "daily_streak": 0, "season": {}}
    assert "deep_scan" not in earned_badges(
        stats, _verdict(correct=True, evidence_count=len(EVIDENCE_ORDER) - 1)
    )
    assert "deep_scan" in earned_badges(
        stats, _verdict(correct=True, evidence_count=len(EVIDENCE_ORDER))
    )
    assert len(EVIDENCE_ORDER) == 6


def test_deep_scan_not_awarded_on_incorrect_verdict():
    stats = {"rounds": 1, "best_streak": 0, "daily_streak": 0, "season": {}}
    assert "deep_scan" not in earned_badges(
        stats, _verdict(correct=False, evidence_count=6)
    )
