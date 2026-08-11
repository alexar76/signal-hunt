from __future__ import annotations

import base64
import hashlib
import json

import httpx

from signal_hunt.app import create_app
from signal_hunt.config import Settings
from signal_hunt.database import GameDatabase
from signal_hunt.signing import ProviderSigner, SessionTokens


def live_snapshot() -> dict:
    return {
        "observation_id": "obs-live",
        "state_hash": "a" * 64,
        "observed_at": "2026-08-10T10:00:00Z",
        "hub_url": "https://hunt.example",
        "hub_name": "Signal Hunt Hub",
        "hub_generated_at": "2026-08-10T09:59:59Z",
        "signer_public_key": "hub-key",
        "capabilities": {"total": 57, "local": 4, "external": 53},
        "sources": [
            {"id": "https://oracles", "name": "Oracles", "capabilities": 42, "share": 42/53, "price_min_usd": 0.001, "price_median_usd": 0.01, "price_max_usd": 0.02},
            {"id": "https://iot", "name": "IoT", "capabilities": 11, "share": 11/53, "price_min_usd": 0.002, "price_median_usd": 0.01, "price_max_usd": 0.05},
        ],
        "prices": {"count": 53, "min_usd": 0.001, "median_usd": 0.01, "p90_usd": 0.02, "max_usd": 0.05},
        "peers": [], "settlement": {},
        "latency": {"measured_count": 0, "probed_count": 0, "unavailable_count": 0, "max_ms": None, "median_ms": None},
        "sources_status": {"manifest": {"status": "ok", "elapsed_ms": 12}, "well_known": {"status": "ok", "elapsed_ms": 8}, "peers": {"status": "ok", "elapsed_ms": 9}, "stats": {"status": "ok", "elapsed_ms": 10}},
    }


class FixedFederation:
    async def snapshot(self):
        return live_snapshot()

    async def fairness_seed(self, alpha: str):
        return {
            "status": "ok",
            "capability_id": "sortes.draw@v1",
            "source_hub": "https://oracles",
            "result_hash": hashlib.sha256(alpha.encode()).hexdigest(),
            "elapsed_ms": 8.5,
        }


