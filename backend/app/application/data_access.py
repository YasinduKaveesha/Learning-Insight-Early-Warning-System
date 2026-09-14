"""The shared data-access layer (work order B2.4).

One module, and after this lands the only module, that reads:

* student-app identity/roster tables (`classrooms`, `classroom_memberships`, `b_learners`)
* Component 3's own analytics tables (`t3_pipeline_runs`, `t3_panel`, `t3_features_at_t`,
  `t3_predictions`)

No migration, no endpoint and no other logic lives here -- see `plan/backend_plan.md`
section 8 ("Layering"): this is the `app/application/` repository layer that B5/B6/B4.2 call,
not a caller of them.

Two DISTINCT provenance rules, deliberately not unified into one `filter_real()` helper:

* **Student-app tables mix real and test-fixture rows.** Every reader in the
  "student-app readers" section below filters `source_class = 'REAL'` -- unconditionally,
  with no parameter to turn it off. `b_learners` measured live: 47 REAL rows (all
  `status='ACTIVE'`), 94 TEST rows (`status` either lowercase `'active'` or `'test_only'`,
  *all* of them TEST). Filtering on `source_class` alone throws out every TEST row; a
  separate `status` case-fix would paper over the real rule.
* **Component 3's own `t3_*` analytics rows are SYNTHETIC BY DESIGN** (`docs/` D15, the
  research dataset behind v1). They are written with `source_class = 'SYNTHETIC'`.
  Applying `source_class = 'REAL'` to `t3_panel` / `t3_features_at_t` / `t3_predictions`
  returns **zero rows** -- an empty dashboard that reads as "no one needs attention" rather
  than a bug. The "t3 readers" section below scopes exclusively by the active
  `pipeline_run_id` and never touches `source_class`.

Every join here uses `b_learners.learner_id` (uuid). The derived display code
(sha256 of the learner id, reduced modulo 10,000) is roughly a 50% collision probability
at ~118 learners and must never be used as a join key anywhere in this module.

Every function below names the exact columns it returns; none select every column of a
table. That is what keeps a forbidden field (a latent trait, a raw token) from leaking by
way of a row that happened to carry everything. Nothing in this module logs `population`,
`dd_subtype`, or a raw token.
"""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import (
    ClassroomKey,
    FeaturesAtT,
    Panel,
    PipelineRun,
    Prediction,
    Recommendation,
)
from app.infrastructure.db.models import (
    b_learners,
    classroom_invites,
    classroom_memberships,
    classrooms,
    teacher_profiles,
)

#: The one value every student-app reader in this module filters to. Never a parameter --
#: a caller must not be able to ask this layer for TEST rows.
REAL_SOURCE_CLASS = "REAL"

#: The APPROVED membership state -- UPPERCASE, matching `classroom_memberships.state`
#: (`plan/backend_plan.md` section 3). PENDING and REJECTED never count as roster members.
APPROVED_STATE = "APPROVED"
PENDING_STATE = "PENDING"


class ActivePipelineRunError(RuntimeError):
    """`active_pipeline_run` could not resolve exactly one run for the given model version."""


# ==========================================================================================
# Provenance root
# ==========================================================================================


async def active_pipeline_run(
    session: AsyncSession, *, active_model_version: str
) -> Row:
    """Resolve the ONE `t3_pipeline_runs` row the API serves from.

    `active_model_version` is the caller's `T3_ACTIVE_MODEL_VERSION` (settings live outside
    this module -- see `app/infrastructure/settings.py`). Zero matching runs, or more than
    one, is an error: ambiguity must never be resolved by silently picking the newest, since
    that would let a re-run silently mix generations of derived data on screen.
    """

    stmt = select(
        PipelineRun.pipeline_run_id,
        PipelineRun.model_version,
        PipelineRun.started_at_utc,
        PipelineRun.dataset_manifest,
    ).where(PipelineRun.model_version == active_model_version)

    rows = (await session.execute(stmt)).all()

    if not rows:
        raise ActivePipelineRunError(
            f"no t3_pipeline_runs row for active model version {active_model_version!r}"
        )
    if len(rows) > 1:
        raise ActivePipelineRunError(
            f"{len(rows)} t3_pipeline_runs rows found for active model version "
            f"{active_model_version!r}; exactly one is required -- refusing to pick one"
        )
    return rows[0]



