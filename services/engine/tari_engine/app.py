"""FastAPI application: local-only inference and orchestration service."""

from __future__ import annotations

import hmac
import logging
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from tari_perception.onnx_backend import available_providers
from tari_schema import SCHEMA_VERSION

from . import __version__
from .config import EngineConfig
from .session import StreamSession
from .store import SessionStore
from .telemetry import ResourceSampler

log = logging.getLogger("tari.engine")


@dataclass
class EngineContext:
    config: EngineConfig
    version: str = __version__
    store: SessionStore | None = None
    sampler: ResourceSampler = field(default_factory=ResourceSampler)
    onnx_providers: list[str] = field(default_factory=available_providers)
    started: float = field(default_factory=time.time)
    recovery_reported: bool = False
    ready_line: str | None = None


def create_app(config: EngineConfig, announce_port: int | None = None) -> FastAPI:
    ctx = EngineContext(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if config.persistence:
            try:
                ctx.store = SessionStore(config.db_path)
            except Exception as exc:  # noqa: BLE001 - engine keeps running without persistence
                log.error("persistence unavailable", extra={"error": repr(exc)})
                ctx.store = None
        if announce_port is not None:
            # The desktop supervisor waits for this exact line on stdout.
            print(f'TARI_ENGINE_READY {{"port": {announce_port}, "version": "{ctx.version}"}}', flush=True)
            sys.stdout.flush()
        log.info("engine ready", extra={"version": ctx.version, "providers": ctx.onnx_providers})
        yield
        if ctx.store is not None:
            ctx.store.close()

    app = FastAPI(title="TARI engine", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.ctx = ctx
    app.add_middleware(CORSMiddleware, allow_origins=list(config.allowed_origins), allow_methods=["GET"],
                       allow_headers=["x-tari-token"])

    def check_token(x_tari_token: str | None = Header(default=None)) -> None:
        if x_tari_token is None or not hmac.compare_digest(x_tari_token, config.token):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": ctx.version, "schema_version": SCHEMA_VERSION,
                "uptime_s": round(time.time() - ctx.started, 1)}

    @app.get("/v1/info", dependencies=[Depends(check_token)])
    def info() -> dict[str, Any]:
        return {
            "version": ctx.version, "schema_version": SCHEMA_VERSION,
            "onnx_providers_available": ctx.onnx_providers,
            "persistence": "sqlite" if ctx.store else "unavailable",
            "persistence_degraded": ctx.store.degraded if ctx.store else None,
            "database_recovery": ctx.store.recovery if ctx.store else None,
        }

    @app.get("/v1/sessions", dependencies=[Depends(check_token)])
    def sessions(limit: int = 50) -> list[dict[str, Any]]:
        if ctx.store is None:
            raise HTTPException(503, "persistence unavailable")
        return ctx.store.list_sessions(min(max(limit, 1), 500))

    @app.get("/v1/sessions/{session_id}", dependencies=[Depends(check_token)])
    def session_detail(session_id: str) -> dict[str, Any]:
        if ctx.store is None:
            raise HTTPException(503, "persistence unavailable")
        detail = ctx.store.session_detail(session_id)
        if detail is None:
            raise HTTPException(404, "session not found")
        return detail

    @app.get("/v1/profile", dependencies=[Depends(check_token)])
    def profile(player_id: str = "local", include_simulated: bool = False) -> dict[str, Any]:
        if ctx.store is None:
            raise HTTPException(503, "persistence unavailable")
        return ctx.store.profile(player_id, include_simulated).model_dump()

    @app.websocket("/v1/stream")
    async def stream(ws: WebSocket) -> None:
        token = ws.query_params.get("token", "")
        if not hmac.compare_digest(token, config.token):
            await ws.close(code=4401)
            return
        await ws.accept()
        await StreamSession(ws, ctx).run()

    return app
