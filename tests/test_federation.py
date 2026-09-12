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
    # Peers are IP LITERALS on purpose. The probe guard resolves a hostname and fails closed
    # when it cannot (see `probe_target`), so a reserved-for-documentation name like
    # `fast.example` would be refused before any transport mock was consulted — the test
    # would then assert transport behaviour the code never reaches. A literal needs no DNS,
    # so this stays hermetic AND runs through the real guard.
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
            {"url": "https://93.184.216.34", "name": "fast", "capabilities_count": 3},
            {"url": "https://8.8.8.8", "name": "down", "capabilities_count": 1},
        ]}),
        "https://hunt.example/ai-market/v2/stats/live": (200, {"summary": {}}),
        "https://93.184.216.34/.well-known/ai-market.json": (200, {"name": "fast"}),
        "https://8.8.8.8/.well-known/ai-market.json": (500, {"detail": "boom"}),
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
    assert by_url["https://93.184.216.34"]["probe_status"] == "ok"
    assert isinstance(by_url["https://93.184.216.34"]["latency_ms"], float)
    assert by_url["https://8.8.8.8"]["probe_status"] == "unavailable"
    assert by_url["https://8.8.8.8"]["latency_ms"] is None
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


class RecordingTransport(httpx.AsyncBaseTransport):
    """Absolute-URL router that remembers every URL it was actually asked for.

    The assertion that matters for the peer probe is not what came back, it is whether the
    request was made at all: a guard that refuses an address must leave no request behind.
    """

    def __init__(self, payloads: dict[str, tuple[int, dict]],
                 redirects: dict[str, str] | None = None):
        self.payloads = payloads
        self.redirects = redirects or {}
        self.seen: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        self.seen.append(key)
        if key in self.redirects:
            return httpx.Response(302, headers={"location": self.redirects[key]}, request=request)
        status, payload = self.payloads.get(key, (404, {"detail": key}))
        return httpx.Response(status, json=payload, request=request)


def _hub_payloads(peers: list[dict]) -> dict[str, tuple[int, dict]]:
    return {
        "https://hunt.example/ai-market/v2/manifest": (200, {
            "generated_at": "2026-08-10T00:00:00Z",
            "tools": [
                {"source_hub": "https://a", "source_hub_name": "A", "product_id": "p",
                 "capability_id": "x@v1", "price_per_call_usd": 0.01},
                {"source_hub": "local", "product_id": "signal-hunt",
                 "capability_id": "signal.case@v1", "price_per_call_usd": 0},
            ],
        }),
        "https://hunt.example/.well-known/ai-market.json": (200, {"name": "Hub", "signer_public_key": "k"}),
        "https://hunt.example/ai-market/v2/federation/peers": (200, {"peers": peers}),
        "https://hunt.example/ai-market/v2/stats/live": (200, {"summary": {}}),
    }


def _install(monkeypatch, transport: httpx.AsyncBaseTransport) -> None:
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


async def test_peer_probe_refuses_peer_urls_that_are_not_public(monkeypatch):
    """A federated peer roster must not be able to aim this observer at an internal host.

    The peer document's `url` is chosen by the peer, and the hub admits peers it crawled.
    Probing it unchecked turns the observer into an internal reachability scanner whose
    oracle is the probe_status/http_status/latency it reports back.
    """
    peers = [
        {"url": "http://169.254.169.254", "name": "metadata"},
        {"url": "http://127.0.0.1:9000", "name": "loopback"},
        {"url": "http://10.0.0.5", "name": "rfc1918"},
        {"url": "file:///etc/passwd", "name": "not-http"},
        {"url": "https://93.184.216.34", "name": "public"},
    ]
    transport = RecordingTransport({
        **_hub_payloads(peers),
        "https://93.184.216.34/.well-known/ai-market.json": (200, {"name": "public"}),
    })
    _install(monkeypatch, transport)

    result = await FederationClient("https://hunt.example").snapshot()
    by_url = {row["url"]: row for row in result["peers"]}

    for blocked in ("http://169.254.169.254", "http://127.0.0.1:9000",
                    "http://10.0.0.5", "file:///etc/passwd"):
        assert by_url[blocked]["probe_status"] == "refused", blocked
        assert by_url[blocked]["latency_ms"] is None, blocked

    # The whole property: no request was ever issued to any of them.
    for host in ("169.254.169.254", "127.0.0.1", "10.0.0.5", "/etc/passwd"):
        assert not any(host in seen for seen in transport.seen), host

    # A public peer is still probed normally.
    assert by_url["https://93.184.216.34"]["probe_status"] == "ok"
    assert result["latency"]["measured_count"] == 1


async def test_peer_probe_does_not_follow_redirects_to_internal_hosts(monkeypatch):
    """A public peer that 302-pivots inward must not be followed.

    This is the same argument aimarket-agent's receipt verifier already makes about
    well-known documents: they have no reason to redirect, and following one lets a
    public origin reach anywhere the prober can.
    """
    peers = [{"url": "https://93.184.216.34", "name": "pivot"}]
    transport = RecordingTransport(
        {
            **_hub_payloads(peers),
            "http://169.254.169.254/latest/meta-data/": (200, {"leaked": True}),
        },
        redirects={
            "https://93.184.216.34/.well-known/ai-market.json":
                "http://169.254.169.254/latest/meta-data/",
        },
    )
    _install(monkeypatch, transport)

    result = await FederationClient("https://hunt.example").snapshot()
    by_url = {row["url"]: row for row in result["peers"]}

    assert not any("169.254.169.254" in seen for seen in transport.seen)
    assert by_url["https://93.184.216.34"]["probe_status"] == "unavailable"
    assert by_url["https://93.184.216.34"]["latency_ms"] is None
