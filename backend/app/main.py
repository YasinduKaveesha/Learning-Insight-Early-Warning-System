"""FastAPI application entry point for the Component 3 backend."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.infrastructure import model_loading
from app.infrastructure.db import engine as db_engine
from app.infrastructure.logging import configure_logging, request_id_ctx
from app.infrastructure.settings import get_settings

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
logger = logging.getLogger("t3.http")


def _accepted_request_id(value: str | None) -> str:
    return value if value and REQUEST_ID_PATTERN.fullmatch(value) else str(uuid4())


def create_app() -> FastAPI:
    settings = get_settings()  # fail fast: raises if a required variable is missing
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        artefact_path = model_loading.resolve_artefact_path(
            settings.t3_model_artefact_path, settings.t3_active_model_version
        )
        try:
            model = model_loading.load_model(
                artefact_path, model_version=settings.t3_active_model_version
            )
            app.state.model_state = model_loading.ModelState(model=model)
            logger.info(
                "model artefact loaded",
                extra={"model_version": model.model_version, "sha256": model.artefact_sha256},
            )
        except model_loading.ModelLoadError as exc:
            app.state.model_state = model_loading.ModelState(error=exc)
            logger.error("model artefact failed to load", extra={"error": str(exc)})

        # The engine is NOT opened here. It is created lazily on first use so a database
        # that is briefly down cannot stop the process from starting and answering
        # `/health/ready` with an honest 503 -- which is the whole point of the probe.
        try:
            yield
        finally:
            # Always dispose, even if startup partly failed: an undisposed asyncpg pool
            # holds server connections open, and on a shared database those are somebody
            # else's too. `dispose()` also clears the module-level engine, so a fresh app
            # in the same process (every TestClient) never inherits the previous URL.
            await db_engine.dispose()

    application = FastAPI(
        title="Component 3 - Learning Insight & Early Warning System API",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_observability(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _accepted_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response

    application.include_router(health_router)

    return application


app = create_app()
