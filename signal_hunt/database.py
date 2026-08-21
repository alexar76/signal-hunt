from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
import hashlib


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class GameDatabase:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    state_hash TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_time
                    ON snapshots(observed_at DESC);

                CREATE TABLE IF NOT EXISTS rounds (
                    id TEXT PRIMARY KEY,
                    state_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    diagnosis_code TEXT NOT NULL,
                    answer_salt TEXT NOT NULL,
                    answer_commitment TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rounds_time ON rounds(created_at DESC);

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    handle TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    public_profile INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS evidence_views (
                    round_id TEXT NOT NULL REFERENCES rounds(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    evidence_id TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    PRIMARY KEY(round_id, session_id, evidence_id)
                );

                CREATE TABLE IF NOT EXISTS submissions (
                    round_id TEXT NOT NULL REFERENCES rounds(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    answer_code TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    correct INTEGER NOT NULL,
                    brier REAL NOT NULL,
                    skill REAL NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    evidence_factor REAL NOT NULL,
                    score INTEGER NOT NULL,
                    submitted_at TEXT NOT NULL,
                    verdict_json TEXT NOT NULL,
                    PRIMARY KEY(round_id, session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_submissions_score
                    ON submissions(score DESC, submitted_at ASC);

                CREATE TABLE IF NOT EXISTS rewards (
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    code TEXT NOT NULL,
                    earned_at TEXT NOT NULL,
                    round_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(session_id, code)
                );

                CREATE TABLE IF NOT EXISTS hero_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hero_events_time
                    ON hero_events(created_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS presence (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
                    seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_presence_seen ON presence(seen_at DESC);
                """
            )
            columns = {
                str(row[1]) for row in self._db.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "public_profile" not in columns:
                self._db.execute(
                    "ALTER TABLE sessions ADD COLUMN public_profile INTEGER NOT NULL DEFAULT 0"
                )
            sub_columns = {
                str(row[1]) for row in self._db.execute("PRAGMA table_info(submissions)").fetchall()
            }
            if "diagnosis_code" not in sub_columns:
                self._db.execute(
                    "ALTER TABLE submissions ADD COLUMN diagnosis_code TEXT NOT NULL DEFAULT ''"
                )
            if "prime" not in sub_columns:
                self._db.execute(
                    "ALTER TABLE submissions ADD COLUMN prime INTEGER NOT NULL DEFAULT 0"
                )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO snapshots(id,state_hash,observed_at,payload_json) "
                "VALUES(?,?,?,?)",
                (
                    snapshot["observation_id"],
                    snapshot["state_hash"],
                    snapshot["observed_at"],
                    json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def recent_snapshots(self, limit: int = 20, *, before_id: str = "") -> list[dict[str, Any]]:
        with self._lock:
            if before_id:
                rows = self._db.execute(
                    "SELECT payload_json FROM snapshots WHERE id != ? "
                    "ORDER BY observed_at DESC LIMIT ?",
                    (before_id, limit),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT payload_json FROM snapshots ORDER BY observed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def snapshot_count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM snapshots").fetchone()
        return int(row[0]) if row else 0

    def prune_snapshots(self, keep: int) -> int:
        keep = max(int(keep), 1)
        with self._lock, self._db:
            row = self._db.execute("SELECT COUNT(*) FROM snapshots").fetchone()
            total = int(row[0]) if row else 0
            extra = total - keep
            if extra <= 0:
                return 0
            doomed = [
                row[0]
                for row in self._db.execute(
                    "SELECT id FROM snapshots ORDER BY observed_at ASC LIMIT ?",
                    (extra,),
                ).fetchall()
            ]
            self._db.execute(
                f"DELETE FROM snapshots WHERE id IN ({','.join('?' * len(doomed))})",
                doomed,
            )
            return extra

    def latest_round_for_state_hash(self, state_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM rounds WHERE state_hash=? ORDER BY created_at DESC LIMIT 1",
                (state_hash,),
            ).fetchone()
        if row is None:
            return None
        return self._round_record(row)

    def extend_round_expiry(self, round_id: str, expires_at: str) -> None:
        record = self.get_round(round_id)
        if record is None:
            return
        payload = dict(record["payload"])
        payload["expires_at"] = expires_at
        with self._lock, self._db:
            self._db.execute(
                "UPDATE rounds SET expires_at=?, payload_json=? WHERE id=?",
                (
                    expires_at,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    round_id,
                ),
            )

    @staticmethod
    def _round_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "state_hash": row["state_hash"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "diagnosis_code": row["diagnosis_code"],
            "answer_salt": row["answer_salt"],
            "answer_commitment": row["answer_commitment"],
            "payload": json.loads(row["payload_json"]),
        }

    def save_round(self, record: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO rounds"
                "(id,state_hash,created_at,expires_at,diagnosis_code,answer_salt,"
                "answer_commitment,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    record["id"], record["state_hash"], record["created_at"],
                    record["expires_at"], record["diagnosis_code"], record["answer_salt"],
                    record["answer_commitment"],
                    json.dumps(record["payload"], ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def replace_round(self, record: dict[str, Any]) -> None:
        """Overwrite an unplayed round when richer history becomes available."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO rounds"
                "(id,state_hash,created_at,expires_at,diagnosis_code,answer_salt,"
                "answer_commitment,payload_json) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "state_hash=excluded.state_hash, created_at=excluded.created_at, "
                "expires_at=excluded.expires_at, diagnosis_code=excluded.diagnosis_code, "
                "answer_salt=excluded.answer_salt, answer_commitment=excluded.answer_commitment, "
                "payload_json=excluded.payload_json",
                (
                    record["id"], record["state_hash"], record["created_at"],
                    record["expires_at"], record["diagnosis_code"], record["answer_salt"],
                    record["answer_commitment"],
                    json.dumps(record["payload"], ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def get_round(self, round_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
        if row is None:
            return None
        return self._round_record(row)

    def upsert_session(
        self, session_id: str, handle: str, public_profile: bool = False
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions(id,handle,created_at,public_profile) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET handle=excluded.handle, "
                "public_profile=excluded.public_profile",
                (session_id, handle, now, int(public_profile)),
            )
            row = self._db.execute(
                "SELECT id,handle,created_at,public_profile FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        result = dict(row)
        result["public_profile"] = bool(result["public_profile"])
        return result

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id,handle,created_at,public_profile FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["public_profile"] = bool(result["public_profile"])
        return result

    def update_session(self, session_id: str, handle: str, public_profile: bool) -> dict[str, Any]:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET handle=?, public_profile=? WHERE id=?",
                (handle, int(public_profile), session_id),
            )
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def open_evidence(self, round_id: str, session_id: str, evidence_id: str) -> int:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO evidence_views(round_id,session_id,evidence_id,opened_at) "
                "VALUES(?,?,?,?)",
                (round_id, session_id, evidence_id, utc_now()),
            )
            row = self._db.execute(
                "SELECT COUNT(*) FROM evidence_views WHERE round_id=? AND session_id=?",
                (round_id, session_id),
            ).fetchone()
        return int(row[0])

    def opened_evidence(self, round_id: str, session_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT evidence_id FROM evidence_views WHERE round_id=? AND session_id=? "
                "ORDER BY opened_at",
                (round_id, session_id),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def get_submission(self, round_id: str, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT verdict_json FROM submissions WHERE round_id=? AND session_id=?",
                (round_id, session_id),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_submission(
        self,
        *,
        round_id: str,
        session_id: str,
        answer_code: str,
        confidence: float,
        verdict: dict[str, Any],
        diagnosis_code: str = "",
        prime: bool = False,
    ) -> dict[str, Any]:
        serialized = json.dumps(verdict, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO submissions"
                "(round_id,session_id,answer_code,confidence,correct,brier,skill,"
                "evidence_count,evidence_factor,score,submitted_at,verdict_json,"
                "diagnosis_code,prime) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    round_id, session_id, answer_code, confidence,
                    int(bool(verdict["correct"])), verdict["scoring"]["brier"],
                    verdict["scoring"]["skill"], verdict["scoring"]["evidence_count"],
                    verdict["scoring"]["evidence_factor"], verdict["score"],
                    verdict["submitted_at"], serialized,
                    diagnosis_code or str(verdict.get("answer") or ""),
                    int(bool(prime)),
                ),
            )
            row = self._db.execute(
                "SELECT verdict_json FROM submissions WHERE round_id=? AND session_id=?",
                (round_id, session_id),
            ).fetchone()
        return json.loads(row[0])

    def touch_presence(self, session_id: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO presence(session_id, seen_at) VALUES(?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET seen_at=excluded.seen_at",
                (session_id, utc_now()),
            )

    def presence_count(self, *, within_seconds: int = 900) -> int:
        cutoff = datetime.now(UTC).timestamp() - within_seconds
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat().replace("+00:00", "Z")
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) FROM presence WHERE seen_at >= ?",
                (cutoff_iso,),
            ).fetchone()
        return int(row[0])

    def round_solve_count(self, round_id: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) FROM submissions WHERE round_id=?",
                (round_id,),
            ).fetchone()
        return int(row[0])

    def player_play_days(self, session_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT DISTINCT substr(submitted_at, 1, 10) AS day "
                "FROM submissions WHERE session_id=? ORDER BY day ASC",
                (session_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def season_stats(self, session_id: str, week: str) -> dict[str, Any]:
        """Weekly score / distinct correct diagnoses / prime corrects for ISO week_id."""
        # submitted_at is ISO-Z; filter in Python for portable week matching.
        with self._lock:
            rows = self._db.execute(
                "SELECT score, correct, diagnosis_code, prime, submitted_at, verdict_json "
                "FROM submissions WHERE session_id=?",
                (session_id,),
            ).fetchall()
        weekly_score = 0
        distinct: set[str] = set()
        prime_corrects = 0
        for row in rows:
            try:
                submitted = datetime.fromisoformat(
                    str(row["submitted_at"]).replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                continue
            iso = submitted.isocalendar()
            wid = f"{iso.year}-W{iso.week:02d}"
            if wid != week:
                continue
            weekly_score += int(row["score"] or 0)
            if bool(row["correct"]) and row["diagnosis_code"]:
                distinct.add(str(row["diagnosis_code"]))
            if bool(row["correct"]) and bool(row["prime"]):
                prime_corrects += 1
        return {
            "weekly_score": weekly_score,
            "distinct_correct_diagnoses": sorted(distinct),
            "prime_corrects": prime_corrects,
        }

    def hero_event_for_round(self, session_id: str, round_id: str) -> dict[str, Any] | None:
        event_id = "hero_" + hashlib.sha256(
            f"{session_id}:{round_id}".encode()
        ).hexdigest()[:24]
        with self._lock:
            row = self._db.execute(
                "SELECT payload_json FROM hero_events WHERE id=?",
                (event_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def weekly_leaderboard(self, week: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT s.handle, v.session_id, v.score, v.correct, v.submitted_at
                FROM submissions v
                JOIN sessions s ON s.id = v.session_id
                """
            ).fetchall()
        totals: dict[str, dict[str, Any]] = {}
        for row in rows:
            try:
                submitted = datetime.fromisoformat(
                    str(row["submitted_at"]).replace("Z", "+00:00")
                ).astimezone(UTC)
            except ValueError:
                continue
            iso = submitted.isocalendar()
            wid = f"{iso.year}-W{iso.week:02d}"
            if wid != week:
                continue
            bucket = totals.setdefault(
                row["session_id"],
                {"handle": row["handle"], "score": 0, "rounds": 0, "correct": 0},
            )
            bucket["score"] += int(row["score"] or 0)
            bucket["rounds"] += 1
            bucket["correct"] += int(row["correct"] or 0)
        ordered = sorted(
            totals.values(),
            key=lambda item: (-item["score"], -item["correct"], item["handle"]),
        )[:limit]
        return [
            {
                "rank": idx + 1,
                "handle": item["handle"],
                "score": item["score"],
                "rounds": item["rounds"],
                "correct": item["correct"],
                "week_id": week,
            }
            for idx, item in enumerate(ordered)
        ]

    def update_submission_verdict(
        self, round_id: str, session_id: str, verdict: dict[str, Any]
    ) -> None:
        serialized = json.dumps(verdict, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._db:
            self._db.execute(
                "UPDATE submissions SET verdict_json=? WHERE round_id=? AND session_id=?",
                (serialized, round_id, session_id),
            )

    def player_stats(self, session_id: str) -> dict[str, Any]:
        from .engagement import daily_streak_state, season_progress, utc_day, week_id

        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        with self._lock:
            rows = self._db.execute(
                "SELECT correct,score,brier,submitted_at FROM submissions "
                "WHERE session_id=? ORDER BY submitted_at ASC, round_id ASC",
                (session_id,),
            ).fetchall()
        streak = 0
        best_streak = 0
        for row in rows:
            streak = streak + 1 if bool(row["correct"]) else 0
            best_streak = max(best_streak, streak)
        total = len(rows)
        correct = sum(int(row["correct"]) for row in rows)
        play_days = [utc_day(str(row["submitted_at"])) for row in rows]
        daily = daily_streak_state(play_days)
        week = week_id()
        season_raw = self.season_stats(session_id, week)
        season = season_progress(
            week=week,
            weekly_score=int(season_raw["weekly_score"]),
            distinct_correct_diagnoses=list(season_raw["distinct_correct_diagnoses"]),
            prime_corrects=int(season_raw["prime_corrects"]),
        )
        return {
            "id": session["id"],
            "handle": session["handle"],
            "public_profile": session["public_profile"],
            "created_at": session["created_at"],
            "score": sum(int(row["score"]) for row in rows),
            "rounds": total,
            "correct": correct,
            "accuracy": round(correct / total, 6) if total else None,
            "mean_brier": round(sum(float(row["brier"]) for row in rows) / total, 6)
            if total else None,
            "current_streak": streak,
            "best_streak": best_streak,
            "last_played_at": rows[-1]["submitted_at"] if rows else None,
            "daily_streak": daily["daily_streak"],
            "daily_streak_meta": daily,
            "season": season,
        }

    def grant_reward(
        self, session_id: str, code: str, round_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        earned_at = utc_now()
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO rewards(session_id,code,earned_at,round_id,payload_json) "
                "VALUES(?,?,?,?,?)",
                (session_id, code, earned_at, round_id, serialized),
            )
        if cursor.rowcount == 0:
            return None
        return {**payload, "earned_at": earned_at, "round_id": round_id}

    def rewards(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT code,earned_at,round_id,payload_json FROM rewards "
                "WHERE session_id=? ORDER BY earned_at ASC, code ASC",
                (session_id,),
            ).fetchall()
        return [
            {
                **json.loads(row["payload_json"]),
                "code": row["code"],
                "earned_at": row["earned_at"],
                "round_id": row["round_id"],
            }
            for row in rows
        ]

    def save_hero_event(self, event_id: str, session_id: str, payload: dict[str, Any]) -> bool:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO hero_events(id,session_id,created_at,payload_json) "
                "VALUES(?,?,?,?)",
                (event_id, session_id, payload["created_at"], serialized),
            )
        return cursor.rowcount > 0

    def hero_events(self, limit: int = 100) -> list[dict[str, Any]]:
        # Only sessions that still have public_profile=1 appear in the feed.
        # Opt-out therefore revokes future broadcast of already-stored events;
        # opt-in never backfills — events are written only at submit time.
        with self._lock:
            rows = self._db.execute(
                "SELECT he.payload_json FROM hero_events he "
                "JOIN sessions s ON s.id = he.session_id "
                "WHERE s.public_profile = 1 "
                "ORDER BY he.created_at DESC, he.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def leaderboard(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT s.handle,
                       SUM(v.score) AS score,
                       COUNT(*) AS rounds,
                       SUM(v.correct) AS correct,
                       AVG(v.brier) AS mean_brier,
                       MAX(v.submitted_at) AS last_played_at
                FROM submissions v
                JOIN sessions s ON s.id=v.session_id
                GROUP BY v.session_id, s.handle
                ORDER BY score DESC, correct DESC, mean_brier ASC, last_played_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "rank": idx + 1,
                "handle": row["handle"],
                "score": int(row["score"]),
                "rounds": int(row["rounds"]),
                "correct": int(row["correct"]),
                "mean_brier": round(float(row["mean_brier"]), 6),
                "last_played_at": row["last_played_at"],
            }
            for idx, row in enumerate(rows)
        ]
