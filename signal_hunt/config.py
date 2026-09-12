from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _origins() -> tuple[str, ...]:
    raw = os.getenv("SIGNAL_HUNT_CORS_ORIGINS", "").strip()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    hub_url: str = field(
        default_factory=lambda: os.getenv(
            "SIGNAL_HUNT_HUB_URL", "http://127.0.0.1:9183"
        ).rstrip("/")
    )
    public_url: str = field(
        default_factory=lambda: os.getenv(
            "SIGNAL_HUNT_PUBLIC_URL", "http://127.0.0.1:8060"
        ).rstrip("/")
    )
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("SIGNAL_HUNT_DATA_DIR", "data/signal-hunt"))
    )
    request_timeout_s: float = field(
        default_factory=lambda: float(os.getenv("SIGNAL_HUNT_REQUEST_TIMEOUT_S", "12"))
    )
    observation_cache_s: float = field(
        default_factory=lambda: float(os.getenv("SIGNAL_HUNT_OBSERVATION_CACHE_S", "30"))
    )
    # Default 30m buckets — hourly felt too sparse for one-shot sessions.
    # Operators can raise SIGNAL_HUNT_ROUND_SECONDS back to 3600 if desired.
    round_seconds: int = field(
        default_factory=lambda: int(os.getenv("SIGNAL_HUNT_ROUND_SECONDS", "1800"))
    )
    # 0 = tests / no background poll. Prod compose sets 300.
    observe_interval_s: float = field(
        default_factory=lambda: float(os.getenv("SIGNAL_HUNT_OBSERVE_INTERVAL_S", "0"))
    )
    snapshot_keep: int = field(
        default_factory=lambda: int(os.getenv("SIGNAL_HUNT_SNAPSHOT_KEEP", "500"))
    )
    cors_origins: tuple[str, ...] = field(default_factory=_origins)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "signal-hunt.db"

    @property
    def provider_key_path(self) -> Path:
        return self.data_dir / "provider_signing_key"

    @property
    def session_secret_path(self) -> Path:
        return self.data_dir / "session_secret"
