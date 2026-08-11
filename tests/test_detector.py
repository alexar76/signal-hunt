from __future__ import annotations

from datetime import UTC, datetime

from signal_hunt.detector import build_round, detect, score_answer, verify_commitment


def snapshot(
    *,
    state: str,
    sources: dict[str, int],
    median_price: float | None = 0.01,
    peers: list[dict] | None = None,
    peers_status: str = "ok",
) -> dict:
    external = sum(sources.values())
    peer_rows = peers if peers is not None else []
    measured = [
        float(row["latency_ms"])
        for row in peer_rows
        if isinstance(row.get("latency_ms"), (int, float))
    ]
    return {
        "observation_id": f"obs-{state}",
        "state_hash": state * 64,
        "observed_at": "2026-08-10T10:00:00Z",
        "hub_url": "https://hunt.example",
        "hub_name": "Signal Hunt Hub",
        "hub_generated_at": "2026-08-10T09:59:59Z",
        "signer_public_key": "real-key-from-fixture",
        "capabilities": {"total": external + 4, "local": 4, "external": external},
        "sources": [
            {
                "id": name,
                "name": name,
                "capabilities": count,
                "share": count / external if external else None,
                "price_min_usd": median_price,
                "price_median_usd": median_price,
                "price_max_usd": median_price,
            }
            for name, count in sources.items()
        ],
        "prices": {
            "count": external,
            "min_usd": median_price,
            "median_usd": median_price,
            "p90_usd": median_price,
            "max_usd": median_price,
        },
        "peers": peer_rows,
        "latency": {
            "measured_count": len(measured),
            "max_ms": max(measured) if measured else None,
            "median_ms": sorted(measured)[len(measured) // 2] if measured else None,
        },
        "settlement": {},
        "sources_status": {
            "manifest": {"status": "ok", "elapsed_ms": 12.4},
            "well_known": {"status": "ok", "elapsed_ms": 9.1},
            "peers": {"status": peers_status, "elapsed_ms": 8.2},
            "stats": {"status": "unavailable", "elapsed_ms": 5.1},
        },
    }


def test_first_observation_detects_measured_concentration_without_fake_baseline():
    code, params = detect(snapshot(state="a", sources={"oracle": 42, "iot": 11}), [])
    assert code == "source_concentration"
    assert params == {
        "source_hub": "oracle",
        "capabilities": 42,
        "external_total": 53,
        "share_pct": 79.25,
        "source_count": 2,
    }


def test_historical_median_drives_catalog_contraction():
    history = [
        snapshot(state=str(index), sources={"a": 40, "b": 10})
        for index in range(5)
    ]
    code, params = detect(snapshot(state="x", sources={"a": 25, "b": 5}), history)
    assert code == "catalog_contraction"
    assert params["baseline_median"] == 50
    assert params["current"] == 30
    assert params["change_pct"] == -40
    assert params["sample_size"] == 5


def test_zero_external_capabilities_is_isolation_not_stability():
    code, params = detect(snapshot(state="z", sources={}, median_price=None), [])
    assert code == "federation_isolated"
    assert params["external_capabilities"] == 0


def test_round_commitment_is_published_and_verifiable():
    current = snapshot(state="a", sources={"oracle": 42, "iot": 11})
    round_record = build_round(
        current,
        [],
        now=datetime(2026, 8, 10, 10, 15, tzinfo=UTC),
        salt="fixed-review-salt",
    )
    assert "diagnosis_code" not in round_record["payload"]
    assert round_record["payload"]["signal"]["sealed"] is True
    assert "code" not in round_record["payload"]["signal"]
    assert round_record["payload"]["_signal_reveal"]["code"] == round_record["diagnosis_code"]
    assert verify_commitment(
        round_record["id"],
        round_record["diagnosis_code"],
        round_record["answer_salt"],
        round_record["answer_commitment"],
    )
    assert set(round_record["payload"]["options"]) >= {"source_concentration"}


def test_brier_score_is_reproducible_and_evidence_penalty_is_bounded():
    perfect = score_answer(
        selected="stable", answer="stable", confidence=1, option_count=4, evidence_count=0
    )
    assert perfect["brier"] == 0
    assert perfect["skill"] == 1
    assert perfect["score"] == 1000
    informed = score_answer(
        selected="stable", answer="stable", confidence=0.75, option_count=4, evidence_count=4
    )
    assert informed["probability_sum"] == 1
    assert informed["evidence_factor"] == 0.8
    assert 0 < informed["score"] < 1000
    wrong_confident = score_answer(
        selected="price_shift", answer="stable", confidence=1, option_count=4, evidence_count=0
    )
    assert wrong_confident["score"] == 0


def test_uniform_guess_scores_zero_skill():
    result = score_answer(
        selected="stable", answer="stable", confidence=0.25, option_count=4, evidence_count=0
    )
    assert result["brier"] == result["brier_baseline"]
    assert result["skill"] == 0
    assert result["score"] == 0


def _peer(url: str, *, name: str | None = None, caps: int = 4, latency_ms: float | None = None):
    row = {
        "url": url,
        "name": name or url,
        "capabilities_count": caps,
        "probe_status": "ok" if latency_ms is not None else "skipped",
        "latency_ms": latency_ms,
    }
    return row


def test_peer_departure_is_peer_churn_not_source_disappearance():
    history = [
        snapshot(
            state=str(index),
            sources={"oracle": 20, "iot": 18},
            peers=[_peer("https://alpha.example", name="alpha"), _peer("https://beta.example", name="beta")],
        )
        for index in range(3)
    ]
    current = snapshot(
        state="now",
        sources={"oracle": 20, "iot": 18},
        peers=[_peer("https://alpha.example", name="alpha")],
    )
    code, params = detect(current, history)
    assert code == "peer_churn"
    assert params["left_count"] == 1
    assert params["joined_count"] == 0
    assert params["left"][0]["peer_url"] == "https://beta.example"


def test_peer_arrival_requires_history_depth():
    history = [
        snapshot(
            state=str(index),
            sources={"oracle": 20, "iot": 18},
            peers=[_peer("https://alpha.example", name="alpha")],
        )
        for index in range(2)
    ]
    current = snapshot(
        state="now",
        sources={"oracle": 20, "iot": 18},
        peers=[
            _peer("https://alpha.example", name="alpha"),
            _peer("https://gamma.example", name="gamma", caps=8),
        ],
    )
    code, params = detect(current, history)
    assert code == "peer_churn"
    assert params["joined_count"] == 1
    assert params["joined"][0]["peer_url"] == "https://gamma.example"


def test_peer_churn_skipped_when_peers_endpoint_unavailable():
    history = [
        snapshot(
            state=str(index),
            sources={"oracle": 20, "iot": 18},
            peers=[_peer("https://alpha.example")],
        )
        for index in range(3)
    ]
    current = snapshot(
        state="now",
        sources={"oracle": 20, "iot": 18},
        peers=[],
        peers_status="unavailable",
    )
    code, params = detect(current, history)
    assert code != "peer_churn"


def test_latency_weather_uses_measured_rtt_only():
    current = snapshot(
        state="hot",
        sources={"oracle": 20, "iot": 18},
        peers=[
            _peer("https://fast.example", name="fast", latency_ms=120),
            _peer("https://slow.example", name="slow", latency_ms=820),
        ],
    )
    code, params = detect(current, [])
    assert code == "latency_weather"
    assert params["threshold_ms"] == 500
    assert params["slow_count"] == 1
    assert params["slowest_peer_url"] == "https://slow.example"
    assert params["max_ms"] == 820


def test_null_latency_never_invents_weather():
    current = snapshot(
        state="calm",
        sources={"oracle": 20, "iot": 18},
        peers=[
            _peer("https://a.example", name="a"),
            _peer("https://b.example", name="b"),
        ],
    )
    code, _params = detect(current, [])
    assert code != "latency_weather"


def test_latency_below_threshold_is_not_weather():
    current = snapshot(
        state="ok",
        sources={"oracle": 20, "iot": 18},
        peers=[
            _peer("https://a.example", latency_ms=200),
            _peer("https://b.example", latency_ms=350),
        ],
    )
    code, _params = detect(current, [])
    assert code != "latency_weather"


def test_evidence_includes_roster_and_latency_blocks():
    current = snapshot(
        state="e",
        sources={"oracle": 20, "iot": 18},
        peers=[_peer("https://a.example", latency_ms=900)],
    )
    from signal_hunt.detector import EVIDENCE_ORDER, evidence_blocks

    blocks = evidence_blocks(current, [])
    assert list(blocks) == list(EVIDENCE_ORDER)
    assert blocks["roster"]["kind"] == "peer_roster"
    assert blocks["latency"]["kind"] == "latency_surface"
    assert blocks["latency"]["slow_count"] == 1
    assert blocks["latency"]["threshold_ms"] == 500


def test_six_evidence_opens_hit_score_floor():
    result = score_answer(
        selected="stable", answer="stable", confidence=1, option_count=4, evidence_count=6
    )
    assert result["evidence_factor"] == 0.7
    assert result["score"] == 700


def test_diagnoses_include_new_fuel_classes():
    from signal_hunt.detector import DIAGNOSES

    assert "peer_churn" in DIAGNOSES
    assert "latency_weather" in DIAGNOSES
    assert DIAGNOSES.index("peer_churn") < DIAGNOSES.index("catalog_contraction")
    assert DIAGNOSES.index("latency_weather") < DIAGNOSES.index("source_concentration")


def test_peer_join_ignored_when_history_too_shallow():
    history = [
        snapshot(
            state="0",
            sources={"oracle": 20, "iot": 18},
            peers=[_peer("https://alpha.example", name="alpha")],
        )
    ]
    current = snapshot(
        state="now",
        sources={"oracle": 20, "iot": 18},
        peers=[
            _peer("https://alpha.example", name="alpha"),
            _peer("https://gamma.example", name="gamma"),
        ],
    )
    code, _params = detect(current, history)
    assert code != "peer_churn"


def test_peer_leave_ignored_with_single_sighting():
    history = [
        snapshot(
            state="0",
            sources={"oracle": 20, "iot": 18},
            peers=[
                _peer("https://alpha.example", name="alpha"),
                _peer("https://beta.example", name="beta"),
            ],
        )
    ]
    current = snapshot(
        state="now",
        sources={"oracle": 20, "iot": 18},
        peers=[_peer("https://alpha.example", name="alpha")],
    )
    code, _params = detect(current, history)
    assert code != "peer_churn"


def test_peer_churn_reports_both_join_and_leave():
    history = [
        snapshot(
            state=str(index),
            sources={"oracle": 20, "iot": 18},
            peers=[
                _peer("https://alpha.example", name="alpha"),
                _peer("https://beta.example", name="beta"),
            ],
        )
        for index in range(2)
    ]
    current = snapshot(
        state="now",
        sources={"oracle": 20, "iot": 18},
        peers=[
            _peer("https://alpha.example", name="alpha"),
            _peer("https://gamma.example", name="gamma"),
        ],
    )
    code, params = detect(current, history)
    assert code == "peer_churn"
    assert params["left_count"] == 1
    assert params["joined_count"] == 1
    assert params["left"][0]["peer_url"] == "https://beta.example"
    assert params["joined"][0]["peer_url"] == "https://gamma.example"


def test_peer_churn_beats_catalog_expansion():
    history = [
        snapshot(
            state=str(index),
            sources={"oracle": 10, "iot": 10},
            peers=[_peer("https://alpha.example"), _peer("https://beta.example")],
        )
        for index in range(3)
    ]
    # Big catalog expansion AND a peer left — peer_churn must win by precedence.
    current = snapshot(
        state="now",
        sources={"oracle": 40, "iot": 40},
        peers=[_peer("https://alpha.example")],
    )
    code, params = detect(current, history)
    assert code == "peer_churn"
    assert params["left_count"] == 1


def test_latency_weather_beats_concentration_when_both_true():
    current = snapshot(
        state="hot",
        sources={"oracle": 42, "iot": 11},
        peers=[_peer("https://slow.example", name="slow", latency_ms=900)],
    )
    code, params = detect(current, [])
    assert code == "latency_weather"
    assert params["slowest_peer_name"] == "slow"


def test_build_round_exposes_peers_without_free_rtt():
    current = snapshot(
        state="r",
        sources={"oracle": 20, "iot": 18},
        peers=[_peer("https://a.example", latency_ms=120)],
    )
    record = build_round(current, [], salt="peer-round-salt")
    observation = record["payload"]["observation"]
    assert observation["peer_count"] == 1
    assert observation["peers"][0]["url"] == "https://a.example"
    assert "latency_ms" not in observation["peers"][0]
    assert observation["latency"]["measured_count"] == 1
    evidence_ids = [row["id"] for row in record["payload"]["evidence"]]
    assert evidence_ids == [
        "distribution", "change", "pricing", "roster", "latency", "provenance",
    ]
    assert record["diagnosis_code"] in record["payload"]["options"]
    assert len(record["payload"]["options"]) == 4
    # RTT detail lives only in the paid latency evidence block.
    lat = record["payload"]["_evidence_payload"]["latency"]
    assert lat["peers"][0]["latency_ms"] == 120


def test_follow_up_roster_matches_sealed_peer_churn_params():
    from signal_hunt.engagement import build_follow_up

    current = {
        "capabilities": {"external": 30},
        "prices": {},
        "sources": [{"id": "https://a", "capabilities": 30}],
        "peers": [{"url": "https://new.example"}],
    }
    # Detector would not count a leave with a single sighting — sealed params win.
    public, reveal = build_follow_up(
        current,
        [{"peers": [{"url": "https://gone.example"}]}],
        diagnosis="peer_churn",
        round_seed="sealed-roster",
        diagnosis_params={
            "joined": [{"peer_url": "https://new.example"}],
            "left": [],
            "joined_count": 1,
            "left_count": 0,
        },
    )
    assert public["kind"] == "roster_event"
    assert reveal["answer"] == "joined"
    assert reveal["left_count"] == 0
