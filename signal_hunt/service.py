from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from .config import Settings
from .database import GameDatabase, utc_now
from .detector import build_round, score_answer
from .engagement import (
    PRESENCE_WINDOW_SECONDS,
    apply_score_modifiers,
    cliffhanger,
    prime_window,
    score_follow_up,
)
from .federation import FederationClient
from .progression import TIERS, earned_badges, profile_payload, reward_payload, tier_for_score
from .signing import SessionTokens

_HANDLE = re.compile(r"^[\w.-]{2,24}$", re.UNICODE)


class GameError(ValueError):
    def __init__(self, code: str, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class GameService:
    def __init__(
        self,
        settings: Settings,
        db: GameDatabase,
        federation: FederationClient,
        tokens: SessionTokens,
    ):
        self.settings = settings
        self.db = db
        self.federation = federation
        self.tokens = tokens
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._observation_lock = asyncio.Lock()

    def create_session(
        self, handle: str | None = None, public_profile: bool = False
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        chosen = (handle or f"observer-{session_id[:6]}").strip()
        if not _HANDLE.fullmatch(chosen):
            raise GameError(
                "invalid_handle",
                "handle must be 2-24 letters, numbers, underscore, dot or dash",
            )
        session = self.db.upsert_session(session_id, chosen, public_profile)
        return {**session, "token": self.tokens.issue(session_id)}

    def authenticate(self, token: str) -> dict[str, str]:
        session_id = self.tokens.verify(token)
        session = self.db.get_session(session_id) if session_id else None
        if session is None:
            raise GameError("invalid_session", "valid session token required", 401)
        return session

    @staticmethod
    def _validate_handle(handle: str) -> str:
        chosen = handle.strip()
        if not _HANDLE.fullmatch(chosen):
            raise GameError(
                "invalid_handle",
                "handle must be 2-24 letters, numbers, underscore, dot or dash",
            )
        return chosen

    def update_profile(
        self, session_id: str, handle: str, public_profile: bool
    ) -> dict[str, Any]:
        self.db.update_session(
            session_id, self._validate_handle(handle), bool(public_profile)
        )
        return self.profile(session_id)

    def profile(self, session_id: str) -> dict[str, Any]:
        stats = self.db.player_stats(session_id)
        return profile_payload(stats, self.db.rewards(session_id))

    async def observation(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._cache and now - self._cache[0] < self.settings.observation_cache_s:
            return self._cache[1]
        async with self._observation_lock:
            now = time.monotonic()
            if self._cache and now - self._cache[0] < self.settings.observation_cache_s:
                return self._cache[1]
            snapshot = await self.federation.snapshot()
            self.db.save_snapshot(snapshot)
            self._cache = (now, snapshot)
            return snapshot

    async def live_round(self, session_id: str) -> dict[str, Any]:
        self.db.touch_presence(session_id)
        current = await self.observation()
        history = self.db.recent_snapshots(20, before_id=current["observation_id"])
        now = datetime.now(UTC)
        provisional = build_round(
            current, history, round_seconds=self.settings.round_seconds, now=now
        )
        existing = self.db.get_round(provisional["id"])
        if existing is not None:
            sealed_depth = int(
                ((existing.get("payload") or {}).get("signal") or {}).get("history_depth")
                or 0
            )
            # Cold first snap in a bucket sealed hist=0 forever; refresh while unplayed.
            if (
                len(history) <= sealed_depth
                or self.db.round_solve_count(existing["id"]) > 0
            ):
                return self._public_round(existing, session_id)
        bucket = int(now.timestamp()) // max(self.settings.round_seconds, 60)
        assist = await self.federation.fairness_seed(
            f"signal-hunt:{current['state_hash']}:{bucket}"
        )
        built = build_round(
            current,
            history,
            round_seconds=self.settings.round_seconds,
            now=now,
            external_entropy=assist,
        )
        if existing is not None:
            self.db.replace_round(built)
        else:
            self.db.save_round(built)
        record = self.db.get_round(built["id"])
        assert record is not None
        return self._public_round(record, session_id)

    def round_by_id(self, round_id: str, session_id: str) -> dict[str, Any]:
        record = self.db.get_round(round_id)
        if record is None:
            raise GameError("round_not_found", "round not found", 404)
        return self._public_round(record, session_id)

    def _public_round(self, record: dict[str, Any], session_id: str) -> dict[str, Any]:
        payload = dict(record["payload"])
        payload.pop("_evidence_payload", None)
        reveal = payload.pop("_signal_reveal", None)
        payload.pop("_follow_up_reveal", None)
        payload.setdefault(
            "federation_assist",
            {
                "status": "unavailable",
                "reason": "legacy_round",
                "capability_id": "sortes.draw@v1",
            },
        )
        live_prime = prime_window()
        stored_prime = payload.get("prime") if isinstance(payload.get("prime"), dict) else {}
        locked = bool(stored_prime.get("active"))
        payload["prime"] = {
            # Scoring lock for THIS round — never OR with the live window.
            "active": locked,
            "locked_for_round": locked,
            "multiplier": float(stored_prime.get("multiplier") or 1.0) if locked else 1.0,
            # Live UTC window (informational only when the round was born cold).
            "window_active": bool(live_prime["active"]),
            "window_multiplier": float(live_prime["multiplier"]),
            "ends_at": live_prime["ends_at"] if live_prime["active"] else None,
            "next_starts_at": live_prime["next_starts_at"],
        }
        opened = self.db.opened_evidence(record["id"], session_id)
        submitted = self.db.get_submission(record["id"], session_id)
        payload["opened_evidence"] = opened
        payload["submitted"] = submitted is not None
        if reveal is None:
            legacy = payload.get("signal") or {}
            if isinstance(legacy, dict) and legacy.get("code"):
                reveal = {
                    "code": legacy["code"],
                    "params": legacy.get("params") or {},
                    "severity": (
                        "calm" if legacy["code"] == "stable" else "anomaly"
                    ),
                }
        if submitted and reveal is not None:
            payload["signal"] = {
                "sealed": False,
                "severity": reveal.get("severity")
                or ("calm" if reveal["code"] == "stable" else "anomaly"),
                "history_depth": (payload.get("signal") or {}).get("history_depth"),
                "code": reveal["code"],
                "params": reveal.get("params") or {},
            }
        else:
            severity = (
                reveal.get("severity")
                if isinstance(reveal, dict) and reveal.get("severity")
                else (
                    "calm"
                    if record.get("diagnosis_code") == "stable"
                    else "anomaly"
                )
            )
            history_depth = (payload.get("signal") or {}).get("history_depth")
            if history_depth is None and isinstance(reveal, dict):
                history_depth = (reveal.get("params") or {}).get("sample_size")
            payload["signal"] = {
                "sealed": True,
                "severity": severity,
                "history_depth": history_depth,
            }
        payload["engagement"] = {
            "presence": {
                "active_observers": self.db.presence_count(
                    within_seconds=PRESENCE_WINDOW_SECONDS
                ),
                "solved_this_round": self.db.round_solve_count(record["id"]),
                "window_seconds": PRESENCE_WINDOW_SECONDS,
            },
            "cliffhanger": cliffhanger(
                expires_at=record["expires_at"],
                severity=None if not submitted else (payload.get("signal") or {}).get("severity"),
            ),
        }
        if submitted:
            payload["verdict"] = submitted
            payload["broadcast_available"] = self._broadcast_available(
                session_id, record["id"], submitted
            )
        return payload

    def _broadcast_available(
        self, session_id: str, round_id: str, verdict: dict[str, Any]
    ) -> bool:
        session = self.db.get_session(session_id)
        if not session or not session["public_profile"]:
            return False
        if self.db.hero_event_for_round(session_id, round_id):
            return False
        score = int(verdict.get("score") or 0)
        rewards = [
            str(item.get("code") or "")
            for item in (verdict.get("progression") or {}).get("new_rewards") or []
        ]
        all_reward_codes = rewards + [
            str(item.get("code") or "")
            for item in ((verdict.get("progression") or {}).get("profile") or {}).get("rewards")
            or []
        ]
        return score >= 950 or "perfect_orbit" in all_reward_codes

    def submit(
        self,
        round_id: str,
        session_id: str,
        answer_code: str,
        confidence: float,
        follow_up_answer: str | None = None,
    ) -> dict[str, Any]:
        self.db.touch_presence(session_id)
        existing = self.db.get_submission(round_id, session_id)
        if existing is not None:
            return existing
        record = self.db.get_round(round_id)
        if record is None:
            raise GameError("round_not_found", "round not found", 404)
        options = list(record["payload"]["options"])
        if answer_code not in options:
            raise GameError("invalid_answer", "answer must be one of the round options")
        follow_public = record["payload"].get("follow_up") or {}
        follow_reveal = record["payload"].get("_follow_up_reveal") or {}
        if follow_up_answer and follow_up_answer not in list(follow_public.get("options") or []):
            raise GameError("invalid_follow_up", "follow-up answer must be one of the options")
        opened_count = len(self.db.opened_evidence(round_id, session_id))
        scoring = score_answer(
            selected=answer_code,
            answer=record["diagnosis_code"],
            confidence=float(confidence),
            option_count=len(options),
            evidence_count=opened_count,
        )
        follow = score_follow_up(
            selected=follow_up_answer,
            answer=str(follow_reveal.get("answer") or ""),
        )
        # PRIME multiplier locks to the round's creation-time flag so late submits
        # in a PRIME-born round keep the bonus, while non-PRIME rounds stay fair.
        round_prime = bool((record["payload"].get("prime") or {}).get("active"))
        modified = apply_score_modifiers(
            int(scoring["score"]),
            follow_up_bonus=int(follow["bonus"]),
            prime_active=round_prime,
        )
        scoring = {
            **scoring,
            "follow_up_bonus": modified["follow_up_bonus"],
            "prime_active": modified["prime_active"],
            "prime_multiplier": modified["prime_multiplier"],
            "base_score": modified["base_score"],
            "score": modified["score"],
        }
        submitted_at = utc_now()
        verdict = {
            "round_id": round_id,
            "submitted_at": submitted_at,
            "selected": answer_code,
            "answer": record["diagnosis_code"],
            "correct": scoring["correct"],
            "score": scoring["score"],
            "scoring": scoring,
            "follow_up": follow,
            "prime": {
                "active": round_prime,
                "multiplier": modified["prime_multiplier"],
            },
            "integrity": {
                "answer_commitment": record["answer_commitment"],
                "answer_salt": record["answer_salt"],
                "state_hash": record["state_hash"],
                "formula": "SHA256(round_id:answer_code:answer_salt)",
            },
            "cliffhanger": cliffhanger(expires_at=record["expires_at"]),
        }
        saved = self.db.save_submission(
            round_id=round_id,
            session_id=session_id,
            answer_code=answer_code,
            confidence=float(confidence),
            verdict=verdict,
            diagnosis_code=record["diagnosis_code"],
            prime=round_prime,
        )
        stats = self.db.player_stats(session_id)
        codes = earned_badges(stats, saved)
        tier = tier_for_score(int(stats["score"]))
        if tier.code != TIERS[0].code:
            codes.append(f"tier:{tier.code}")
        new_rewards = [
            reward
            for code in codes
            if (
                reward := self.db.grant_reward(
                    session_id, code, round_id, reward_payload(code)
                )
            )
            is not None
        ]
        profile = profile_payload(stats, self.db.rewards(session_id))
        saved["progression"] = {
            "profile": profile,
            "new_rewards": new_rewards,
        }
        saved["broadcast_available"] = self._broadcast_available(session_id, round_id, saved)
        self.db.update_submission_verdict(round_id, session_id, saved)
        session = self.db.get_session(session_id)
        reward_codes = [str(item["code"]) for item in new_rewards]
        high_orbit = int(scoring["score"]) >= 900
        if session and session["public_profile"] and (new_rewards or high_orbit):
            self._write_hero_event(
                session=session,
                session_id=session_id,
                round_id=round_id,
                record=record,
                saved=saved,
                submitted_at=submitted_at,
                reward_codes=reward_codes,
                high_orbit=high_orbit,
                event_type_hint=None,
            )
        return saved

    def _write_hero_event(
        self,
        *,
        session: dict[str, Any],
        session_id: str,
        round_id: str,
        record: dict[str, Any],
        saved: dict[str, Any],
        submitted_at: str,
        reward_codes: list[str],
        high_orbit: bool,
        event_type_hint: str | None,
    ) -> dict[str, Any] | None:
        event_id = "hero_" + hashlib.sha256(
            f"{session_id}:{round_id}".encode()
        ).hexdigest()[:24]
        codes = list(reward_codes)
        if high_orbit and "orbit:high" not in codes:
            codes = [*codes, "orbit:high"]
        profile = (saved.get("progression") or {}).get("profile") or self.profile(session_id)
        event = {
            "id": event_id,
            "schema": "aicom.signal-hunt.hero.v1",
            "created_at": submitted_at,
            "handle": session["handle"],
            "event_type": event_type_hint
            or (
                "promotion"
                if any(code.startswith("tier:") for code in codes)
                else "achievement"
            ),
            "status": profile["tier"]["code"],
            "score": profile["score"],
            "rounds": profile["rounds"],
            "correct": profile["correct"],
            "best_streak": profile["best_streak"],
            "rewards": codes,
            "proof": {
                "round_id": round_id,
                "state_hash": record["state_hash"],
                "answer_commitment": record["answer_commitment"],
                "verdict_sha256": hashlib.sha256(
                    json.dumps(
                        saved["integrity"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            },
            "url": f"{self.settings.public_url}/#heroes",
        }
        if self.db.save_hero_event(event_id, session_id, event):
            return event
        return self.db.hero_event_for_round(session_id, round_id)

    def broadcast(self, round_id: str, session_id: str) -> dict[str, Any]:
        """One-tap public ritual after a strong verified verdict."""
        session = self.db.get_session(session_id)
        if session is None:
            raise GameError("invalid_session", "valid session required", 401)
        if not session["public_profile"]:
            raise GameError(
                "broadcast_private",
                "enable public hero relay before broadcasting",
                403,
            )
        record = self.db.get_round(round_id)
        if record is None:
            raise GameError("round_not_found", "round not found", 404)
        verdict = self.db.get_submission(round_id, session_id)
        if verdict is None:
            raise GameError("not_submitted", "submit a verdict before broadcasting", 400)
        if not self._broadcast_available(session_id, round_id, verdict):
            existing = self.db.hero_event_for_round(session_id, round_id)
            if existing:
                return {"ok": True, "event": existing, "already": True}
            raise GameError(
                "broadcast_unavailable",
                "broadcast requires a strong verified orbit (score ≥ 950 or perfect orbit)",
                400,
            )
        event = self._write_hero_event(
            session=session,
            session_id=session_id,
            round_id=round_id,
            record=record,
            saved=verdict,
            submitted_at=utc_now(),
            reward_codes=[
                str(item.get("code") or "")
                for item in (verdict.get("progression") or {}).get("new_rewards") or []
            ],
            high_orbit=int(verdict.get("score") or 0) >= 900,
            event_type_hint="broadcast",
        )
        return {"ok": True, "event": event, "already": False}

    def weekly_leaderboard(self, limit: int = 20) -> dict[str, Any]:
        from .engagement import week_id

        week = week_id()
        entries = self.db.weekly_leaderboard(week, limit)
        for entry in entries:
            entry["tier"] = tier_for_score(int(entry["score"])).code
        return {"week_id": week, "entries": entries}

    def evidence(
        self, round_id: str, evidence_id: str, session_id: str
    ) -> dict[str, Any]:
        record = self.db.get_round(round_id)
        if record is None:
            raise GameError("round_not_found", "round not found", 404)
        evidence_payload = record["payload"].get("_evidence_payload")
        if evidence_payload is None:
            # Evidence is deliberately not in the public payload. Reconstruct it from the
            # immutable observation snapshot referenced by state_hash.
            snapshots = self.db.recent_snapshots(100)
            current = next(
                (row for row in snapshots if row["state_hash"] == record["state_hash"]), None
            )
            if current is None:
                raise GameError("evidence_unavailable", "observation no longer available", 503)
            history = [row for row in snapshots if row["observation_id"] != current["observation_id"]]
            from .detector import evidence_blocks

            evidence_payload = evidence_blocks(current, history[:20])
        if evidence_id not in evidence_payload:
            raise GameError("evidence_not_found", "evidence not found", 404)
        opened_count = self.db.open_evidence(round_id, session_id, evidence_id)
        block = evidence_payload[evidence_id]
        return {
            "round_id": round_id,
            "evidence_id": evidence_id,
            "opened_count": opened_count,
            "kind": block.get("kind") if isinstance(block, dict) else None,
            "data": block,
        }

    def leaderboard(self, limit: int = 20) -> dict[str, Any]:
        entries = self.db.leaderboard(min(max(limit, 1), 100))
        for entry in entries:
            tier = tier_for_score(int(entry["score"]))
            entry["tier"] = tier.code
        return {
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "entries": entries,
            "ranking": "sum(score), correct desc, mean_brier asc, first completion",
        }

    def heroes(self, limit: int = 100) -> dict[str, Any]:
        return {
            "schema": "aicom.signal-hunt.heroes.v1",
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": self.settings.public_url,
            "events": self.db.hero_events(min(max(limit, 1), 200)),
        }
