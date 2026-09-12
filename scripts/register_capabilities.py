#!/usr/bin/env python3
"""Register Signal Hunt's operator-owned local capabilities in its ordinary Hub."""
from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability


PRODUCT_ID = "signal-hunt"


CAPABILITIES = (
    (
        "signal.case@v1",
        "case_current",
        "Return the current immutable Signal Hunt round derived from measured federation telemetry.",
        {
            "type": "object",
            "required": ["session_token"],
            "properties": {"session_token": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    (
        "signal.evidence@v1",
        "evidence_open",
        "Reveal one evidence block committed to a Signal Hunt round.",
        {
            "type": "object",
            "required": ["session_token", "round_id", "evidence_id"],
            "properties": {
                "session_token": {"type": "string"},
                "round_id": {"type": "string"},
                "evidence_id": {
                    "type": "string",
                    "enum": ["distribution", "change", "pricing", "provenance"],
                },
            },
            "additionalProperties": False,
        },
    ),
    (
        "signal.submit@v1",
        "diagnosis_submit",
        "Commit one diagnosis and receive a deterministic Brier-scored verdict.",
        {
            "type": "object",
            "required": ["session_token", "round_id", "answer_code", "confidence"],
            "properties": {
                "session_token": {"type": "string"},
                "round_id": {"type": "string"},
                "answer_code": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.25, "maximum": 1},
            },
            "additionalProperties": False,
        },
    ),
    (
        "signal.leaderboard@v1",
        "leaderboard",
        "Return pseudonymous rankings computed only from persisted verified submissions.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "additionalProperties": False,
        },
    ),
    (
        "signal.heroes@v1",
        "heroes_feed",
        "Return opt-in hero milestones currently eligible for public display. "
        "Unsigned Hub invoke body — DIOSCURI must pull the Ed25519-signed "
        "HTTP feed at GET /api/v1/heroes/feed instead.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            "additionalProperties": False,
        },
    ),
)


def request_json(url: str, body: dict | None = None) -> tuple[dict, float]:
    encoded = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json"} if encoded else {},
        method="POST" if encoded else "GET",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    return payload, (time.perf_counter() - started) * 1000


def main() -> None:
    db_path = os.getenv("AIMARKET_DB_PATH", "/app/data/hub.db")
    internal_provider = os.getenv(
        "SIGNAL_HUNT_INTERNAL_PROVIDER_URL", "http://game:8060/provider"
    ).rstrip("/")
    public_provider = os.environ["SIGNAL_HUNT_PUBLIC_URL"].rstrip("/") + "/provider/invoke"
    key_doc, _ = request_json(f"{internal_provider}/public-key")
    public_key = str(key_doc["public_key"])

    latencies: list[float] = []
    successes = 0
    probe = {
        "product_id": PRODUCT_ID,
        "capability_id": "signal.leaderboard@v1",
        "input": {"limit": 1},
    }
    for _ in range(5):
        try:
            payload, elapsed = request_json(f"{internal_provider}/invoke", probe)
            latencies.append(elapsed)
            successes += int(isinstance(payload, dict) and "result" in payload)
        except Exception:
            latencies.append(10_000.0)
    if successes == 0:
        raise SystemExit("provider registration probe failed: no successful response")
    measured_p50_ms = max(1, round(statistics.median(latencies)))
    measured_success = successes / len(latencies)

    db = HubDatabase(db_path)
    try:
        for capability_id, name, description, input_schema in CAPABILITIES:
            db.upsert_capability(
                Capability(
                    product_id=PRODUCT_ID,
                    capability_id=capability_id,
                    name=name,
                    version="v1",
                    description=description,
                    input_schema=input_schema,
                    output_schema={"type": "object"},
                    price_per_call_usd=0.0,
                    p50_latency_ms=measured_p50_ms,
                    success_rate_30d=measured_success,
                    source_hub="local",
                    source_hub_name="Signal Hunt",
                    routed_price_usd=0.0,
                    routing_fee_bps=0,
                    trust_score=1.0,
                    invoke_url=public_provider,
                    publisher_id="signal-hunt-operator",
                    provider_pubkey=public_key,
                    is_demo=False,
                )
            )
        print(
            json.dumps(
                {
                    "registered": len(CAPABILITIES),
                    "product_id": PRODUCT_ID,
                    "provider_public_key": public_key,
                    "registration_probe_p50_ms": measured_p50_ms,
                    "registration_probe_successes": successes,
                    "registration_probe_attempts": len(latencies),
                },
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
