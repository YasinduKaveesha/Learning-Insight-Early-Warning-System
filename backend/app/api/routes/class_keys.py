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

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import CurrentPrincipal, DbSession
from app.api.routes.dashboard import _FORBIDDEN
from app.application import class_key_service
from app.domain.dashboard import ClassKeyResponse


class ClassKeyStoreRequest(BaseModel):
    """The join code the student application minted for this classroom and showed once.

    Accepted grouped (``M7KP-4X9D``) or bare -- it is normalised before hashing, exactly as the
    student app normalises before it hashes, so a code a child could redeem is never rejected
    here for the dashes a teacher reads it with.
    """

    invite_token: str = Field(min_length=1, max_length=32)

router = APIRouter(prefix="/api/v1/t3", tags=["classes"])


@router.post(
    "/classes/{classroom_id}/key",
    response_model=ClassKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def ensure_key(
    classroom_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: DbSession,
    body: ClassKeyStoreRequest | None = None,
) -> ClassKeyResponse:
    """200, not 201: the caller asked for the classroom's key, and whether this call happened to
    store it is not their business -- the answer is the same key either way.

    With a body, the caller is handing over the join code the student application just minted and
    showed once (D49); it is verified against that classroom's live invite before it is stored.
    Without one, this reads back the key already held, and can never create one.
    """

    try:
        key = await class_key_service.ensure_class_key(
            session,
            principal.teacher_profile_id,
            classroom_id,
            invite_token=body.invite_token if body is not None else None,
        )
    except class_key_service.ClassroomNotVisibleError as exc:
        raise _FORBIDDEN from exc
    except class_key_service.InviteTokenMismatchError as exc:
        # 422, not 404: the classroom is visible and the request is well-formed -- the code in it
        # is simply not this classroom's live join code. Same answer for a wrong, revoked or
        # other-classroom code, so none can be told apart by probing.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invite_token is not this classroom's live join code",
        ) from exc
    except class_key_service.ClassKeyNotIssuedError as exc:
        # 404: there is no key to read, and this endpoint cannot invent one -- only the student
        # application can mint a code, because only it holds the hash a learner is checked against.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="this classroom has no join code stored yet",
        ) from exc
    return ClassKeyResponse(classroom_id=classroom_id, class_key=key)
