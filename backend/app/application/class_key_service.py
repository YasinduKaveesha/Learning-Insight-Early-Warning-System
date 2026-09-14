"""Minting and reading the permanent class key (B7 / B6.4; D1).

THE ONE RULE: **a class key is generated once and never changes.** There is no rotation, no
regeneration and no deletion anywhere in this codebase -- `ClassroomKeyRepository` is insert-only
and `app.application.class_key` exposes no update path. A teacher reads this key aloud to a room
and a child types it to join; a key that changed would lock out every child who wrote it down.

So `ensure_class_key` is idempotent by DESIGN, not by luck: if the classroom already has a key it
returns THAT key and writes nothing. It never compares, replaces or "refreshes" it.

Called at two moments, both deliberate:

* class creation (B6.4) -- the classroom is created through the student app's own API, which knows
  nothing about `t3_classroom_keys`, and the dashboard then asks for its key;
* `backend/scripts/mint_class_keys.py`, for classrooms that existed before this endpoint.

Reading it happens on the cohort response (`class_key`), never by minting on a GET.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.application import data_access
from app.infrastructure.classroom_key_repository import ClassroomKeyRepository

#: A fixed, documented placeholder, as in `principal_resolution.DEMO_BINDING_PIPELINE_RUN_ID`.
#: `t3_classroom_keys` carries the provenance columns because every t3_ table does, not because a
#: class key is a pipeline output. It is never joined against `t3_pipeline_runs`.
CLASS_KEY_PIPELINE_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

SOURCE_CLASS = "REAL"
SOURCE_SYSTEM = "t3-class-key"
PARAMETER_SOURCE_STATUS = "OPERATOR_ASSIGNED"


class ClassroomNotVisibleError(PermissionError):
    """The classroom does not exist, is not REAL, or belongs to another teacher. One answer for
    all three, so an id cannot be probed for existence."""


async def ensure_class_key(
    session: AsyncSession, teacher_profile_id: uuid.UUID, classroom_id: uuid.UUID
) -> str:
    """Return this classroom's permanent key, minting it only if it has none.

    The ownership guard runs FIRST: a caller who does not own the classroom must not be able to
    cause a write, nor learn whether a key exists.
    """

    if not await data_access.teacher_owns_classroom(session, teacher_profile_id, classroom_id):
        raise ClassroomNotVisibleError(str(classroom_id))

    existing = await data_access.class_keys_for_classrooms(session, [classroom_id])
    if classroom_id in existing:
        return existing[classroom_id]  # never re-minted, never rotated

    key = await ClassroomKeyRepository(session).create_key(
        classroom_id,
        source_class=SOURCE_CLASS,
        source_system=SOURCE_SYSTEM,
        parameter_source_status=PARAMETER_SOURCE_STATUS,
        pipeline_run_id=CLASS_KEY_PIPELINE_RUN_ID,
    )
    await session.commit()
    return key
