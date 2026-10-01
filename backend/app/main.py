"""FastAPI application factory."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_audit, routes_system, routes_workflow
from app.config import Settings
from app.container import AppContainer
from app.errors import DomainError
from app.observability.logging import (
    configure_logging,
    get_correlation_id,
    log_event,
    new_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger("trustchain.http")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def create_app(container: AppContainer | None = None) -> FastAPI:
    container = container or AppContainer(Settings.from_env())
    configure_logging(container.settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        container.initialise()
        yield

    app = FastAPI(
        title="TrustChain AI",
        description="Human-governed, Web3-verifiable autonomous AI agents (proof of concept).",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(container.settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-User-Id", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )

    @app.middleware("http")
    async def correlate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # A caller-supplied id is accepted only if it is safe to write to a log.
        supplied = request.headers.get("X-Correlation-ID", "")
        set_correlation_id(supplied if _CORRELATION_ID.match(supplied) else new_correlation_id())
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = get_correlation_id()
        log_event(
            logger,
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": exc.code,
                "message": exc.message,
                "correlation_id": get_correlation_id(),
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Details go to the log, not to the caller.
        logger.error("unhandled_error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Unexpected error. Quote the correlation id when reporting it.",
                "correlation_id": get_correlation_id(),
            },
        )

    app.include_router(routes_system.router)
    app.include_router(routes_workflow.router)
    app.include_router(routes_audit.router)
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn app.main:app_factory --factory`."""
    return create_app()
