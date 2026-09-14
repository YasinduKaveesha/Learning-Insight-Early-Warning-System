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
The one-off repair of the six pre-D49 demo keys ran on 2026-09-14 and its script has been
removed: it wrote to `classroom_invites` (a table the student app owns, D3/D10) and carried an
overwrite path for a key D1 calls permanent. `backend/scripts/verify_class_keys.py` replaces it
and only READS -- a mismatch is repaired by asking the student app to reissue, never by writing.

Reading it happens on the cohort response (`class_key`), never by minting on a GET.
"""

from __future__ import annotations

import re
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


class InviteTokenMismatchError(ValueError):
    """The supplied code is not this classroom's live join code (D49).

    Raised for a wrong code, a revoked one, and one belonging to another classroom alike. The
    caller learns only that this code will not be stored -- never whether some *other* code
    would have been accepted.
    """


class ClassKeyNotIssuedError(LookupError):
    """Asked for a key the classroom does not have, without supplying one to store.

    This endpoint cannot mint a code: only the student application can, because only it holds
    the hash a learner's code is checked against. A classroom reaches this state when its
    invite was created but storing the code failed -- the repair is to revoke that invite and
    create the pair again, never to invent a key here.
    """


def normalise_join_code(raw: str) -> str:
    """Match the student application's normalisation exactly: strip separators, upper-case.

    A teacher is shown ``M7KP-4X9D`` and may hand back either that or ``m7kp4x9d``; the student
    app hashes the ungrouped upper-case form. Normalising differently here would reject a code a
    child could successfully redeem -- the two applications must agree character for character.
    """

    return re.sub(r"[\s-]+", "", raw).upper()


async def ensure_class_key(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    classroom_id: uuid.UUID,
    invite_token: str | None = None,
) -> str:
    """Return this classroom's permanent key, storing `invite_token` only if it has none.

    The ownership guard runs FIRST: a caller who does not own the classroom must not be able to
    cause a write, nor learn whether a key exists.

    `invite_token` is the plaintext join code the student application minted for this classroom
    and showed exactly once. It is **verified against the live invite's hash** before it is
    stored (D49) -- Component 3 keeps the only readable copy of a code that grants entry to a
    classroom, so it must not keep whatever string a caller sent.

    Omitting the token is legitimate and means "tell me the key you already have". It is the
    only way to read a key back after class creation, and it can never mint one.
    """

    if not await data_access.teacher_owns_classroom(session, teacher_profile_id, classroom_id):
        raise ClassroomNotVisibleError(str(classroom_id))

    existing = await data_access.class_keys_for_classrooms(session, [classroom_id])
    if classroom_id in existing:
        return existing[classroom_id]  # never re-stored, never rotated

    if invite_token is None:
        raise ClassKeyNotIssuedError(str(classroom_id))

    canonical = normalise_join_code(invite_token)
    if not await data_access.token_matches_live_invite(session, classroom_id, canonical):
        raise InviteTokenMismatchError(str(classroom_id))

    key = await ClassroomKeyRepository(session).store_key(
        classroom_id,
        canonical,
        source_class=SOURCE_CLASS,
        source_system=SOURCE_SYSTEM,
        parameter_source_status=PARAMETER_SOURCE_STATUS,
        pipeline_run_id=CLASS_KEY_PIPELINE_RUN_ID,
    )
    await session.commit()
    return key
