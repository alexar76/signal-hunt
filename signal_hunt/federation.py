from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import statistics
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from .thresholds import PEER_PROBE_LIMIT, PEER_PROBE_TIMEOUT_S


class FederationUnavailable(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _round_money(value: float | None) -> float | None:
    return round(value, 8) if value is not None else None


class FederationClient:
    def __init__(self, hub_url: str, timeout_s: float = 12):
        self.hub_url = hub_url.rstrip("/")
        self.timeout_s = timeout_s

    async def _get(
        self, path: str, *, client: httpx.AsyncClient | None = None
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        started = time.perf_counter()
        own_client = client is None
        try:
            if own_client:
                client = httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True)
            assert client is not None
            response = await client.get(f"{self.hub_url}{path}")
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("response is not a JSON object")
            return payload, {"status": "ok", "elapsed_ms": elapsed, "http_status": response.status_code}
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return None, {
                "status": "unavailable",
                "elapsed_ms": elapsed,
                "error": type(exc).__name__,
            }
        finally:
            if own_client and client is not None:
                await client.aclose()

    async def _probe_peer(self, client: httpx.AsyncClient, peer_url: str) -> dict[str, Any]:
        """Measure RTT to a peer's well-known. Latency is stored only on success."""
        target = f"{peer_url.rstrip('/')}/.well-known/ai-market.json"
        started = time.perf_counter()
        try:
            response = await client.get(target)
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            response.raise_for_status()
            return {
                "probe_status": "ok",
                "latency_ms": elapsed,
                "http_status": response.status_code,
            }
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return {
                "probe_status": "unavailable",
                "latency_ms": None,
                "probe_elapsed_ms": elapsed,
                "error": type(exc).__name__,
            }

    async def _enrich_peers_with_latency(
        self, peer_rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Probe up to PEER_PROBE_LIMIT peers; never invent a latency_ms."""
        candidates = [row for row in peer_rows if row.get("url")]
        limited = candidates[:PEER_PROBE_LIMIT]
        if not limited:
            return peer_rows

        timeout = httpx.Timeout(PEER_PROBE_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            probes = await asyncio.gather(
                *[self._probe_peer(client, str(row["url"])) for row in limited]
            )

        by_url = {
            str(row["url"]): probe
            for row, probe in zip(limited, probes, strict=True)
        }
        enriched: list[dict[str, Any]] = []
        for row in peer_rows:
            url = str(row.get("url") or "")
            probe = by_url.get(url)
            if probe is None:
                enriched.append({
                    **row,
                    "probe_status": "skipped",
                    "latency_ms": None,
                })
                continue
            enriched.append({**row, **probe})
        return enriched

    async def snapshot(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
            results = await asyncio.gather(
                self._get("/ai-market/v2/manifest", client=client),
                self._get("/.well-known/ai-market.json", client=client),
                self._get("/ai-market/v2/federation/peers", client=client),
                self._get("/ai-market/v2/stats/live", client=client),
            )
        (manifest, manifest_meta), (well_known, wk_meta), (peers_doc, peers_meta), (
            stats_doc, stats_meta,
        ) = results
        if manifest is None:
            # Full detail (incl. the possibly-internal hub URL) goes to the log;
            # the player-facing error stays generic so deployment topology never leaks.
            logger.warning(
                "mandatory manifest unavailable from %s: %s",
                self.hub_url,
                manifest_meta.get("error", "unknown error"),
            )
            raise FederationUnavailable("mandatory Hub manifest is unavailable")

        tools = [row for row in (manifest.get("tools") or []) if isinstance(row, dict)]
        normalized_tools: list[dict[str, Any]] = []
        for tool in tools:
            source = str(tool.get("source_hub") or "local")
            base_price = _finite_number(tool.get("price_per_call_usd"))
            routed_price = _finite_number(tool.get("routed_price_usd"))
            effective = routed_price if routed_price is not None else base_price
            normalized_tools.append(
                {
                    "source_hub": source,
                    "source_hub_name": str(tool.get("source_hub_name") or source),
                    "product_id": str(tool.get("product_id") or ""),
                    "capability_id": str(tool.get("capability_id") or tool.get("name") or ""),
                    "price_usd": effective,
                }
            )

        external = [row for row in normalized_tools if row["source_hub"] != "local"]
        source_rows: dict[str, list[dict[str, Any]]] = {}
        for tool in external:
            source_rows.setdefault(tool["source_hub"], []).append(tool)

        sources = []
        external_total = len(external)
        for source_id, rows in source_rows.items():
            prices = [row["price_usd"] for row in rows if row["price_usd"] is not None]
            sources.append(
                {
                    "id": source_id,
                    "name": next((r["source_hub_name"] for r in rows if r["source_hub_name"]), source_id),
                    "capabilities": len(rows),
                    "share": round(len(rows) / external_total, 6) if external_total else None,
                    "price_min_usd": _round_money(min(prices) if prices else None),
                    "price_median_usd": _round_money(statistics.median(prices) if prices else None),
                    "price_max_usd": _round_money(max(prices) if prices else None),
                }
            )
        sources.sort(key=lambda row: (-row["capabilities"], row["id"]))

        all_prices = [row["price_usd"] for row in external if row["price_usd"] is not None]
        peer_rows: list[dict[str, Any]] = []
        if peers_doc is not None:
            for peer in peers_doc.get("peers") or []:
                if not isinstance(peer, dict):
                    continue
                url = str(peer.get("url") or "").rstrip("/")
                if not url:
                    continue
                peer_rows.append(
                    {
                        "url": url,
                        "name": str(peer.get("name") or url),
                        "capabilities_count": peer.get("capabilities_count"),
                        "last_crawl": peer.get("last_crawl") or None,
                        "trust_score": _finite_number(peer.get("trust_score")),
                        "depth": peer.get("depth"),
                    }
                )

        # Measured peer RTT — only when the roster endpoint answered.
        if peers_meta.get("status") == "ok" and peer_rows:
            peer_rows = await self._enrich_peers_with_latency(peer_rows)
        else:
            peer_rows = [
                {**row, "probe_status": "skipped", "latency_ms": None}
                for row in peer_rows
            ]

        measured_latencies = [
            float(row["latency_ms"])
            for row in peer_rows
            if isinstance(row.get("latency_ms"), (int, float))
        ]
        latency_surface = {
            "measured_count": len(measured_latencies),
            "probed_count": sum(
                1 for row in peer_rows if row.get("probe_status") in {"ok", "unavailable"}
            ),
            "unavailable_count": sum(
                1 for row in peer_rows if row.get("probe_status") == "unavailable"
            ),
            "max_ms": round(max(measured_latencies), 2) if measured_latencies else None,
            "median_ms": (
                round(statistics.median(measured_latencies), 2) if measured_latencies else None
            ),
        }

        summary = stats_doc.get("summary") if isinstance(stats_doc, dict) else None
        if not isinstance(summary, dict):
            summary = {}
        settlement = {
            "invocations_24h": summary.get("invocations_24h"),
            "open_channels": summary.get("open_channels"),
            "settled_volume_usd": summary.get(
                "settled_only_volume_usd", summary.get("settled_volume_usd")
            ),
            "volume_24h_usd": summary.get("settled_volume_24h_usd"),
        }

        state_core = {
            "hub_url": self.hub_url,
            "signer_public_key": (well_known or {}).get("signer_public_key"),
            "capability_identities": sorted(
                [
                    [row["source_hub"], row["product_id"], row["capability_id"]]
                    for row in normalized_tools
                ]
            ),
            "prices": sorted(
                [
                    [row["source_hub"], row["product_id"], row["capability_id"], row["price_usd"]]
                    for row in normalized_tools
                ]
            ),
            "peers": sorted([[row["url"], row["capabilities_count"]] for row in peer_rows]),
            # Measured RTT is part of the committed field weather — nulls stay null.
            "peer_latency": sorted(
                [
                    [row["url"], row.get("latency_ms")]
                    for row in peer_rows
                    if row.get("probe_status") == "ok"
                ]
            ),
        }
        state_hash = hashlib.sha256(
            json.dumps(state_core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        observed_at = _now()
        observation_id = hashlib.sha256(f"{state_hash}:{observed_at}".encode()).hexdigest()[:24]
        return {
            "observation_id": observation_id,
            "state_hash": state_hash,
            "observed_at": observed_at,
            "hub_url": self.hub_url,
            "hub_name": (well_known or {}).get("name") or self.hub_url,
            "hub_generated_at": manifest.get("generated_at"),
            "signer_public_key": (well_known or {}).get("signer_public_key"),
            "capabilities": {
                "total": len(normalized_tools),
                "local": len(normalized_tools) - external_total,
                "external": external_total,
            },
            "sources": sources,
            "prices": {
                "count": len(all_prices),
                "min_usd": _round_money(min(all_prices) if all_prices else None),
                "median_usd": _round_money(statistics.median(all_prices) if all_prices else None),
                "p90_usd": _round_money(_percentile(all_prices, 0.90)),
                "max_usd": _round_money(max(all_prices) if all_prices else None),
            },
            "peers": peer_rows,
            "latency": latency_surface,
            "settlement": settlement,
            "sources_status": {
                "manifest": manifest_meta,
                "well_known": wk_meta,
                "peers": peers_meta,
                "stats": stats_meta,
            },
        }

    async def fairness_seed(self, alpha: str) -> dict[str, Any]:
        """Invoke a remotely discovered ECVRF capability through this Hub.

        The external result orders answer options; it never decides the diagnosis. A
        missing route/payment/backend is returned as an explicit unavailable state and
        is never replaced with invented oracle output.
        """
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
                search = await client.get(
                    f"{self.hub_url}/ai-market/v2/search",
                    params={"intent": "verifiable randomness ECVRF", "limit": 100},
                )
                search.raise_for_status()
                matches = search.json().get("matches") or []
                route = next(
                    (
                        row for row in matches
                        if isinstance(row, dict) and row.get("capability_id") == "sortes.draw@v1"
                    ),
                    None,
                )
                if route is None:
                    return {
                        "status": "unavailable",
                        "reason": "capability_not_discovered",
                        "capability_id": "sortes.draw@v1",
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                response = await client.post(
                    f"{self.hub_url}/ai-market/v2/invoke",
                    json={
                        "product_id": route.get("product_id"),
                        "capability_id": route.get("capability_id"),
                        "source_hub": route.get("source_hub"),
                        "input": {"alpha": alpha, "num_bytes": 16},
                    },
                )
                if response.status_code != 200:
                    reason = "payment_required" if response.status_code == 402 else f"http_{response.status_code}"
                    return {
                        "status": "unavailable",
                        "reason": reason,
                        "capability_id": route.get("capability_id"),
                        "source_hub": route.get("source_hub"),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("success") is False:
                    raise ValueError("federated invoke did not return a successful object")
                result = payload.get("result", payload.get("output", payload))
                result_hash = hashlib.sha256(
                    json.dumps(
                        result, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, default=str,
                    ).encode()
                ).hexdigest()
                return {
                    "status": "ok",
                    "capability_id": route.get("capability_id"),
                    "product_id": route.get("product_id"),
                    "source_hub": route.get("source_hub"),
                    "routed_price_usd": route.get("routed_price_usd"),
                    "result_hash": result_hash,
                    "receipt_nonce": (payload.get("receipt") or {}).get("nonce")
                    if isinstance(payload.get("receipt"), dict) else None,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                }
        except Exception as exc:
            return {
                "status": "unavailable",
                "reason": type(exc).__name__,
                "capability_id": "sortes.draw@v1",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
