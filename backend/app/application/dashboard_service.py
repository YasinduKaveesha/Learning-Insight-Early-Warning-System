"""Dashboard read services (work order B6.1) -- backend_plan.md section 8.

The use-case layer between the thin route handlers and
:mod:`app.application.data_access`. Route handlers parse, delegate and serialise; every
invariant lives here, because several of them are ethical rather than technical and must not
be re-implemented differently in a second endpoint six months from now.

THE INVARIANTS THIS MODULE OWNS
-------------------------------
1. **Latest snapshot per learner, never a carried-forward flag.** A learner's card shows the
   most recent `t` they have a prediction for. If the current snapshot is unavailable, the
   previous one is NOT substituted -- rank correlation decays to ~0 within six sessions and
   is negative across the study, so a stale flag is not a weaker signal, it is a wrong one.
2. **Watch-list order is `(t, rank_within_t)`, never pooled by rank alone.** Ranks are only
   comparable within one `t`. Sorting the whole list by `rank_within_t` would interleave a
   `t=3` rank-1 with a `t=19` rank-1 as though they meant the same thing.
3. **Below the warm-up floor is its own state, not "no concern".** A learner with fewer than
   three sessions is counted in `getting_started_count` and never in `watch_count`. The two
   counts are disjoint and neither absorbs the other.
4. **Ownership is checked before any learner data is read**, via the `data_access` guards,
   which fail closed. A classroom that does not exist and a classroom owned by someone else
   are the same answer here, deliberately -- there is no separate "not found" branch to leak
   the difference.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.application import data_access
from app.domain.dashboard import (
    ClassCard,
    CohortResponse,
    CohortStats,
    HomeSummary,
    LearnerCard,
    SignalOut,
    StudentDetail,
    WatchListResponse,
)

WARMUP_FLOOR = 3


class ClassroomNotVisibleError(PermissionError):
    """The caller does not own this classroom -- or it does not exist. One error for both."""


class LearnerNotVisibleError(PermissionError):
    """The learner is not APPROVED in a classroom this caller owns."""


class NoPredictionsError(LookupError):
    """The learner has no prediction in the active run. Not an error state for the teacher --
    the route turns it into an empty/getting-started shape rather than a 500."""


def _latest_by_student(rows: Sequence[Any]) -> dict[uuid.UUID, Any]:
    """Invariant 1. Keeps the highest `t` per learner and discards the rest."""

    latest: dict[uuid.UUID, Any] = {}
    for row in rows:
        current = latest.get(row.student_id)
        if current is None or row.t > current.t:
            latest[row.student_id] = row
    return latest


def _learner_card(row: Any, display_name: str) -> LearnerCard:
    return LearnerCard(
        student_id=row.student_id,
        display_name=display_name,
        t=row.t,
        evidence_status=row.evidence_status,
        sessions_completed=row.sessions_completed,
        watch_flag=row.watch_flag,
        rank_within_t=row.rank_within_t,
        practice_trajectory=row.practice_trajectory,
    )


def _sort_watch_list(cards: list[LearnerCard]) -> list[LearnerCard]:
    """Invariant 2. Group by `t` descending (the most current snapshots first), and within
    one `t` by `rank_within_t` ascending. Ranks from different `t` values are never compared.
    """

    return sorted(
        cards,
        key=lambda card: (
            -card.t,
            card.rank_within_t if card.rank_within_t is not None else 10**9,
            str(card.student_id),
        ),
    )


async def _cards_for_classroom(
    session: AsyncSession, classroom_id: uuid.UUID, pipeline_run_id: uuid.UUID
) -> list[LearnerCard]:
    roster = await data_access.classroom_roster(session, classroom_id)
    if not roster:
        return []

    predictions = await data_access.predictions_for_run(session, pipeline_run_id)
    latest = _latest_by_student(predictions)

    cards: list[LearnerCard] = []
    for learner in roster:
        row = latest.get(learner.learner_id)
        if row is None:
            # On the roster but not in this run: the demo learner map does not reach them.
            # Shown as getting-started rather than silently dropped, so a teacher's class
            # count and their learner list can never disagree.
            cards.append(
                LearnerCard(
                    student_id=learner.learner_id,
                    display_name=learner.name,
                    t=0,
                    evidence_status="insufficient_exposure",
                    sessions_completed=0,
                    watch_flag=False,
                    rank_within_t=None,
                    practice_trajectory="unknown",
                )
            )
            continue
        cards.append(_learner_card(row, learner.name))
    return cards


def _stats_for(cards: Sequence[LearnerCard]) -> CohortStats:
    """Invariant 3. `watch_count` and `getting_started_count` are disjoint by construction:
    a below-floor learner cannot carry a watch flag (the decision layer forces it false)."""

    return CohortStats(
        learner_count=len(cards),
        watch_count=sum(1 for c in cards if c.watch_flag),
        getting_started_count=sum(
            1 for c in cards if c.sessions_completed < WARMUP_FLOOR
        ),
        improving_count=sum(1 for c in cards if c.practice_trajectory == "improving"),
        needs_attention_count=sum(
            1 for c in cards if c.practice_trajectory == "needs_attention"
        ),
    )


async def home_summary(
    session: AsyncSession, teacher_profile_id: uuid.UUID, *, model_version: str
) -> HomeSummary:
    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)

    class_cards: list[ClassCard] = []
    watch_total = 0
    active_total = 0
    getting_started_total = 0

    for classroom in classrooms:
        cards = await _cards_for_classroom(session, classroom.classroom_id, run)
        stats = _stats_for(cards)
        watch_total += stats.watch_count
        active_total += stats.learner_count
        getting_started_total += stats.getting_started_count
        class_cards.append(
            ClassCard(
                classroom_id=classroom.classroom_id,
                name=classroom.name,
                learner_count=stats.learner_count,
                watch_count=stats.watch_count,
                getting_started_count=stats.getting_started_count,
            )
        )

    return HomeSummary(
        watch_count=watch_total,
        active_students=active_total,
        class_count=len(class_cards),
        getting_started_count=getting_started_total,
        classes=class_cards,
    )


async def cohort(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    classroom_id: uuid.UUID,
    *,
    model_version: str,
) -> CohortResponse:
    if not await data_access.teacher_owns_classroom(
        session, teacher_profile_id, classroom_id
    ):
        raise ClassroomNotVisibleError(str(classroom_id))

    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    cards = await _cards_for_classroom(session, classroom_id, run)
    return CohortResponse(
        classroom_id=classroom_id, stats=_stats_for(cards), learners=cards
    )


async def classroom_watch_list(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    classroom_id: uuid.UUID,
    *,
    model_version: str,
) -> WatchListResponse:
    if not await data_access.teacher_owns_classroom(
        session, teacher_profile_id, classroom_id
    ):
        raise ClassroomNotVisibleError(str(classroom_id))

    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    cards = [c for c in await _cards_for_classroom(session, classroom_id, run) if c.watch_flag]
    return WatchListResponse(classroom_id=classroom_id, learners=_sort_watch_list(cards))


async def all_classes_watch_list(
    session: AsyncSession, teacher_profile_id: uuid.UUID, *, model_version: str
) -> WatchListResponse:
    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)

    cards: list[LearnerCard] = []
    for classroom in classrooms:
        cards.extend(
            c
            for c in await _cards_for_classroom(session, classroom.classroom_id, run)
            if c.watch_flag
        )
    return WatchListResponse(classroom_id=None, learners=_sort_watch_list(cards))


async def student_detail(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    student_id: uuid.UUID,
    *,
    model_version: str,
) -> StudentDetail:
    if not await data_access.learner_visible_to_teacher(
        session, teacher_profile_id, student_id
    ):
        raise LearnerNotVisibleError(str(student_id))

    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    rows = await data_access.predictions_for_run(session, run, student_id=student_id)
    latest = _latest_by_student(rows).get(student_id)
    if latest is None:
        raise NoPredictionsError(str(student_id))

    roster_name = await _display_name_for(session, student_id)

    # `shap_top3` stores the raw feature key alongside the display name; only the display
    # name crosses the wire (filter 3). `SignalOut` forbids extras, so a future change that
    # widens the stored shape cannot leak the key by accident.
    signals = [
        SignalOut(display_name=s["display_name"], direction=s["direction"])
        for s in (latest.shap_top3 or [])
    ]

    return StudentDetail(
        student_id=student_id,
        display_name=roster_name,
        t=latest.t,
        evidence_status=latest.evidence_status,
        sessions_completed=latest.sessions_completed,
        watch_flag=latest.watch_flag,
        rank_within_t=latest.rank_within_t,
        practice_trajectory=latest.practice_trajectory,
        explanation=latest.risk_explanation,
        signals=signals,
    )


async def _display_name_for(session: AsyncSession, learner_id: uuid.UUID) -> str:
    learners = await data_access.real_learners(session, learner_ids=[learner_id])
    return learners[0].name if learners else "Unknown learner"
