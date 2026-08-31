"""Liveness and readiness endpoints.

For this work order, `/health/ready` reports model-artefact status only (loaded + sha256
verified) -- no database check yet; that arrives with the DB work order. backend_plan.md
section 1.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.domain.health import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


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

    model = model_state.model
    assert model is not None  # error is None => load succeeded
    return ReadinessResponse(
        status="ready",
        request_id=request.state.request_id,
        model_version=model.model_version,
        artefact_sha256=model.artefact_sha256,
        checks={"model_artefact": "loaded_and_verified"},
    )
