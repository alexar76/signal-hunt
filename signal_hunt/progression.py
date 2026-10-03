from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from signal_hunt.detector import EVIDENCE_ORDER


@dataclass(frozen=True)
class Tier:
    code: str
    min_score: int
    accent: str


TIERS = (
    Tier("stargazer", 0, "#7892aa"),
    Tier("pathfinder", 500, "#45e7ff"),
    Tier("signal_analyst", 1_500, "#60ffbf"),
    Tier("void_navigator", 3_500, "#9c70ff"),
    Tier("constellation_keeper", 7_500, "#ff67cf"),
    Tier("federation_oracle", 15_000, "#ffd36a"),
)

BADGES: dict[str, dict[str, str]] = {
    "first_contact": {"rarity": "common", "sigil": "I"},
    "calibrated_mind": {"rarity": "rare", "sigil": "σ"},
    "deep_scan": {"rarity": "rare", "sigil": "◇"},
    "clean_vector": {"rarity": "epic", "sigil": "∆"},
    "minimal_evidence": {"rarity": "epic", "sigil": "Ø"},
    "triple_lock": {"rarity": "epic", "sigil": "III"},
    "seasoned_observer": {"rarity": "rare", "sigil": "V"},
    "perfect_orbit": {"rarity": "legendary", "sigil": "✦"},
    "season_polyglot": {"rarity": "epic", "sigil": "∑"},
    "season_hunter": {"rarity": "epic", "sigil": "⚔"},
    "season_prime_runner": {"rarity": "legendary", "sigil": "☀"},
    "streak_keeper": {"rarity": "rare", "sigil": "🔥"},
    "dual_lock": {"rarity": "rare", "sigil": "Ⅱ"},
}


def tier_for_score(score: int) -> Tier:
    current = TIERS[0]
    for tier in TIERS:
        if score < tier.min_score:
            break
        current = tier
    return current


def profile_payload(stats: dict[str, Any], rewards: list[dict[str, Any]]) -> dict[str, Any]:
    score = int(stats.get("score") or 0)
    tier = tier_for_score(score)
    index = TIERS.index(tier)
    next_tier = TIERS[index + 1] if index + 1 < len(TIERS) else None
    if next_tier is None:
        progress = 1.0
    else:
        span = next_tier.min_score - tier.min_score
        progress = max(0.0, min(1.0, (score - tier.min_score) / span))
    return {
        **stats,
        "tier": {"code": tier.code, "min_score": tier.min_score, "accent": tier.accent},
        "next_tier": (
            {"code": next_tier.code, "min_score": next_tier.min_score, "accent": next_tier.accent}
            if next_tier else None
        ),
        "tier_progress": round(progress, 6),
        "rewards": rewards,
    }


def earned_badges(stats: dict[str, Any], verdict: dict[str, Any]) -> list[str]:
    earned: list[str] = []
    if int(stats.get("rounds") or 0) >= 1:
        earned.append("first_contact")
    if float(verdict["scoring"]["brier"]) <= 0.08:
        earned.append("calibrated_mind")
    if bool(verdict["correct"]) and int(verdict["scoring"]["evidence_count"]) == len(EVIDENCE_ORDER):
        earned.append("deep_scan")
    if bool(verdict["correct"]) and int(verdict["score"]) >= 800:
        earned.append("clean_vector")
    if (
        bool(verdict["correct"])
        and int(verdict["scoring"]["evidence_count"]) == 0
        and float(verdict["scoring"]["selected_probability"]) >= 0.75
    ):
        earned.append("minimal_evidence")
    if int(stats.get("best_streak") or 0) >= 3:
        earned.append("triple_lock")
    if int(stats.get("rounds") or 0) >= 5:
        earned.append("seasoned_observer")
    if bool(verdict["correct"]) and int(verdict["score"]) >= 950:
        earned.append("perfect_orbit")
    follow = verdict.get("follow_up") or {}
    if bool(verdict["correct"]) and bool(follow.get("correct")):
        earned.append("dual_lock")
    if int(stats.get("daily_streak") or 0) >= 3:
        earned.append("streak_keeper")
    season = stats.get("season") or {}
    for code in season.get("badges") or []:
        earned.append(str(code))
    return earned


def reward_payload(code: str) -> dict[str, str]:
    if code.startswith("tier:"):
        tier = next(item for item in TIERS if item.code == code.removeprefix("tier:"))
        return {"code": code, "kind": "status", "rarity": "status", "sigil": "✧", "accent": tier.accent}
    meta = BADGES.get(code) or {"rarity": "rare", "sigil": "◇"}
    return {"code": code, "kind": "badge", **meta}