def _as_records(rows: Sequence[Row]) -> list[SimpleNamespace]:
    """Convert result rows to plain namespaces so selected columns are reachable by name.

    THIS IS NOT COSMETIC. `sqlalchemy.Row` defines its own attributes -- `t`, `count`,
    `index` among them -- and they SHADOW a selected column of the same name.
    `t3_predictions.t` is exactly that collision: on a real `Row`, `row.t` returns the
    tuple accessor, not the snapshot index. It type-checks, it never raises at the access
    site, and the wrong object travels until something far away rejects it.

    It stayed invisible for two phases because the dashboard tests monkeypatch this module
    wholesale with a hand-written stand-in whose `.t` is an ordinary attribute, and because
    `t3_predictions` was empty until a real pipeline run existed. The first real request
    after that run returned HTTP 500.

    Returning namespaces means the reader layer hands back only what it selected, under the
    names it selected them by -- so no future column can be shadowed by the row type.
    """

    return [SimpleNamespace(**row._mapping) for row in rows]


# ==========================================================================================
# Student-app readers -- ALWAYS filter source_class = 'REAL'.
# ==========================================================================================


async def real_learners(
    session: AsyncSession, *, learner_ids: Sequence[uuid.UUID] | None = None
) -> Sequence[Row]:
    """`b_learners` rows with `source_class = 'REAL'`. Never returns a TEST row.

    `learner_ids`, when given, narrows the result further; it does not replace the
    `source_class` filter.
    """

    stmt = select(
        b_learners.c.learner_id,
        b_learners.c.name,
        b_learners.c.grade,
        b_learners.c.status,
    ).where(b_learners.c.source_class == REAL_SOURCE_CLASS)
    if learner_ids is not None:
        stmt = stmt.where(b_learners.c.learner_id.in_(learner_ids))
    return (await session.execute(stmt)).all()


async def classroom_roster(session: AsyncSession, classroom_id: uuid.UUID) -> Sequence[Row]:
    """The learners a teacher sees for one classroom: APPROVED membership, REAL learner.

    A learner is APPROVED in at most one classroom (a partial unique index on
    `classroom_memberships.learner_id` enforces it on the live schema), so this never
    double-counts a learner across classes. PENDING and REJECTED rows never appear here.
    """

    stmt = (
        select(
            b_learners.c.learner_id,
            b_learners.c.name,
            b_learners.c.grade,
            b_learners.c.status,
        )
        .select_from(
            classroom_memberships.join(
                b_learners,
                classroom_memberships.c.learner_id == b_learners.c.learner_id,
            )
        )
        .where(
            classroom_memberships.c.classroom_id == classroom_id,
            classroom_memberships.c.state == APPROVED_STATE,
            b_learners.c.source_class == REAL_SOURCE_CLASS,
        )
    )
    return (await session.execute(stmt)).all()


async def classrooms_for_teacher(
    session: AsyncSession, teacher_profile_id: uuid.UUID
) -> Sequence[Row]:
    """Every REAL classroom this teacher owns. The scoping read behind `/home` and the
    all-classes watch list.

    Carries the student-app provenance rule (`source_class = 'REAL'`) like every other
    reader in this section -- a TEST classroom must never appear on a teacher's home screen
    even though it is genuinely owned by them.

    A classroom the teacher DELETED (student-app migration 20260914_0009, a soft delete) is
    excluded the same way on every classroom reader and guard here: it keeps its row, but it
    is gone from every teacher screen.
    """

    stmt = select(
        classrooms.c.classroom_id,
        classrooms.c.name,
        classrooms.c.grade,
    ).where(
        classrooms.c.teacher_profile_id == teacher_profile_id,
        classrooms.c.source_class == REAL_SOURCE_CLASS,
        classrooms.c.deleted_at_utc.is_(None),
    )
    return (await session.execute(stmt)).all()


