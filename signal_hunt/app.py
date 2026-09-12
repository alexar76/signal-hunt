from __future__ import annotations

import asyncio
import base64
import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings
from .database import GameDatabase
from .federation import FederationClient, FederationUnavailable
from .service import GameError, GameService
from .signing import ProviderSigner, SessionTokens


class SessionRequest(BaseModel):
    handle: str | None = Field(None, max_length=24)
    public_profile: bool = False


class ProfileRequest(BaseModel):
    handle: str = Field(..., min_length=2, max_length=24)
    public_profile: bool = False


class SubmissionRequest(BaseModel):
    answer_code: str = Field(..., min_length=2, max_length=64)
    confidence: float = Field(..., ge=0.25, le=1)
    follow_up_answer: str | None = Field(None, max_length=128)


class ProviderInvokeRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    product_id: str = Field("signal-hunt", max_length=80)
    capability_id: str = Field(..., max_length=80)


def create_app(
    settings: Settings | None = None,
    *,
    db: GameDatabase | None = None,
    federation: FederationClient | None = None,
    tokens: SessionTokens | None = None,
    signer: ProviderSigner | None = None,
) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    database = db or GameDatabase(settings.database_path)
    token_manager = tokens or SessionTokens(settings.session_secret_path)
    provider_signer = signer or ProviderSigner(settings.provider_key_path)
    federation_client = federation or FederationClient(
        settings.hub_url, settings.request_timeout_s
    )
    service = GameService(settings, database, federation_client, token_manager)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = None
        if settings.observe_interval_s > 0:
            task = asyncio.create_task(service.run_observer())
        yield
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="AICOM Signal Hunt",
        description="Federation-native investigation game over measured AIMarket telemetry",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.service = service
    app.state.provider_signer = provider_signer

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(GameError)
    async def game_error_handler(_, exc: GameError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.code, "detail": exc.detail},
        )

    @app.exception_handler(FederationUnavailable)
    async def federation_error_handler(_, exc: FederationUnavailable):
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "federation_unavailable",
                "detail": str(exc),
                "live": False,
            },
        )

    def session_from_header(authorization: str = Header(default="")) -> dict[str, str]:
        token = authorization.removeprefix("Bearer ").strip()
        return service.authenticate(token)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "aicom-signal-hunt",
            "version": __version__,
            "hub_url": settings.hub_url,
            "data_mode": "live-only",
            "observe_interval_s": settings.observe_interval_s,
            "snapshots": database.snapshot_count(),
        }

    @app.post("/api/v1/session")
    async def create_session(body: SessionRequest):
        return service.create_session(body.handle, body.public_profile)

    @app.get("/api/v1/profile")
    async def profile(session: dict[str, str] = Depends(session_from_header)):
        return service.profile(session["id"])

    @app.put("/api/v1/profile")
    async def update_profile(
        body: ProfileRequest,
        session: dict[str, str] = Depends(session_from_header),
    ):
        return service.update_profile(
            session["id"], body.handle, body.public_profile
        )

    @app.get("/api/v1/rounds/live")
    async def live_round(session: dict[str, str] = Depends(session_from_header)):
        return await service.live_round(session["id"])

    @app.get("/api/v1/rounds/{round_id}")
    async def get_round(
        round_id: str, session: dict[str, str] = Depends(session_from_header)
    ):
        return service.round_by_id(round_id, session["id"])

    @app.post("/api/v1/rounds/{round_id}/evidence/{evidence_id}")
    async def open_evidence(
        round_id: str,
        evidence_id: str,
        session: dict[str, str] = Depends(session_from_header),
    ):
        return service.evidence(round_id, evidence_id, session["id"])

    @app.post("/api/v1/rounds/{round_id}/submit")
    async def submit(
        round_id: str,
        body: SubmissionRequest,
        session: dict[str, str] = Depends(session_from_header),
    ):
        return service.submit(
            round_id,
            session["id"],
            body.answer_code,
            body.confidence,
            body.follow_up_answer,
        )

    @app.post("/api/v1/rounds/{round_id}/broadcast")
    async def broadcast(
        round_id: str,
        session: dict[str, str] = Depends(session_from_header),
    ):
        return service.broadcast(round_id, session["id"])

    @app.get("/api/v1/leaderboard")
    async def leaderboard(limit: int = Query(20, ge=1, le=100)):
        return service.leaderboard(limit)

    @app.get("/api/v1/leaderboard/weekly")
    async def weekly_leaderboard(limit: int = Query(20, ge=1, le=100)):
        return service.weekly_leaderboard(limit)

    @app.get("/api/v1/heroes/feed")
    async def heroes_feed(limit: int = Query(100, ge=1, le=200)):
        payload = service.heroes(limit)
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        return {
            "schema": "aicom.signal-hunt.signed-feed.v1",
            "payload": payload,
            "signed_payload_b64": base64.urlsafe_b64encode(encoded).decode().rstrip("="),
            "signature": {
                "algorithm": "ed25519",
                "public_key": provider_signer.public_key_b64,
                "value": provider_signer.sign_bytes(encoded),
            },
        }

    @app.get("/provider/public-key")
    async def provider_public_key():
        return {
            "algorithm": "ed25519",
            "public_key": provider_signer.public_key_b64,
            "canonical": "aimarket-request-bound-v1",
        }

    @app.post("/provider/invoke")
    async def provider_invoke(body: ProviderInvokeRequest):
        inp = body.input
        try:
            if body.capability_id == "signal.case@v1":
                token = str(inp.get("session_token") or "")
                session = service.authenticate(token)
                result = await service.live_round(session["id"])
            elif body.capability_id == "signal.evidence@v1":
                token = str(inp.get("session_token") or "")
                session = service.authenticate(token)
                result = service.evidence(
                    str(inp.get("round_id") or ""),
                    str(inp.get("evidence_id") or ""),
                    session["id"],
                )
            elif body.capability_id == "signal.submit@v1":
                token = str(inp.get("session_token") or "")
                session = service.authenticate(token)
                result = service.submit(
                    str(inp.get("round_id") or ""),
                    session["id"],
                    str(inp.get("answer_code") or ""),
                    float(inp.get("confidence", 0)),
                    follow_up_answer=(
                        str(inp["follow_up_answer"])
                        if inp.get("follow_up_answer") not in (None, "")
                        else None
                    ),
                )
            elif body.capability_id == "signal.leaderboard@v1":
                result = service.leaderboard(int(inp.get("limit", 20)))
            elif body.capability_id == "signal.heroes@v1":
                result = service.heroes(int(inp.get("limit", 20)))
            else:
                result = {
                    "success": False,
                    "error": "unknown_capability",
                    "detail": f"unknown Signal Hunt capability: {body.capability_id}",
                }
        except (GameError, FederationUnavailable, TypeError, ValueError) as exc:
            result = {
                "success": False,
                "error": getattr(exc, "code", type(exc).__name__),
                "detail": getattr(exc, "detail", str(exc)),
            }
        signature = provider_signer.sign_response(
            body.capability_id, body.product_id, inp, result
        )
        return JSONResponse(
            content={"success": result.get("success", True), "result": result},
            headers={"X-Provider-Signature": signature},
        )

    static_dir = Path(
        os.getenv(
            "SIGNAL_HUNT_STATIC_DIR",
            str(Path(__file__).resolve().parent.parent / "frontend" / "dist"),
        )
    )
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


app = create_app()
