"""Recommendation endpoints (work order B7) -- `docs/10` section 6.

Thin controllers over :mod:`app.application.recommendation_service`. There is **no POST that
creates a recommendation** and there must not be one until the trigger -> action mapping is ruled
on (`dev_docs/QUESTIONS_FOR_ML_TEAM_4.md`). Until then every list is empty, which is correct.

Status codes:

* 403 -- the learner is not visible to this teacher, OR the recommendation id does not exist.
  One answer for both, so an id cannot be probed for existence.
* 409 -- the recommendation is already decided or has expired. The body names which.
* 503 -- no single active pipeline run (the same rule as every dashboard read).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import CurrentPrincipal, DbSession
from app.api.routes.dashboard import _FORBIDDEN, _active_model_version, _no_active_run
from app.application import recommendation_service
from app.application.data_access import ActivePipelineRunError
from app.domain.recommendations import (
    ModifyRequest,
    RecommendationListResponse,
    RecommendationOut,
)

router = APIRouter(prefix="/api/v1/t3", tags=["recommendations"])


def _conflict(exc: recommendation_service.RecommendationConflictError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"stage": "recommendation", "error": exc.reason},
    )


@router.get(
    "/students/{student_id}/recommendations", response_model=RecommendationListResponse
)
async def list_recommendations(
    student_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: DbSession,
    status_filter: Literal["active", "all"] = Query("active", alias="status"),
) -> RecommendationListResponse:
    try:
        return await recommendation_service.list_for_student(
            session,
            principal.teacher_profile_id,
            student_id,
            model_version=_active_model_version(),
            status_filter=status_filter,
        )
    except recommendation_service.LearnerNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


async def _decide(
    session: DbSession,
    principal: CurrentPrincipal,
    recommendation_id: uuid.UUID,
    decision: recommendation_service.Decision,
    body: ModifyRequest | None = None,
) -> RecommendationOut:
    try:
        return await recommendation_service.decide(
            session,
            principal.teacher_profile_id,
            recommendation_id,
            decision,
            modified_action=None if body is None else body.teacher_modified_action,
        )
    except recommendation_service.LearnerNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except recommendation_service.RecommendationConflictError as exc:
        raise _conflict(exc) from exc


@router.post("/recommendations/{recommendation_id}/accept", response_model=RecommendationOut)
async def accept(
    recommendation_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> RecommendationOut:
    return await _decide(session, principal, recommendation_id, "accepted")


@router.post("/recommendations/{recommendation_id}/dismiss", response_model=RecommendationOut)
async def dismiss(
    recommendation_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> RecommendationOut:
    return await _decide(session, principal, recommendation_id, "dismissed")


@router.post("/recommendations/{recommendation_id}/modify", response_model=RecommendationOut)
async def modify(
    recommendation_id: uuid.UUID,
    body: ModifyRequest,
    principal: CurrentPrincipal,
    session: DbSession,
) -> RecommendationOut:
    return await _decide(session, principal, recommendation_id, "modified", body)
