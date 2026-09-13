"""Recommendation reads and the teacher-decision state machine (work order B7; `docs/13`).

WHAT THIS MODULE DOES
---------------------
* Lists a learner's recommendations for a teacher who may see that learner.
* Moves a recommendation out of ``pending`` -- accept, dismiss or modify -- and writes the
  `t3_recommendation_transitions` log row IN THE SAME TRANSACTION, so a decision without a log
  row cannot be committed (`docs/13` section 6: the log is a research output and must be complete).

WHAT IT MUST NEVER DO
---------------------
* **Create a recommendation.** There is no generator here and there must not be one until the
  ML team rules on the trigger -> action mapping (`dev_docs/QUESTIONS_FOR_ML_TEAM_4.md`).
* **Set `b_applied_at_intervention_session` / `c_applied_at_intervention_session`.** D10: v1 is
  read-only toward Components B and C. Nothing here writes either column, and the ethical-gate
  CHECK would reject a pending/dismissed row that had one.

The database is the final arbiter of the state machine (`ck_t3_reco_transition_from_pending`,
`uq_t3_reco_transition_once`, `ck_t3_reco_modified`). The checks in this module exist to return a
readable 409 before the constraint fires, not to replace it -- and the row is locked `FOR UPDATE`
so two tabs deciding at once cannot both pass the check.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy import null as sql_null
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import data_access
from app.domain.recommendations import (
    ActionOut,
    RecommendationListResponse,
    RecommendationOut,
    TriggerOut,
    filter_evidence,
)
from app.infrastructure.db.models import Panel, Recommendation, RecommendationTransition

Decision = Literal["accepted", "dismissed", "modified"]

#: A teacher's decision is a real act by a real teacher about a real learner.
TRANSITION_SOURCE_CLASS = "REAL"
TRANSITION_SOURCE_SYSTEM = "t3-recommendation-service"
TRANSITION_PARAMETER_SOURCE_STATUS = "TEACHER_DECISION"

ACTIVE_STATUSES = frozenset({"pending", "accepted", "modified"})

_ONCE_CONSTRAINT = "uq_t3_reco_transition_once"


class LearnerNotVisibleError(PermissionError):
    """The caller may not see this learner -- or the recommendation does not exist. The route
    answers both with the same 403 so an id cannot be probed for existence."""


class RecommendationConflictError(RuntimeError):
    """The decision is not legal from the recommendation's current state. `reason` is one of
    `already_decided` or `expired`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _latest_session(
    session: AsyncSession, pipeline_run_id: uuid.UUID, student_id: uuid.UUID
) -> int | None:
    """The learner's most recent intervention session in the run -- the clock expiry is
    measured against. None when the panel holds nothing for them."""

    stmt = select(func.max(Panel.intervention_session_number)).where(
        Panel.pipeline_run_id == pipeline_run_id, Panel.student_id == student_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _is_expired(expires_after_session: int, latest_session: int | None) -> bool:
    """Past `expires_after_session` means no longer the right suggestion (`docs/13` section 2).
    With no known session there is no evidence it has expired, so it has not."""

    return latest_session is not None and latest_session > expires_after_session


def _action(value: Any) -> ActionOut | None:
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        return None
    detail = value.get("detail")
    return ActionOut(kind=value["kind"], detail=detail if isinstance(detail, dict) else {})


def _to_out(row: Recommendation, latest_session: int | None) -> RecommendationOut:
    trigger = row.trigger if isinstance(row.trigger, dict) else {}
    proposed = _action(row.proposed_action) or ActionOut(kind="", detail={})
    return RecommendationOut(
        recommendation_id=row.recommendation_id,
        student_id=row.student_id,
        issued_at_intervention_session=row.issued_at_intervention_session,
        expires_after_session=row.expires_after_session,
        target_component=row.target_component,
        trigger=TriggerOut(
            type=str(trigger.get("type", "")),
            skill=trigger.get("skill") if isinstance(trigger.get("skill"), str) else None,
            evidence=filter_evidence(trigger.get("evidence")),
        ),
        proposed_action=proposed,
        evidence_summary=row.evidence_summary,
        teacher_status=row.teacher_status,
        teacher_modified_action=_action(row.teacher_modified_action),
        b_applied_at_intervention_session=row.b_applied_at_intervention_session,
        c_applied_at_intervention_session=row.c_applied_at_intervention_session,
        expired=_is_expired(row.expires_after_session, latest_session),
    )


async def list_for_student(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    student_id: uuid.UUID,
    *,
    model_version: str,
    status_filter: Literal["active", "all"] = "active",
) -> RecommendationListResponse:
    """Recommendations in the ACTIVE pipeline run only -- a t3_ table, scoped by run, never by
    `source_class` (the provenance rule every t3_ reader follows).

    `active` means pending/accepted/modified AND not expired. `all` returns everything,
    including dismissed and expired, each carrying its `expired` flag.
    """

    if not await data_access.learner_visible_to_teacher(
        session, teacher_profile_id, student_id
    ):
        raise LearnerNotVisibleError(str(student_id))

    run = (
        await data_access.active_pipeline_run(session, active_model_version=model_version)
    ).pipeline_run_id
    latest = await _latest_session(session, run, student_id)

    stmt = (
        select(Recommendation)
        .where(
            Recommendation.pipeline_run_id == run,
            Recommendation.student_id == student_id,
        )
        .order_by(
            Recommendation.issued_at_intervention_session.desc(),
            Recommendation.recommendation_id,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    items = [_to_out(row, latest) for row in rows]
    if status_filter == "active":
        items = [i for i in items if i.teacher_status in ACTIVE_STATUSES and not i.expired]
    return RecommendationListResponse(student_id=student_id, recommendations=items)


async def decide(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    decision: Decision,
    *,
    modified_action: ActionOut | None = None,
    now: dt.datetime | None = None,
) -> RecommendationOut:
    """Move one recommendation out of `pending`, logging the transition atomically.

    Raises `LearnerNotVisibleError` for an unknown id or a learner the teacher cannot see (one
    403 for both), and `RecommendationConflictError` when already decided or expired.
    """

    if (decision == "modified") != (modified_action is not None):
        # A programming error, not a user one: the route builds these arguments.
        raise ValueError("modified_action is required exactly when decision is 'modified'")

    row = (
        await session.execute(
            select(Recommendation)
            .where(Recommendation.recommendation_id == recommendation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if row is None or not await data_access.learner_visible_to_teacher(
        session, teacher_profile_id, row.student_id
    ):
        await session.rollback()
        raise LearnerNotVisibleError(str(recommendation_id))

    if row.teacher_status != "pending":
        await session.rollback()
        raise RecommendationConflictError("already_decided")

    latest = await _latest_session(session, row.pipeline_run_id, row.student_id)
    if _is_expired(row.expires_after_session, latest):
        await session.rollback()
        raise RecommendationConflictError("expired")

    decided_at = now or dt.datetime.now(dt.timezone.utc)
    # `sql_null()`, NOT Python None. On a JSONB column SQLAlchemy writes None as the JSON value
    # `null`, which IS NOT NULL to Postgres -- so an accept would store a "modified action" and
    # `ck_t3_reco_modified` would (correctly) refuse it. Caught by the live suite, not by review.
    modified_json = sql_null() if modified_action is None else modified_action.model_dump()
    trigger = row.trigger if isinstance(row.trigger, dict) else {}

    await session.execute(
        update(Recommendation)
        .where(
            Recommendation.recommendation_id == recommendation_id,
            # Belt and braces with FOR UPDATE: the UPDATE itself only matches a pending row.
            Recommendation.teacher_status == "pending",
        )
        .values(
            teacher_status=decision,
            teacher_modified_action=modified_json,
            decided_at_utc=decided_at,
            updated_at_utc=decided_at,
        )
    )
    session.add(
        RecommendationTransition(
            transition_id=uuid.uuid4(),
            recommendation_id=recommendation_id,
            teacher_profile_id=teacher_profile_id,
            from_status="pending",
            to_status=decision,
            trigger_type=str(trigger["type"]) if trigger.get("type") is not None else None,
            teacher_modified_action=modified_json,
            occurred_at_utc=decided_at,
            source_class=TRANSITION_SOURCE_CLASS,
            source_system=TRANSITION_SOURCE_SYSTEM,
            parameter_source_status=TRANSITION_PARAMETER_SOURCE_STATUS,
            pipeline_run_id=row.pipeline_run_id,
        )
    )
    # One commit for both writes. If the log insert fails, the status change rolls back with it.
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # A concurrent decision that slipped past the lock is caught by the once-per-
        # recommendation constraint, and gets the same answer as the pre-check. ANY OTHER
        # integrity failure is a real fault and propagates -- reporting it as "already decided"
        # would tell a teacher their click landed when nothing was saved.
        if _ONCE_CONSTRAINT in str(getattr(exc, "orig", exc)):
            raise RecommendationConflictError("already_decided") from exc
        raise
    await session.refresh(row)
    return _to_out(row, latest)