async def teacher_display_name(
    session: AsyncSession, teacher_profile_id: uuid.UUID
) -> str | None:
    """`teacher_profiles.name` for the signed-in teacher, or None.

    NOT NULL upstream, so None here means the row is absent or not REAL rather than unnamed --
    which cannot normally happen, because `resolve_principal` already required a REAL
    `teacher_profiles` row to mint the principal. Returning None rather than raising keeps a
    display detail from taking down a page that is otherwise fine.
    """

    stmt = select(teacher_profiles.c.name).where(
        teacher_profiles.c.teacher_profile_id == teacher_profile_id,
        teacher_profiles.c.source_class == REAL_SOURCE_CLASS,
    )
    row = (await session.execute(stmt)).first()
    return None if row is None else row.name


async def classroom_for_learner(
    session: AsyncSession, teacher_profile_id: uuid.UUID, learner_id: uuid.UUID
) -> Row | None:
    """The APPROVED classroom this learner sits in, within this teacher's classes.

    `StudentDetail` carries no classroom context at all, so the student-overview screen has no
    other source for a class name. Scoped by `teacher_profile_id` on purpose: this is a read
    on behalf of one teacher, and a learner may only ever be seen through a class that teacher
    owns. It is NOT an ownership guard -- `learner_visible_to_teacher` remains that -- but it
    must not be able to leak a class name the caller could not otherwise see.

    A learner holds at most one APPROVED membership across all classrooms (the student app
    enforces it with a partial unique index), so this returns at most one row.
    """

    stmt = (
        select(classrooms.c.classroom_id, classrooms.c.name, classrooms.c.grade)
        .select_from(classroom_memberships)
        .join(
            classrooms,
            classrooms.c.classroom_id == classroom_memberships.c.classroom_id,
        )
        .where(
            classroom_memberships.c.learner_id == learner_id,
            classroom_memberships.c.state == APPROVED_STATE,
            classrooms.c.teacher_profile_id == teacher_profile_id,
            classrooms.c.source_class == REAL_SOURCE_CLASS,
            classrooms.c.deleted_at_utc.is_(None),
        )
    )
    return (await session.execute(stmt)).first()


