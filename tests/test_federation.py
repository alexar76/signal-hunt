from __future__ import annotations

import httpx

from signal_hunt.federation import FederationClient, FederationUnavailable


class RoutedTransport(httpx.AsyncBaseTransport):
    def __init__(self, payloads: dict[str, tuple[int, dict]]):
        self.payloads = payloads

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        status, payload = self.payloads.get(request.url.path, (404, {"detail": "missing"}))
        return httpx.Response(status, json=payload, request=request)


async def test_snapshot_uses_routed_price_and_preserves_missing_stats(monkeypatch):
    payloads = {
        "/ai-market/v2/manifest": (200, {
            "generated_at": "2026-08-10T00:00:00Z",
            "tools": [
                {"source_hub": "https://a", "source_hub_name": "A", "product_id": "p", "capability_id": "x@v1", "price_per_call_usd": 0.01, "routed_price_usd": 0.012},
                {"source_hub": "https://b", "source_hub_name": "B", "product_id": "p", "capability_id": "y@v1", "price_per_call_usd": 0.02, "routed_price_usd": None},
                {"source_hub": "local", "product_id": "signal-hunt", "capability_id": "signal.case@v1", "price_per_call_usd": 0},
            ],
        }),
        "/.well-known/ai-market.json": (200, {"name": "Signal Hunt Hub", "signer_public_key": "key"}),
        "/ai-market/v2/federation/peers": (200, {"peers": []}),
        "/ai-market/v2/stats/live": (200, {"summary": {"settled_only_volume_usd": 0.04}}),
    }
    transport = RoutedTransport(payloads)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=transport, base_url="https://hunt.example")

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await FederationClient("https://hunt.example").snapshot()
    assert result["capabilities"] == {"total": 3, "local": 1, "external": 2}
    assert result["prices"]["median_usd"] == 0.016
    assert result["settlement"]["settled_volume_usd"] == 0.04
    assert result["settlement"]["volume_24h_usd"] is None
    assert result["settlement"]["invocations_24h"] is None


async def test_manifest_failure_never_falls_back_to_fixture(monkeypatch):
    transport = RoutedTransport({})
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=transport, base_url="https://hunt.example")

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    try:
        await FederationClient("https://hunt.example").snapshot()
    except FederationUnavailable as exc:
        assert "mandatory Hub manifest is unavailable" in str(exc)
        assert "hunt.example" not in str(exc)  # topology must not leak to players
    else:
        raise AssertionError("a missing real manifest must fail closed")


async def test_snapshot_probes_peer_rtt_and_keeps_failures_null(monkeypatch):
    payloads = {
        "https://hunt.example/ai-market/v2/manifest": (200, {
            "generated_at": "2026-08-10T00:00:00Z",
            "tools": [
                {"source_hub": "https://a", "source_hub_name": "A", "product_id": "p", "capability_id": "x@v1", "price_per_call_usd": 0.01},
                {"source_hub": "https://b", "source_hub_name": "B", "product_id": "p", "capability_id": "y@v1", "price_per_call_usd": 0.02},
                {"source_hub": "local", "product_id": "signal-hunt", "capability_id": "signal.case@v1", "price_per_call_usd": 0},
            ],
        }),
        "https://hunt.example/.well-known/ai-market.json": (200, {"name": "Signal Hunt Hub", "signer_public_key": "key"}),
        "https://hunt.example/ai-market/v2/federation/peers": (200, {"peers": [
            {"url": "https://fast.example", "name": "fast", "capabilities_count": 3},
            {"url": "https://down.example", "name": "down", "capabilities_count": 1},
        ]}),
        "https://hunt.example/ai-market/v2/stats/live": (200, {"summary": {}}),
        "https://fast.example/.well-known/ai-market.json": (200, {"name": "fast"}),
        "https://down.example/.well-known/ai-market.json": (500, {"detail": "boom"}),
    }

    class AbsoluteTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            key = str(request.url)
            status, payload = payloads.get(key, (404, {"detail": key}))
            return httpx.Response(status, json=payload, request=request)

    transport = AbsoluteTransport()
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await FederationClient("https://hunt.example").snapshot()
    by_url = {row["url"]: row for row in result["peers"]}
    assert by_url["https://fast.example"]["probe_status"] == "ok"
    assert isinstance(by_url["https://fast.example"]["latency_ms"], float)
    assert by_url["https://down.example"]["probe_status"] == "unavailable"
    assert by_url["https://down.example"]["latency_ms"] is None
    assert result["latency"]["measured_count"] == 1
    assert result["latency"]["unavailable_count"] == 1


async def test_snapshot_skips_peer_probe_when_roster_empty(monkeypatch):
    payloads = {
        "/ai-market/v2/manifest": (200, {
            "generated_at": "2026-08-10T00:00:00Z",
            "tools": [
                {"source_hub": "https://a", "source_hub_name": "A", "product_id": "p", "capability_id": "x@v1", "price_per_call_usd": 0.01},
                {"source_hub": "local", "product_id": "signal-hunt", "capability_id": "signal.case@v1", "price_per_call_usd": 0},
            ],
        }),
        "/.well-known/ai-market.json": (200, {"name": "Signal Hunt Hub", "signer_public_key": "key"}),
        "/ai-market/v2/federation/peers": (200, {"peers": []}),
        "/ai-market/v2/stats/live": (200, {"summary": {}}),
    }
    transport = RoutedTransport(payloads)
    probed = {"count": 0}

    class CountingClient(httpx.AsyncClient):
        async def get(self, url, *args, **kwargs):
            text = str(url)
            if text.endswith("/.well-known/ai-market.json") and "hunt.example" not in text:
                probed["count"] += 1
            return await super().get(url, *args, **kwargs)

    def client_factory(*args, **kwargs):
        return CountingClient(transport=transport, base_url="https://hunt.example")

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await FederationClient("https://hunt.example").snapshot()
    assert result["peers"] == []
    assert result["latency"]["measured_count"] == 0
    assert probed["count"] == 0


async def test_fairness_seed_discovers_and_invokes_remote_vrf(monkeypatch):
    payloads = {
        "/ai-market/v2/search": (200, {"matches": [{
            "product_id": "prod-sortes",
            "capability_id": "sortes.draw@v1",
            "source_hub": "https://oracles.example/family",
            "routed_price_usd": 0.00606,
        }]}),
        "/ai-market/v2/invoke": (200, {
            "success": True,
            "result": {"output": "abc123", "pi": "proof"},
            "receipt": {"nonce": "rcpt-real-test"},
        }),
    }
    transport = RoutedTransport(payloads)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=transport, base_url="https://hunt.example")

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await FederationClient("https://hunt.example").fairness_seed("round-alpha")
    assert result["status"] == "ok"
    assert result["capability_id"] == "sortes.draw@v1"
    assert result["source_hub"] == "https://oracles.example/family"
    assert result["receipt_nonce"] == "rcpt-real-test"
    assert len(result["result_hash"]) == 64