async def test_round_evidence_submit_and_idempotency(tmp_path):
    settings = Settings(data_dir=tmp_path, hub_url="https://hunt.example", observation_cache_s=60)
    signer = ProviderSigner(tmp_path / "provider")
    app = create_app(
        settings,
        db=GameDatabase(":memory:"),
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions"),
        signer=signer,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        session = (
            await client.post(
                "/api/v1/session",
                json={"handle": "observer-1", "public_profile": True},
            )
        ).json()
        auth = {"Authorization": f"Bearer {session['token']}"}
        round_response = await client.get("/api/v1/rounds/live", headers=auth)
        assert round_response.status_code == 200
        round_data = round_response.json()
        assert round_data["signal"]["sealed"] is True
        assert "code" not in round_data["signal"]
        assert round_data["signal"]["severity"] in {"anomaly", "calm"}
        assert "source_concentration" in round_data["options"]
        evidence_ids = {row["id"] for row in round_data["evidence"]}
        assert evidence_ids == {
            "distribution", "change", "pricing", "roster", "latency", "provenance",
        }
        assert round_data["observation"].get("peer_count") == 0
        assert "peers" in round_data["observation"]
        assert "latency" in round_data["observation"]
        assert round_data["federation_assist"]["capability_id"] == "sortes.draw@v1"
        assert "_evidence_payload" not in round_data
        assert "follow_up" in round_data
        assert "options" in round_data["follow_up"]
        assert "prime" in round_data
        assert "engagement" in round_data
        assert "presence" in round_data["engagement"]
        evidence = await client.post(
            f"/api/v1/rounds/{round_data['id']}/evidence/distribution", headers=auth
        )
        assert evidence.json()["opened_count"] == 1
        follow_option = round_data["follow_up"]["options"][0]
        submit_body = {
            "answer_code": "source_concentration",
            "confidence": 0.9,
            "follow_up_answer": follow_option,
        }
        first = await client.post(
            f"/api/v1/rounds/{round_data['id']}/submit", headers=auth, json=submit_body
        )
        second = await client.post(
            f"/api/v1/rounds/{round_data['id']}/submit", headers=auth,
            json={"answer_code": "stable", "confidence": 1},
        )
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        verdict = first.json()
        assert verdict["correct"] is True
        assert "follow_up" in verdict
        assert "base_score" in verdict["scoring"]
        assert verdict["score"] == verdict["scoring"]["score"]
        weekly = (await client.get("/api/v1/leaderboard/weekly")).json()
        assert "week_id" in weekly
        assert weekly["entries"]
        revealed = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        assert revealed["signal"]["sealed"] is False
        assert revealed["signal"]["code"] == "source_concentration"
        integrity = verdict["integrity"]
        recomputed = hashlib.sha256(
            f"{round_data['id']}:{verdict['answer']}:{integrity['answer_salt']}".encode()
        ).hexdigest()
        assert recomputed == round_data["answer_commitment"]
        assert verdict["progression"]["profile"]["rounds"] == 1
        assert verdict["progression"]["new_rewards"]
        assert "daily_streak" in verdict["progression"]["profile"]
        assert "season" in verdict["progression"]["profile"]
        profile = (await client.get("/api/v1/profile", headers=auth)).json()
        assert profile["public_profile"] is True
        assert profile["tier"]["code"] != "stargazer"
        feed = (await client.get("/api/v1/heroes/feed")).json()
        padding = "=" * (-len(feed["signed_payload_b64"]) % 4)
        signed = base64.urlsafe_b64decode(feed["signed_payload_b64"] + padding)
        assert json.loads(signed) == feed["payload"]
        assert signer.verify_bytes(feed["signature"]["value"], signed)
        assert feed["payload"]["events"][0]["handle"] == "observer-1"


async def test_broadcast_after_private_perfect_orbit(tmp_path):
    settings = Settings(data_dir=tmp_path, hub_url="https://hunt.example", observation_cache_s=60)
    app = create_app(
        settings,
        db=GameDatabase(":memory:"),
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions-broadcast"),
        signer=ProviderSigner(tmp_path / "provider-broadcast"),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        session = (await client.post("/api/v1/session", json={})).json()
        auth = {"Authorization": f"Bearer {session['token']}"}
        round_data = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        # No evidence + high confidence on the true diagnosis maximizes score.
        verdict = (
            await client.post(
                f"/api/v1/rounds/{round_data['id']}/submit",
                headers=auth,
                json={"answer_code": "source_concentration", "confidence": 1.0},
            )
        ).json()
        assert verdict["correct"] is True
        assert int(verdict["score"]) >= 950
        assert (await client.get("/api/v1/heroes/feed")).json()["payload"]["events"] == []
        await client.put(
            "/api/v1/profile",
            headers=auth,
            json={"handle": "orbit-relay", "public_profile": True},
        )
        broadcast = await client.post(
            f"/api/v1/rounds/{round_data['id']}/broadcast", headers=auth
        )
        assert broadcast.status_code == 200
        body = broadcast.json()
        assert body["ok"] is True
        feed = (await client.get("/api/v1/heroes/feed")).json()
        assert len(feed["payload"]["events"]) == 1
        assert feed["payload"]["events"][0]["handle"] == "orbit-relay"
    settings = Settings(data_dir=tmp_path, hub_url="https://hunt.example")
    app = create_app(
        settings,
        db=GameDatabase(":memory:"),
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions"),
        signer=ProviderSigner(tmp_path / "provider"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session = (await client.post("/api/v1/session", json={})).json()
        auth = {"Authorization": f"Bearer {session['token']}"}
        round_data = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        await client.post(
            f"/api/v1/rounds/{round_data['id']}/submit",
            headers=auth,
            json={"answer_code": "source_concentration", "confidence": 0.9},
        )
        feed = (await client.get("/api/v1/heroes/feed")).json()
        assert feed["payload"]["events"] == []


async def test_opt_in_after_private_submit_does_not_backfill(tmp_path):
    settings = Settings(data_dir=tmp_path, hub_url="https://hunt.example")
    app = create_app(
        settings,
        db=GameDatabase(":memory:"),
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions"),
        signer=ProviderSigner(tmp_path / "provider"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session = (await client.post("/api/v1/session", json={})).json()
        auth = {"Authorization": f"Bearer {session['token']}"}
        round_data = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        await client.post(
            f"/api/v1/rounds/{round_data['id']}/submit",
            headers=auth,
            json={"answer_code": "source_concentration", "confidence": 0.9},
        )
        assert (await client.get("/api/v1/heroes/feed")).json()["payload"]["events"] == []
        await client.put(
            "/api/v1/profile",
            headers=auth,
            json={"handle": "late-opt-in", "public_profile": True},
        )
        assert (await client.get("/api/v1/heroes/feed")).json()["payload"]["events"] == []


async def test_opt_out_removes_existing_events_from_feed(tmp_path):
    settings = Settings(data_dir=tmp_path, hub_url="https://hunt.example")
    app = create_app(
        settings,
        db=GameDatabase(":memory:"),
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions"),
        signer=ProviderSigner(tmp_path / "provider"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session = (
            await client.post(
                "/api/v1/session",
                json={"handle": "broadcast", "public_profile": True},
            )
        ).json()
        auth = {"Authorization": f"Bearer {session['token']}"}
        round_data = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        await client.post(
            f"/api/v1/rounds/{round_data['id']}/submit",
            headers=auth,
            json={"answer_code": "source_concentration", "confidence": 0.9},
        )
        feed = (await client.get("/api/v1/heroes/feed")).json()
        assert len(feed["payload"]["events"]) == 1
        await client.put(
            "/api/v1/profile",
            headers=auth,
            json={"handle": "broadcast", "public_profile": False},
        )
        assert (await client.get("/api/v1/heroes/feed")).json()["payload"]["events"] == []


async def test_provider_result_signature_is_request_bound(tmp_path):
    settings = Settings(data_dir=tmp_path, hub_url="https://hunt.example")
    signer = ProviderSigner(tmp_path / "provider")
    app = create_app(
        settings,
        db=GameDatabase(":memory:"),
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions"),
        signer=signer,
    )
    request = {
        "product_id": "signal-hunt",
        "capability_id": "signal.leaderboard@v1",
        "input": {"limit": 5},
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/provider/invoke", json=request)
    result = response.json()["result"]
    signature = response.headers["X-Provider-Signature"]
    assert signer.verify_response(
        signature, request["capability_id"], request["product_id"], request["input"], result
    )
    assert not signer.verify_response(
        signature, request["capability_id"], request["product_id"], {"limit": 6}, result
    )


async def test_unplayed_round_refreshes_when_history_grows(tmp_path):
    """Cold first observation must not freeze hist=0 for the whole bucket."""
    settings = Settings(
        data_dir=tmp_path, hub_url="https://hunt.example", observation_cache_s=0
    )
    db = GameDatabase(":memory:")
    app = create_app(
        settings,
        db=db,
        federation=FixedFederation(),
        tokens=SessionTokens(tmp_path / "sessions-hist"),
        signer=ProviderSigner(tmp_path / "provider-hist"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session = (await client.post("/api/v1/session", json={"handle": "hist"})).json()
        auth = {"Authorization": f"Bearer {session['token']}"}
        first = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        assert first["signal"]["history_depth"] == 0
        # Distinct observation ids so recent_snapshots sees prior snaps.
        for idx in range(3):
            snap = live_snapshot()
            snap["observation_id"] = f"obs-warm-{idx}"
            snap["observed_at"] = f"2026-08-10T10:0{idx}:00Z"
            db.save_snapshot(snap)
        second = (await client.get("/api/v1/rounds/live", headers=auth)).json()
        assert second["id"] == first["id"]
        assert second["signal"]["history_depth"] >= 3
        assert second["submitted"] is False
