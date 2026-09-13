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

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.application import data_access
from app.application.decision_layer import EPSILON_PRACTICE
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
from app.domain.sessions import (
    MIN_OBSERVATIONS_FOR_SLOPE,
    ClassReportResponse,
    ClassTrendPoint,
    EarlyWarningPoint,
    GameSession,
    PracticeSession,
    SessionHistoryResponse,
    SessionRecord,
    SkillProgress,
    SkillProgressResponse,
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


@dataclass(frozen=True)
class _PanelSummary:
    """Per-learner series derived from `t3_panel`, for the sparklines and `last_active_date`.

    Nulls inside a series are PRESERVED. A session where Component B recorded nothing is an
    absence, and zero-filling it would draw a 0% accuracy point -- inventing a bad session out
    of a missing one, on a chart a teacher reads as progress.
    """

    last_active_date: dt.date | None = None
    accuracy_sparkline: list[float | None] = field(default_factory=list)
    engagement_sparkline: list[float | None] = field(default_factory=list)


_EMPTY_PANEL = _PanelSummary()


def _panel_summaries(rows: Sequence[Any]) -> dict[uuid.UUID, _PanelSummary]:
    """Group the whole run's panel into one summary per learner, ordered by session.

    Takes the rows rather than a session on purpose: the caller fetches the run ONCE and every
    classroom reuses it. Querying per learner would issue 120 round trips for a six-class
    dashboard, and per classroom would issue six full-run reads.
    """

    by_student: dict[uuid.UUID, list[Any]] = {}
    for row in rows:
        by_student.setdefault(row.student_id, []).append(row)

    summaries: dict[uuid.UUID, _PanelSummary] = {}
    for student_id, learner_rows in by_student.items():
        learner_rows.sort(key=lambda r: r.intervention_session_number)
        dates = [r.intervention_session_date for r in learner_rows if r.intervention_session_date]
        summaries[student_id] = _PanelSummary(
            last_active_date=max(dates) if dates else None,
            accuracy_sparkline=[r.b_accuracy_rate for r in learner_rows],
            engagement_sparkline=[r.c_engagement_score for r in learner_rows],
        )
    return summaries


@dataclass(frozen=True)
class _RunContext:
    """Everything a card needs from the pipeline run, read ONCE per request."""

    latest: dict[uuid.UUID, Any] = field(default_factory=dict)
    panel: dict[uuid.UUID, _PanelSummary] = field(default_factory=dict)


async def _run_context(session: AsyncSession, pipeline_run_id: uuid.UUID) -> _RunContext:
    predictions = await data_access.predictions_for_run(session, pipeline_run_id)
    panel_rows = await data_access.panel_rows_for_run(session, pipeline_run_id)
    return _RunContext(
        latest=_latest_by_student(predictions), panel=_panel_summaries(panel_rows)
    )


def _learner_card(
    row: Any, display_name: str, classroom_id: uuid.UUID, panel: _PanelSummary
) -> LearnerCard:
    return LearnerCard(
        student_id=row.student_id,
        display_name=display_name,
        classroom_id=classroom_id,
        t=row.t,
        evidence_status=row.evidence_status,
        sessions_completed=row.sessions_completed,
        watch_flag=row.watch_flag,
        rank_within_t=row.rank_within_t,
        practice_trajectory=row.practice_trajectory,
        explanation=row.risk_explanation,
        last_active_date=panel.last_active_date,
        accuracy_sparkline=panel.accuracy_sparkline,
        engagement_sparkline=panel.engagement_sparkline,
        model_version=row.model_version,
        inference_timestamp=row.inference_timestamp,
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
    session: AsyncSession,
    classroom_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
    context: _RunContext | None = None,
) -> list[LearnerCard]:
    """`context` is the whole run, read once by the caller. Passing it is what keeps a
    six-class dashboard at one predictions read instead of six."""

    roster = await data_access.classroom_roster(session, classroom_id)
    if not roster:
        return []

    if context is None:
        context = await _run_context(session, pipeline_run_id)
    latest = context.latest

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
                    classroom_id=classroom_id,
                    t=0,
                    evidence_status="insufficient_exposure",
                    sessions_completed=0,
                    watch_flag=False,
                    rank_within_t=None,
                    practice_trajectory="unknown",
                    # Never scored, so there is no model version and no inference time. The
                    # active run's version would be a fabricated provenance claim: it would
                    # name a model that never saw this learner.
                    model_version=None,
                    inference_timestamp=None,
                    last_active_date=context.panel.get(
                        learner.learner_id, _EMPTY_PANEL
                    ).last_active_date,
                )
            )
            continue
        cards.append(
            _learner_card(
                row,
                learner.name,
                classroom_id,
                context.panel.get(learner.learner_id, _EMPTY_PANEL),
            )
        )
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

    # Three reads for the whole page, not three per classroom.
    context = await _run_context(session, run)
    pending = await data_access.pending_request_counts(
        session, [c.classroom_id for c in classrooms]
    )
    teacher_name = await data_access.teacher_display_name(session, teacher_profile_id)

    class_cards: list[ClassCard] = []
    watch_total = 0
    active_total = 0
    getting_started_total = 0

    for classroom in classrooms:
        cards = await _cards_for_classroom(
            session, classroom.classroom_id, run, context
        )
        stats = _stats_for(cards)
        watch_total += stats.watch_count
        active_total += stats.learner_count
        getting_started_total += stats.getting_started_count
        class_cards.append(
            ClassCard(
                classroom_id=classroom.classroom_id,
                name=classroom.name,
                grade=classroom.grade,
                learner_count=stats.learner_count,
                watch_count=stats.watch_count,
                getting_started_count=stats.getting_started_count,
                pending_request_count=pending.get(classroom.classroom_id, 0),
            )
        )

    return HomeSummary(
        teacher_name=teacher_name,
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

    # Name and grade come from the teacher's own classroom list, which is already filtered to
    # REAL. Reusing it keeps one definition of "a classroom this teacher may see".
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)
    this_class = next(
        (c for c in classrooms if c.classroom_id == classroom_id), None
    )
    pending = await data_access.pending_request_counts(session, [classroom_id])

    return CohortResponse(
        classroom_id=classroom_id,
        class_name=None if this_class is None else this_class.name,
        grade=None if this_class is None else this_class.grade,
        pending_request_count=pending.get(classroom_id, 0),
        stats=_stats_for(cards),
        learners=cards,
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
    all_cards = await _cards_for_classroom(session, classroom_id, run)
    flagged = [c for c in all_cards if c.watch_flag]
    # `total_students` is the population the list is drawn from, not the list's own length.
    # A count without its total reads as escalation when it is actually saturation
    # (frontend_plan.md section 1).
    return WatchListResponse(
        classroom_id=classroom_id,
        total_students=len(all_cards),
        learners=_sort_watch_list(flagged),
    )


async def all_classes_watch_list(
    session: AsyncSession, teacher_profile_id: uuid.UUID, *, model_version: str
) -> WatchListResponse:
    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)

    context = await _run_context(session, run)

    cards: list[LearnerCard] = []
    total_students = 0
    for classroom in classrooms:
        classroom_cards = await _cards_for_classroom(
            session, classroom.classroom_id, run, context
        )
        total_students += len(classroom_cards)
        cards.extend(c for c in classroom_cards if c.watch_flag)
    return WatchListResponse(
        classroom_id=None, total_students=total_students, learners=_sort_watch_list(cards)
    )


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

    # `StudentDetail` carries no classroom context of its own, and the student-overview screen
    # has no other source for a class name. Scoped to this teacher so it cannot surface a class
    # the caller could not otherwise see -- `learner_visible_to_teacher` above remains the
    # ownership guard; this is a display read, not a second gate.
    classroom_row = await data_access.classroom_for_learner(
        session, teacher_profile_id, student_id
    )

    return StudentDetail(
        student_id=student_id,
        display_name=roster_name,
        class_name=None if classroom_row is None else classroom_row.name,
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


# ==========================================================================================
# B6.2 -- session history, skill progress and class reports
# ==========================================================================================


def _data_quality(row: Any) -> str:
    """Rule 2 of `app/domain/sessions.py`. A technical fault and a disengaged learner produce
    the same low engagement number and demand opposite responses from a teacher, so the
    distinction is made HERE, once, from the guard columns the panel carries for exactly this
    purpose -- never inferred downstream from the score itself.

    `c_session_technical_issue_flag` is checked FIRST and independently of
    `c_telemetry_quality_status`: migration 0005 added it precisely because the status string
    alone could not separate the two cases.
    """

    if row.c_session_technical_issue_flag:
        return "technical_issue"
    status = (row.c_telemetry_quality_status or "").strip().lower()
    if status and status not in {"ok", "complete", "good"}:
        return "incomplete_telemetry"
    return "ok"


def _practice_session(row: Any) -> PracticeSession | None:
    if not row.b_present:
        return None
    return PracticeSession(
        accuracy_rate=row.b_accuracy_rate,
        total_questions=row.b_total_questions,
        correct_responses=row.b_correct_responses,
        hint_requests=row.b_hint_requests,
        median_item_response_time_sec=row.b_median_item_response_time_sec,
    )


def _game_session(row: Any) -> GameSession | None:
    """Suppresses the engagement and frustration figures when the telemetry is not
    trustworthy, rather than serving them with a caveat.

    A caveat is a field a client can forget to render; a `None` cannot be rendered as a low
    score at all. Making the honest thing the only available thing is the point -- this is
    the one place in the codebase where a technical fault could turn into a claim about a
    child, and it is closed by construction rather than by convention.
    """

    if not row.c_present:
        return None

    quality = _data_quality(row)
    trustworthy = quality == "ok"

    return GameSession(
        accuracy_rate=row.c_accuracy_rate,
        task_completion_rate=row.c_task_completion_rate,
        median_task_latency_sec=row.c_median_game_task_latency_sec,
        engagement_score=row.c_engagement_score if trustworthy else None,
        engagement_components=row.c_engagement_components if trustworthy else None,
        frustration_index=row.c_frustration_index if trustworthy else None,
        frustration_components=row.c_frustration_components if trustworthy else None,
        learner_state=row.c_learner_state,
        current_difficulty_level=row.c_current_difficulty_level,
        difficulty_trend=row.c_difficulty_trend,
        data_quality=quality,
    )


async def session_history(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    student_id: uuid.UUID,
    *,
    model_version: str,
) -> SessionHistoryResponse:
    if not await data_access.learner_visible_to_teacher(
        session, teacher_profile_id, student_id
    ):
        raise LearnerNotVisibleError(str(student_id))

    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    rows = await data_access.session_history_for_student(session, run, student_id)

    return SessionHistoryResponse(
        student_id=student_id,
        display_name=await _display_name_for(session, student_id),
        sessions=[
            SessionRecord(
                session_number=row.intervention_session_number,
                session_date=row.intervention_session_date,
                practice_present=bool(row.b_present),
                games_present=bool(row.c_present),
                practice=_practice_session(row),
                games=_game_session(row),
            )
            for row in rows
        ],
    )


def _skill_direction(slope: float | None, observations: int) -> str:
    """Rule 3. Fewer than four observations means the slope is not reportable -- `unknown`,
    never `stable`. "We cannot tell yet" and "flat" are different claims about a child, and
    collapsing them is how a learner with almost no data comes to look settled.

    The threshold reuses `EPSILON_PRACTICE` from the decision layer rather than inventing a
    second one: the same instrument argument applies, and two epsilons that drift apart would
    let a skill chip and a trajectory chip disagree on screen.
    """

    if observations < MIN_OBSERVATIONS_FOR_SLOPE or slope is None:
        return "unknown"
    if slope > EPSILON_PRACTICE:
        return "improving"
    if slope < -EPSILON_PRACTICE:
        return "needs_attention"
    return "stable"


async def skill_progress(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    student_id: uuid.UUID,
    *,
    model_version: str,
) -> SkillProgressResponse:
    """Direction and practice count per skill. NO mastery value is read, computed or
    returned -- `b_mastery` is not even selected by the reader."""

    if not await data_access.learner_visible_to_teacher(
        session, teacher_profile_id, student_id
    ):
        raise LearnerNotVisibleError(str(student_id))

    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    rows = await data_access.session_history_for_student(session, run, student_id)
    if not rows:
        raise NoPredictionsError(str(student_id))

    latest = rows[-1]
    slopes = latest.b_mastery_slope_w4 or {}
    opportunities = latest.b_opportunities_w4 or {}

    skills = []
    for skill in sorted(set(slopes) | set(opportunities)):
        observations = int(opportunities.get(skill) or 0)
        skills.append(
            SkillProgress(
                skill=skill,
                direction=_skill_direction(slopes.get(skill), observations),
                practice_count=observations,
                relative_level=None,
            )
        )

    return SkillProgressResponse(
        student_id=student_id,
        display_name=await _display_name_for(session, student_id),
        skills=skills,
    )


async def class_report(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    classroom_id: uuid.UUID,
    *,
    model_version: str,
) -> ClassReportResponse:
    """The early-warning curve and the trajectory trend, both computed PER `t`.

    Neither is pooled across `t`. The curve exists to answer "at session 4, how many of this
    class were we flagging?" -- a single pooled flag rate answers nothing, because it is
    dominated by whichever `t` the class is clustered at.
    """

    if not await data_access.teacher_owns_classroom(
        session, teacher_profile_id, classroom_id
    ):
        raise ClassroomNotVisibleError(str(classroom_id))

    run = (
        await data_access.active_pipeline_run(
            session, active_model_version=model_version
        )
    ).pipeline_run_id
    roster = await data_access.classroom_roster(session, classroom_id)
    roster_ids = {learner.learner_id for learner in roster}

    predictions = [
        row
        for row in await data_access.predictions_for_run(session, run)
        if row.student_id in roster_ids
    ]

    by_t: dict[int, list[Any]] = {}
    for row in predictions:
        by_t.setdefault(row.t, []).append(row)

    curve = []
    trend = []
    for t in sorted(by_t):
        rows = by_t[t]
        flagged = sum(1 for r in rows if r.watch_flag)
        curve.append(
            EarlyWarningPoint(
                t=t,
                learners_with_prediction=len(rows),
                watch_flagged=flagged,
                flag_rate=flagged / len(rows),
            )
        )
        trend.append(
            ClassTrendPoint(
                t=t,
                improving=sum(1 for r in rows if r.practice_trajectory == "improving"),
                stable=sum(1 for r in rows if r.practice_trajectory == "stable"),
                needs_attention=sum(
                    1 for r in rows if r.practice_trajectory == "needs_attention"
                ),
                unknown=sum(1 for r in rows if r.practice_trajectory == "unknown"),
            )
        )

    return ClassReportResponse(
        classroom_id=classroom_id,
        learner_count=len(roster_ids),
        early_warning_curve=curve,
        practice_trajectory_trend=trend,
    )
