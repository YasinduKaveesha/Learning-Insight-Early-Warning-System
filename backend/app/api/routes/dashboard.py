"""Teacher-dashboard read endpoints (work order B6.1) -- backend_plan.md section 8.

Thin controllers: parse, delegate, serialise. No business logic and no query composition --
both live in :mod:`app.application.dashboard_service`, which is also where the ethical
invariants are enforced so they cannot be re-implemented differently in a second endpoint.

Base path `/api/v1/t3`. Every route here requires a resolved `Principal`; there is no
unauthenticated read. Ownership is not checked in this module -- the service delegates it to
`data_access`'s fail-closed guards, and a caller who does not own the resource gets 403 with
no hint as to whether it exists.

NOT IN THIS WORK ORDER (named owners so nobody builds them here by accident):
`/classes/{id}/key` (GET and POST) and every `/recommendations` route -- B7.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentPrincipal, DbSession
from app.application import dashboard_service
from app.application.data_access import ActivePipelineRunError
from app.domain.dashboard import (
    CohortResponse,
    HomeSummary,
    StudentDetail,
    WatchListResponse,
)
from app.domain.sessions import (
    ClassReportResponse,
    SessionHistoryResponse,
    SkillProgressResponse,
)
from app.infrastructure.settings import get_settings

router = APIRouter(prefix="/api/v1/t3", tags=["dashboard"])


def _active_model_version() -> str:
    return get_settings().t3_active_model_version


def _no_active_run(exc: ActivePipelineRunError) -> HTTPException:
    """A missing or ambiguous pipeline run is a server-state problem, not the caller's
    fault, and it must not read as "this teacher has no students" -- an empty dashboard that
    means "nothing to worry about" is the single most dangerous failure mode this product
    has. 503, explicitly."""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"stage": "pipeline_run", "error": str(exc)},
    )


_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail={"stage": "authorization", "error": "not visible to this teacher"},
)


@router.get("/home", response_model=HomeSummary)
async def home(principal: CurrentPrincipal, session: DbSession) -> HomeSummary:
    try:
        return await dashboard_service.home_summary(
            session, principal.teacher_profile_id, model_version=_active_model_version()
        )
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


@router.get("/watch", response_model=WatchListResponse)
async def watch_all_classes(
    principal: CurrentPrincipal, session: DbSession
) -> WatchListResponse:
    try:
        return await dashboard_service.all_classes_watch_list(
            session, principal.teacher_profile_id, model_version=_active_model_version()
        )
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


@router.get("/classes/{classroom_id}/cohort", response_model=CohortResponse)
async def cohort(
    classroom_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> CohortResponse:
    try:
        return await dashboard_service.cohort(
            session,
            principal.teacher_profile_id,
            classroom_id,
            model_version=_active_model_version(),
        )
    except dashboard_service.ClassroomNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


@router.get("/classes/{classroom_id}/watch", response_model=WatchListResponse)
async def classroom_watch(
    classroom_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> WatchListResponse:
    try:
        return await dashboard_service.classroom_watch_list(
            session,
            principal.teacher_profile_id,
            classroom_id,
            model_version=_active_model_version(),
        )
    except dashboard_service.ClassroomNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


@router.get("/students/{student_id}", response_model=StudentDetail)
async def student(
    student_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> StudentDetail:
    try:
        return await dashboard_service.student_detail(
            session,
            principal.teacher_profile_id,
            student_id,
            model_version=_active_model_version(),
        )
    except dashboard_service.LearnerNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except dashboard_service.NoPredictionsError as exc:
        # The learner is legitimately visible and simply has no snapshot in the active run.
        # 404 on the ANALYTICS resource, not on the learner -- and deliberately not an empty
        # 200, which a client would render as a learner with nothing to worry about.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"stage": "predictions", "error": "no analytics for this learner yet"},
        ) from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


# --- B6.2: session history, skill progress and class reports ---------------------------


@router.get("/students/{student_id}/sessions", response_model=SessionHistoryResponse)
async def student_sessions(
    student_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> SessionHistoryResponse:
    """Panel history with Component B and Component C as SEPARATE field groups. An empty
    history is a legitimate 200 with `sessions: []` -- unlike `/students/{id}`, there is no
    claim being made here that an empty list could be misread as."""

    try:
        return await dashboard_service.session_history(
            session,
            principal.teacher_profile_id,
            student_id,
            model_version=_active_model_version(),
        )
    except dashboard_service.LearnerNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


@router.get("/students/{student_id}/skills", response_model=SkillProgressResponse)
async def student_skills(
    student_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> SkillProgressResponse:
    try:
        return await dashboard_service.skill_progress(
            session,
            principal.teacher_profile_id,
            student_id,
            model_version=_active_model_version(),
        )
    except dashboard_service.LearnerNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except dashboard_service.NoPredictionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"stage": "sessions", "error": "no session history for this learner yet"},
        ) from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc


@router.get("/classes/{classroom_id}/reports", response_model=ClassReportResponse)
async def class_reports(
    classroom_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> ClassReportResponse:
    try:
        return await dashboard_service.class_report(
            session,
            principal.teacher_profile_id,
            classroom_id,
            model_version=_active_model_version(),
        )
    except dashboard_service.ClassroomNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except ActivePipelineRunError as exc:
        raise _no_active_run(exc) from exc
