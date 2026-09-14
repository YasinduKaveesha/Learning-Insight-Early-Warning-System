"""The permanent class key endpoint (B7 / B6.4; D1).

ONE route, and it is a POST for a reason: minting a key is a write, and a GET that writes is a
side effect a preflight, a retry or a second browser tab would trip over. Reading an existing key
needs no call at all -- it rides on the cohort response.

The POST is IDEMPOTENT and never rotates: a classroom that already has a key gets that same key
back. There is deliberately no PUT, PATCH or DELETE here, and none may be added: a class key is
permanent (D1), because children write it down.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.dependencies import CurrentPrincipal, DbSession
from app.api.routes.dashboard import _FORBIDDEN
from app.application import class_key_service
from app.domain.dashboard import ClassKeyResponse

router = APIRouter(prefix="/api/v1/t3", tags=["classes"])


@router.post(
    "/classes/{classroom_id}/key",
    response_model=ClassKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def ensure_key(
    classroom_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> ClassKeyResponse:
    """200, not 201: the caller asked for the classroom's key, and whether this call happened to
    mint it is not their business -- the answer is the same key either way."""

    try:
        key = await class_key_service.ensure_class_key(
            session, principal.teacher_profile_id, classroom_id
        )
    except class_key_service.ClassroomNotVisibleError as exc:
        raise _FORBIDDEN from exc
    return ClassKeyResponse(classroom_id=classroom_id, class_key=key)
