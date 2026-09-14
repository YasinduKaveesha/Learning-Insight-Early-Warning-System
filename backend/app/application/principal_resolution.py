"""`resolve_principal` -- the sole seam that decides WHO is calling (work order B2.3).

A verified JWT signature (`app.infrastructure.auth.VerifiedClaims`) is NOT an authorized
teacher -- verify, then separately resolve identity (`plan/backend_plan.md` section 8 "Auth").
This module is that separate step, and the only place identity gets decided.

Two paths:

* **Real path.** `sub` -> `app_users.supabase_subject` (filtered to `source_class = 'REAL'`)
  -> must have `profile_type = 'TEACHER'` -> `teacher_profiles` (REAL only). Missing at any
  step raises `PrincipalNotAuthorizedError` (403) -- Component 3 NEVER provisions an
  `app_users` or `teacher_profiles` row; that is the student app's exclusive job
  (Agent Handower/BACKEND_SUPERVISOR_HANDOVER.md section 8.4). This module contains no
  `INSERT`, `UPDATE` or `DELETE` against either table -- see `tests/test_no_bc_writeback.py`'s
  sibling guard for the `t3_*`-only write rule this module also respects for `app_users` /
  `teacher_profiles` specifically.
* **Demo path.** Reachable ONLY when `settings.t3_demo_mode` is true AND the token's own
  claims mark it anonymous (`VerifiedClaims.is_anonymous`). `sub` -> `t3_teacher_bindings` ->
  `teacher_profile_id`. No existing binding: claim the next unclaimed REAL teacher from
  `T3_DEMO_TEACHER_POOL`. Pool exhausted, unset, or empty raises `DemoPoolExhaustedError`
  (409, `error_code = "demo_pool_exhausted"`). An anonymous subject presented while demo mode
  is off is refused outright by `PrincipalNotAuthorizedError` -- never treated as a default
  teacher, and the claiming code below is provably unreached in that case (gate 9).

Claiming is race-safe by construction, mirroring `app.application.class_key`'s
generate-insert-catch-collision-retry shape: this module never checks "is this teacher
already bound" before inserting and treats that answer as settled -- it attempts an INSERT
per candidate inside a SAVEPOINT and reacts only to the unique-violation the database itself
raises on `teacher_profile_id`. Two concurrent claims for the same candidate are decided by
Postgres, not by a lookup this module could race against (mutation test 13b targets exactly
a check-then-insert rewrite of this).

**Never log `subject`.** No line in this module logs a claim value; every exception message
below is claim-free by construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import DemoPoolExhaustedError, PrincipalNotAuthorizedError
from app.domain.principal import Principal, VerifiedClaims
from app.infrastructure.db.models import TeacherBinding, app_users, teacher_profiles
from app.infrastructure.settings import Settings

#: The one value the real path filters every student-app lookup to. Never a parameter -- a
#: caller must not be able to ask this module to authorize against a TEST-fixture row.
REAL_SOURCE_CLASS = "REAL"

#: The only `profile_type` the real path accepts (`app_users.profile_type`, `docs/`
#: `ck_app_users_profile_type`: `'LEARNER'` or `'TEACHER'`).
TEACHER_PROFILE_TYPE = "TEACHER"

#: A fixed, documented placeholder -- `t3_teacher_bindings` is an identity table, not a
#: pipeline output, but carries the full six-column `ProvenanceMixin` like
#: `t3_demo_learner_map` (which also carries a non-FK `pipeline_run_id` for the same reason).
#: This is never a real `t3_pipeline_runs` id and is never joined against that table.
DEMO_BINDING_PIPELINE_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

#: Bounded claim-attempt budget -- one attempt per configured pool entry, so a stuck or
#: fully-claimed pool raises `DemoPoolExhaustedError` rather than looping unbounded.
_MAX_CLAIM_ATTEMPTS = 100


# ==========================================================================================
# Real path -- app_users -> teacher_profiles, REAL only, read-only.
# ==========================================================================================


async def _real_app_user(session: AsyncSession, subject: str):
    stmt = select(app_users.c.user_id, app_users.c.profile_type).where(
        app_users.c.supabase_subject == subject,
        app_users.c.source_class == REAL_SOURCE_CLASS,
    )
    return (await session.execute(stmt)).first()


async def _real_teacher_profile_for_user(session: AsyncSession, user_id: uuid.UUID):
    stmt = select(teacher_profiles.c.teacher_profile_id).where(
        teacher_profiles.c.user_id == user_id,
        teacher_profiles.c.source_class == REAL_SOURCE_CLASS,
    )
    return (await session.execute(stmt)).first()


async def _resolve_real_principal(session: AsyncSession, subject: str) -> Principal:
    user_row = await _real_app_user(session, subject)
    if user_row is None:
        raise PrincipalNotAuthorizedError("no REAL app_users row for this subject")
    if user_row.profile_type != TEACHER_PROFILE_TYPE:
        raise PrincipalNotAuthorizedError("subject's app_users row is not a TEACHER profile")

    teacher_row = await _real_teacher_profile_for_user(session, user_row.user_id)
    if teacher_row is None:
        raise PrincipalNotAuthorizedError("no REAL teacher_profiles row for this user")

    return Principal(teacher_profile_id=teacher_row.teacher_profile_id, resolution="real")


# ==========================================================================================
# Demo path -- t3_teacher_bindings, race-safe claim from T3_DEMO_TEACHER_POOL.
# ==========================================================================================


async def _existing_binding(session: AsyncSession, subject: str):
    stmt = select(TeacherBinding.teacher_profile_id).where(
        TeacherBinding.supabase_subject == subject
    )
    return (await session.execute(stmt)).first()


async def real_candidate_teacher_ids(
    session: AsyncSession, pool: Sequence[uuid.UUID]
) -> list[uuid.UUID]:
    """Filter `pool` to the subset with a REAL `teacher_profiles` row, preserving `pool`'s
    order. Pure filtering, not a claim check -- `source_class` does not change concurrently,
    so reading it first is not the check-then-insert race the claim loop below must avoid.
    This is gate 7's enforcement point: a TEST-provenance pool entry is silently excluded
    from candidacy, never a 500, and never inserted into `t3_teacher_bindings`.
    """

    if not pool:
        return []
    stmt = select(teacher_profiles.c.teacher_profile_id).where(
        teacher_profiles.c.teacher_profile_id.in_(pool),
        teacher_profiles.c.source_class == REAL_SOURCE_CLASS,
    )
    real_ids = {row.teacher_profile_id for row in (await session.execute(stmt)).all()}
    return [candidate for candidate in pool if candidate in real_ids]


async def _claim_demo_teacher(
    session: AsyncSession, subject: str, pool: Sequence[str]
) -> uuid.UUID:
    """Race-safe claim. Attempts an INSERT per REAL candidate in turn, inside a SAVEPOINT so
    one candidate's unique-violation does not poison the session; on a `teacher_profile_id`
    collision (another subject won that candidate first, possibly concurrently) it moves to
    the next one. Deliberately NOT check-then-insert: there is no "is this teacher already
    bound" SELECT anywhere in this function -- the UNIQUE constraint on
    `t3_teacher_bindings.teacher_profile_id` is the only arbiter (mutation test 13b targets a
    rewrite that adds exactly that SELECT).
    """

    if not pool:
        raise DemoPoolExhaustedError("T3_DEMO_TEACHER_POOL is empty or unset")

    candidate_ids = [uuid.UUID(entry) for entry in pool]
    real_candidates = await real_candidate_teacher_ids(session, candidate_ids)

    for candidate in real_candidates[:_MAX_CLAIM_ATTEMPTS]:
        try:
            async with session.begin_nested():
                await session.execute(
                    insert(TeacherBinding).values(
                        supabase_subject=subject,
                        teacher_profile_id=candidate,
                        source_class="SYNTHETIC",
                        source_system="t3-demo-mode",
                        parameter_source_status="DEMO_ASSIGNED",
                        pipeline_run_id=DEMO_BINDING_PIPELINE_RUN_ID,
                    )
                )
        except IntegrityError:
            continue
        await session.commit()
        return candidate

    raise DemoPoolExhaustedError(
        f"no unclaimed T3_DEMO_TEACHER_POOL slot for this subject after "
        f"{len(real_candidates)} REAL candidate(s)"
    )


async def _resolve_demo_principal(
    session: AsyncSession, subject: str, settings: Settings
) -> Principal:
    existing = await _existing_binding(session, subject)
    if existing is not None:
        return Principal(teacher_profile_id=existing.teacher_profile_id, resolution="demo")

    teacher_profile_id = await _claim_demo_teacher(
        session, subject, settings.t3_demo_teacher_pool
    )
    return Principal(teacher_profile_id=teacher_profile_id, resolution="demo")


# ==========================================================================================
# The seam.
# ==========================================================================================


async def resolve_principal(
    session: AsyncSession, claims: VerifiedClaims, settings: Settings
) -> Principal:
    """The sole place identity gets decided. See the module docstring for the two paths.

    An anonymous subject with `T3_DEMO_MODE` off is refused by `PrincipalNotAuthorizedError`
    before any demo-path code runs -- never treated as a default teacher (gate 9).
    """

    if claims.is_anonymous:
        if not settings.t3_demo_mode:
            raise PrincipalNotAuthorizedError(
                "anonymous subject presented while T3_DEMO_MODE is off"
            )
        return await _resolve_demo_principal(session, claims.subject, settings)

    return await _resolve_real_principal(session, claims.subject)
