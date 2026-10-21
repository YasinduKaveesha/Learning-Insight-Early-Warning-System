"""CompD's teacher side: 6 paths, 7 operations under `/api/v1/t3/compd` (owner direction
2026-10-21: the dashboard serves compD itself, independent of the student app's API).

compD's own teacher routes, re-homed. GET and POST only -- this API's CORS allows exactly those --
so compD's `PUT` and `DELETE /questions/{id}` are `POST .../update` and `POST .../delete`.

Every route depends on `CurrentPrincipal`: a caller who is not a resolved teacher is a 401/403
before anything here runs. Which teacher it is does not narrow what CompD shows (every REAL child,
one shared bank -- owner Q8, Q10); it is recorded as a question's author and editor.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import CurrentPrincipal, DbSession
from app.application import compd_service
from app.domain.compd import (
    CompdDashboardResponse,
    CompdDraftRequest,
    CompdDrafts,
    CompdMessage,
    CompdQuestion,
    CompdQuestionCreate,
    CompdQuestionList,
    CompdQuestionUpdate,
    CompdStudentProfiles,
    Difficulty,
    Topic,
)
from app.infrastructure.compd_ai import CompdAiUnavailable
from app.infrastructure.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/t3/compd", tags=["compd"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def ai_transport() -> httpx.AsyncBaseTransport | None:
    """The transport the Gemini call uses. `None` is the real network; tests override this."""

    return None


@router.get("/dashboard", response_model=CompdDashboardResponse)
async def get_dashboard(principal: CurrentPrincipal, session: DbSession) -> CompdDashboardResponse:
    return await compd_service.dashboard(session)


@router.get("/students/{student_id}/profiles", response_model=CompdStudentProfiles)
async def get_student_profiles(
    student_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CompdStudentProfiles:
    try:
        return await compd_service.student_profiles(session, student_id, limit)
    except compd_service.CompdNotFoundError as exc:
        raise _NOT_FOUND from exc


@router.get("/questions", response_model=CompdQuestionList)
async def list_questions(
    principal: CurrentPrincipal,
    session: DbSession,
    topic: Annotated[Topic | None, Query()] = None,
    difficulty: Annotated[Difficulty | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CompdQuestionList:
    return await compd_service.list_questions(session, topic=topic, difficulty=difficulty, limit=limit)


@router.post("/questions", response_model=CompdQuestion, status_code=status.HTTP_201_CREATED)
async def create_question(
    body: CompdQuestionCreate, principal: CurrentPrincipal, session: DbSession
) -> CompdQuestion:
    try:
        return await compd_service.create_question(session, principal.teacher_profile_id, body)
    except compd_service.CompdConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="question_code already exists") from exc


@router.post("/questions/{question_id}/update", response_model=CompdQuestion)
async def update_question(
    question_id: uuid.UUID, body: CompdQuestionUpdate, principal: CurrentPrincipal, session: DbSession
) -> CompdQuestion:
    try:
        return await compd_service.update_question(session, principal.teacher_profile_id, question_id, body)
    except compd_service.CompdNotFoundError as exc:
        raise _NOT_FOUND from exc
    except compd_service.CompdConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="question_code already exists") from exc
    except compd_service.CompdOptionsError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"field": "options", "error": str(exc)}
        ) from exc


@router.post("/questions/{question_id}/delete", response_model=CompdMessage)
async def delete_question(
    question_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> CompdMessage:
    try:
        return await compd_service.delete_question(session, question_id)
    except compd_service.CompdNotFoundError as exc:
        raise _NOT_FOUND from exc


@router.post("/questions/drafts", response_model=CompdDrafts)
async def draft_questions(
    body: CompdDraftRequest,
    principal: CurrentPrincipal,
    settings: Annotated[Settings, Depends(get_settings)],
    transport: Annotated[httpx.AsyncBaseTransport | None, Depends(ai_transport)],
) -> CompdDrafts:
    """Drafts only, NOT saved. 503: the AI is not available (no key, timeout, provider error).
    422: it answered, but nothing usable came back."""

    try:
        return await compd_service.draft_questions(body, api_key=settings.gemini_api_key, transport=transport)
    except CompdAiUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI drafts unavailable") from exc
    except compd_service.CompdDraftsUnusableError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the AI returned no usable drafts"
        ) from exc
