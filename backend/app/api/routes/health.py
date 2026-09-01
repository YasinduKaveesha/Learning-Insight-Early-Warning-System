"""Liveness and readiness endpoints.

`/health/ready` reports both readiness checks (backend_plan.md section 1, build-order
step 1 -- "`/health/ready` answers against the shared database"):

* `model_artefact` -- loaded at startup and sha256-verified.
* `database` -- a real `SELECT 1` on the shared async engine, executed per request.

Neither check may fail open. A probe that catches its own exception and still answers
`ready` turns a hard outage into a silent one and is worse than having no probe at all, so
a database failure is a 503 with `{"stage": "database", ...}` -- the same detail shape the
model-artefact branch already uses, so a caller can switch on one key.

The failure detail is passed through `engine.scrub_secret` first. The connection string
carries a live credential and a driver exception is perfectly capable of quoting it; nothing
derived from an exception reaches a response body or a log line unscrubbed (trap 4).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.domain.health import LivenessResponse, ReadinessResponse
from app.infrastructure.db import engine as db_engine

router = APIRouter(prefix="/health", tags=["health"])

logger = logging.getLogger(__name__)


@router.get("/live", response_model=LivenessResponse)
async def liveness(request: Request) -> LivenessResponse:
    return LivenessResponse(status="alive", request_id=request.state.request_id)


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    model_state = request.app.state.model_state

    if model_state.error is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"stage": "model_artefact", "error": str(model_state.error)},
        )

    try:
        await db_engine.check_database_reachable()
    except Exception as exc:
        # Deliberately broad: anything at all that stops `SELECT 1` -- a refused
        # connection, a DNS failure, an auth rejection, a bad URL that only blows up when
        # the engine is finally built -- means this process is not ready to serve. Narrow
        # it and the un-caught case becomes a 500 that reads like an application bug.
        # The one thing we must NOT do is continue to the `ready` return below.
        detail = db_engine.scrub_secret(f"{type(exc).__name__}: {exc}")
        logger.error("readiness database probe failed", extra={"error": detail})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"stage": "database", "error": detail},
        ) from exc

    model = model_state.model
    assert model is not None  # error is None => load succeeded
    return ReadinessResponse(
        status="ready",
        request_id=request.state.request_id,
        model_version=model.model_version,
        artefact_sha256=model.artefact_sha256,
        checks={"model_artefact": "loaded_and_verified", "database": "select_1_ok"},
    )