async def pending_request_counts(
    session: AsyncSession, classroom_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """PENDING join requests per classroom, for the pending-request indicator.

    Read-only toward `classroom_memberships`: approving or rejecting a request belongs to
    the student app's own endpoints (D3/D10), and Component 3 never writes here. The count
    is only an indicator that takes a teacher to that app's flow.
    """

    if not classroom_ids:
        return {}

    stmt = (
        select(
            classroom_memberships.c.classroom_id,
            func.count().label("pending"),
        )
        .where(
            classroom_memberships.c.classroom_id.in_(classroom_ids),
            classroom_memberships.c.state == PENDING_STATE,
        )
        .group_by(classroom_memberships.c.classroom_id)
    )
    return {row.classroom_id: row.pending for row in (await session.execute(stmt)).all()}


# ==========================================================================================
# t3_* readers -- scoped by the active pipeline_run_id. NEVER filtered by source_class.
# ==========================================================================================


async def handled_suggestions_for_run(
    session: AsyncSession, pipeline_run_id: uuid.UUID
) -> dict[uuid.UUID, tuple[str, int]]:
    """Learners whose OPEN suggestion a teacher has accepted or modified, in this run.

    Returns ``student_id -> (teacher_status, expires_after_session)``. The caller compares the
    expiry against the learner's current session, because expiry is measured against a value
    this table does not hold (see D47).

    "Handled" is decision B, 2026-09-14: a handled watch-flagged learner moves out of the class
    page's Students to Watch section but STAYS in the watch count. Only `accepted` and
    `modified` qualify -- a `dismissed` suggestion means the teacher disagreed with it, so the
    child stays on the watch list. A CLOSED suggestion (D47) no longer counts: once its active
    period ends, a still-flagged child returns to the list.

    Scoped by `pipeline_run_id`, never by `source_class`, like every t3_ reader. Reads status and
    expiry only -- never evidence, never the proposed action.
    """

    stmt = select(
        Recommendation.student_id,
        Recommendation.teacher_status,
        Recommendation.expires_after_session,
    ).where(
        Recommendation.pipeline_run_id == pipeline_run_id,
        Recommendation.teacher_status.in_(("accepted", "modified")),
        Recommendation.closed_at_session.is_(None),
    )
    return {
        row.student_id: (row.teacher_status, row.expires_after_session)
        for row in (await session.execute(stmt)).all()
    }


async def class_keys_for_classrooms(
    session: AsyncSession, classroom_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """The permanent class key for each of `classroom_ids`, for those that have one.

    **The one t3_ reader that is NOT scoped by `pipeline_run_id`, and the reason is D1.** The
    key is generated once at class creation and never rotated; it is a property of the
    classroom, not of a pipeline run. `t3_classroom_keys` carries `pipeline_run_id` because
    `plan/backend_plan.md` section 4 gives every new table the provenance columns, not because
    the key belongs to a run -- so scoping this read by the active run would make a teacher's
    key disappear the moment a new run was published, which is precisely the permanence D1
    promises. Scoped by `classroom_id` instead, and the caller has already passed the
    ownership guard.

    A classroom with no key is ABSENT from the result rather than mapped to `""`. The demo
    classrooms were created through the student app's API, which knows nothing about
    `t3_classroom_keys`, so missing is a real state the UI has to handle -- and an empty
    string looks like a key that is blank rather than a key that was never minted.
    """

    if not classroom_ids:
        return {}

    stmt = select(ClassroomKey.classroom_id, ClassroomKey.class_key).where(
        ClassroomKey.classroom_id.in_(classroom_ids)
    )
    return {row.classroom_id: row.class_key for row in (await session.execute(stmt)).all()}



async def panel_rows_for_run(
    session: AsyncSession,
    pipeline_run_id: uuid.UUID,
    *,
    student_id: uuid.UUID | None = None,
) -> Sequence[Row]:
    """`t3_panel` rows for one pipeline run. Deliberately carries NO `source_class` filter
    -- `t3_panel` is written with `source_class = 'SYNTHETIC'` by design (D15), and applying
    the student-app REAL rule here would silently return zero rows."""

    stmt = select(
        Panel.student_id,
        Panel.intervention_session_number,
        Panel.intervention_session_date,
        Panel.b_present,
        Panel.c_present,
        Panel.b_accuracy_rate,
        Panel.c_accuracy_rate,
        Panel.c_engagement_score,
        Panel.c_frustration_index,
        Panel.pipeline_run_id,
    ).where(Panel.pipeline_run_id == pipeline_run_id)
    if student_id is not None:
        stmt = stmt.where(Panel.student_id == student_id)
    return (await session.execute(stmt)).all()


async def session_history_for_student(
    session: AsyncSession,
    pipeline_run_id: uuid.UUID,
    student_id: uuid.UUID,
) -> Sequence[Row]:
    """`t3_panel` rows for ONE learner, with the per-session columns the sessions endpoint
    serves. Ordered by session number so the caller never has to re-sort.

    Separate from `panel_rows_for_run` on purpose: that reader is the narrow trajectory feed
    used by the decision layer, and widening it would hand every existing caller a much
    larger row for no reason. "Select the columns you intend to return" (backend_plan.md
    section 8) cuts both ways -- a reader should also not fetch columns its callers do not
    need.

    Carries the Component C guard columns (`c_session_technical_issue_flag`,
    `c_telemetry_quality_status`, `c_inactive_time_sec`) because a technical fault must never
    be rendered to a teacher as disengagement (backend_plan.md section 3). The service layer
    cannot make that distinction if the reader does not carry it.
    """

    stmt = (
        select(
            Panel.student_id,
            Panel.intervention_session_number,
            Panel.intervention_session_date,
            Panel.b_present,
            Panel.c_present,
            # Component B -- practice.
            Panel.b_accuracy_rate,
            Panel.b_total_questions,
            Panel.b_correct_responses,
            Panel.b_hint_requests,
            Panel.b_median_item_response_time_sec,
            # D42: read for the skill progress bar ONLY. The sessions service names every field
            # it returns, so selecting it here does not put it in the sessions response.
            Panel.b_mastery,
            Panel.b_mastery_slope_w4,
            Panel.b_opportunities_w4,
            # Component C -- games. NEVER merged with the B values above.
            Panel.c_accuracy_rate,
            Panel.c_task_completion_rate,
            Panel.c_median_game_task_latency_sec,
            Panel.c_engagement_score,
            Panel.c_engagement_components,
            Panel.c_frustration_index,
            Panel.c_frustration_components,
            Panel.c_learner_state,
            Panel.c_current_difficulty_level,
            Panel.c_difficulty_trend,
            # Guards.
            Panel.c_telemetry_quality_status,
            Panel.c_session_technical_issue_flag,
            Panel.c_inactive_time_sec,
        )
        .where(
            Panel.pipeline_run_id == pipeline_run_id,
            Panel.student_id == student_id,
        )
        .order_by(Panel.intervention_session_number)
    )
    return (await session.execute(stmt)).all()


async def features_for_run(
    session: AsyncSession,
    pipeline_run_id: uuid.UUID,
    *,
    student_id: uuid.UUID | None = None,
) -> Sequence[Row]:
    """`t3_features_at_t` rows for one pipeline run. No `source_class` filter -- see module
    docstring; the features matrix is synthetic by design (D15)."""

    stmt = select(
        FeaturesAtT.student_id,
        FeaturesAtT.t,
        FeaturesAtT.feature_version,
        FeaturesAtT.features,
        FeaturesAtT.pipeline_run_id,
    ).where(FeaturesAtT.pipeline_run_id == pipeline_run_id)
    if student_id is not None:
        stmt = stmt.where(FeaturesAtT.student_id == student_id)
    # Same `Row.t` collision as `predictions_for_run`.
    return _as_records((await session.execute(stmt)).all())


async def predictions_for_run(
    session: AsyncSession,
    pipeline_run_id: uuid.UUID,
    *,
    student_id: uuid.UUID | None = None,
) -> Sequence[Row]:
    """`t3_predictions` rows for one pipeline run. No `source_class` filter -- see module
    docstring. Does NOT select `prob_class_0/1/2plus`, `predicted_class` or
    `engagement_trajectory`: those are server-only / never-served fields (backend_plan.md
    section 8), and this reader has no caller that is entitled to them."""

    stmt = select(
        Prediction.student_id,
        Prediction.t,
        Prediction.model_version,
        # B6.3d: the frontend shows when a learner was last scored. Selected explicitly like
        # everything else here -- never `SELECT *`, which would put the never-served
        # probability columns one logging statement away from exposure.
        Prediction.inference_timestamp,
        Prediction.evidence_status,
        Prediction.sessions_completed,
        Prediction.watch_flag,
        Prediction.rank_within_t,
        Prediction.rank_percentile_within_t,
        Prediction.practice_trajectory,
        Prediction.risk_explanation,
        Prediction.shap_top3,
        Prediction.risk_level,
        Prediction.risk_level_status,
        Prediction.pipeline_run_id,
    ).where(Prediction.pipeline_run_id == pipeline_run_id)
    if student_id is not None:
        stmt = stmt.where(Prediction.student_id == student_id)
    # `_as_records`, not `.all()`: `Prediction.t` collides with `Row.t`. See its docstring.
    return _as_records((await session.execute(stmt)).all())


# ==========================================================================================
# Ownership guards -- the only place these two questions are answered. Both fail CLOSED:
# unknown, missing or ambiguous means False, never True.
# ==========================================================================================


async def teacher_owns_classroom(
    session: AsyncSession, teacher_profile_id: uuid.UUID, classroom_id: uuid.UUID
) -> bool:
    """True only if `classroom_id` exists, is REAL, and its `teacher_profile_id` matches.

    A nonexistent classroom, one owned by a different teacher, or one of TEST provenance
    returns False -- there is no separate "not found" branch to get wrong.

    The `source_class` filter was missing until B6.3d, which made this guard disagree with
    `classrooms_for_teacher` (which has always applied it): a TEST-provenance classroom passed
    the ownership check while never appearing on `/home`. Its sibling guard
    `learner_visible_to_teacher` filters provenance too. A guard family that disagrees with
    itself is how an access decision ends up depending on which endpoint you came through.
    """

    stmt = select(classrooms.c.classroom_id).where(
        classrooms.c.classroom_id == classroom_id,
        classrooms.c.teacher_profile_id == teacher_profile_id,
        classrooms.c.source_class == REAL_SOURCE_CLASS,
        classrooms.c.deleted_at_utc.is_(None),
    )
    return (await session.execute(stmt)).first() is not None


async def token_matches_live_invite(
    session: AsyncSession, classroom_id: uuid.UUID, canonical_token: str
) -> bool:
    """True only if `canonical_token` is this classroom's live join code (D49).

    Component 3 stores the plaintext so a teacher can re-read it, but it must never store a
    string a browser simply asserted is the code. The student app keeps
    `sha256(normalised code)`, and both applications share one database, so the claim is
    checkable here without calling the student app at all: hash what we were given and look
    for a non-revoked invite on this classroom with that hash.

    `canonical_token` must already be normalised the way the student app normalises before
    hashing -- separators stripped, upper-cased -- or a code a child could redeem would be
    rejected here purely for carrying the dashes a teacher reads it with.
    """

    token_hash = hashlib.sha256(canonical_token.encode()).hexdigest()
    stmt = select(classroom_invites.c.classroom_invite_id).where(
        classroom_invites.c.classroom_id == classroom_id,
        classroom_invites.c.token_hash == token_hash,
        classroom_invites.c.revoked_at_utc.is_(None),
    )
    return (await session.execute(stmt)).first() is not None


async def learner_visible_to_teacher(
    session: AsyncSession, teacher_profile_id: uuid.UUID, learner_id: uuid.UUID
) -> bool:
    """True only if the learner is APPROVED in a REAL classroom that this teacher owns.

    This is the cross-tenant check: a learner APPROVED in a DIFFERENT teacher's classroom
    must return False here, not True. Also False for a TEST-fixture learner -- this module's
    student-app readers never surface TEST rows, and this guard does not either.
    """

    stmt = (
        select(classroom_memberships.c.classroom_membership_id)
        .select_from(
            classroom_memberships.join(
                classrooms,
                classroom_memberships.c.classroom_id == classrooms.c.classroom_id,
            ).join(
                b_learners,
                classroom_memberships.c.learner_id == b_learners.c.learner_id,
            )
        )
        .where(
            classroom_memberships.c.learner_id == learner_id,
            classroom_memberships.c.state == APPROVED_STATE,
            classrooms.c.teacher_profile_id == teacher_profile_id,
            classrooms.c.deleted_at_utc.is_(None),
            b_learners.c.source_class == REAL_SOURCE_CLASS,
        )
    )
    return (await session.execute(stmt)).first() is not None
