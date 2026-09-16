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
from app.application.run_cache import run_cache
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
    ClassReportResponse,
    ClassTrendPoint,
    EarlyWarningPoint,
    GameSession,
    PracticeSession,
    SessionHistoryResponse,
    SessionRecord,
    ParticipationBucket,
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
    #: student_id -> (teacher_status, expires_after_session), open suggestions only.
    handled: dict[uuid.UUID, tuple[str, int]] = field(default_factory=dict)


async def _run_context(
    session: AsyncSession,
    pipeline_run_id: uuid.UUID,
    *,
    student_ids: Sequence[uuid.UUID] | None = None,
) -> _RunContext:
    """The run data a page of cards needs.

    Predictions and the panel are the run's IMMUTABLE data, served from `run_cache` and then
    narrowed in memory to `student_ids` -- the learners the page shows, taken from a roster the
    caller has already read under an ownership check. `None` means the whole run.

    Suggestion status is read LIVE: a teacher's decision must show on the next request, and the
    watch count depends on it."""

    wanted = None if student_ids is None else set(student_ids)
    predictions = [
        row
        for row in await run_cache.predictions(session, pipeline_run_id)
        if wanted is None or row.student_id in wanted
    ]
    panel_rows = [
        row
        for row in await run_cache.panel(session, pipeline_run_id)
        if wanted is None or row.student_id in wanted
    ]
    handled = await data_access.handled_suggestions_for_run(session, pipeline_run_id)
    return _RunContext(
        latest=_latest_by_student(predictions),
        panel=_panel_summaries(panel_rows),
        handled=handled,
    )


def _suggestion_status(context: _RunContext, student_id: uuid.UUID, current_t: int) -> str | None:
    """Decision B. Handled only while the suggestion is still live: past its
    `expires_after_session` it no longer counts even before the generator writes the closure,
    so a still-flagged child returns to the watch list on time (D47's "keep the guards")."""

    entry = context.handled.get(student_id)
    if entry is None:
        return None
    status, expires_after_session = entry
    return None if current_t > expires_after_session else status


def _learner_card(
    row: Any,
    display_name: str,
    classroom_id: uuid.UUID,
    panel: _PanelSummary,
    suggestion_status: str | None = None,
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
        # Absent when the caller asked for the narrow projection (see `_run_context`); those
        # callers count cards rather than render them.
        explanation=getattr(row, "risk_explanation", None),
        last_active_date=panel.last_active_date,
        accuracy_sparkline=panel.accuracy_sparkline,
        engagement_sparkline=panel.engagement_sparkline,
        model_version=row.model_version,
        inference_timestamp=row.inference_timestamp,
        suggestion_status=suggestion_status,
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


def _cards_from_roster(
    roster: Sequence[Any], classroom_id: uuid.UUID, context: _RunContext
) -> list[LearnerCard]:
    """The card-building half of `_cards_for_classroom`, with the roster already in hand.

    Split out so `/home` can read every class's roster in one query and still build cards the
    same way -- identical rules, including the not-in-this-run case below.
    """

    cards: list[LearnerCard] = []
    for learner in roster:
        row = context.latest.get(learner.learner_id)
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
                _suggestion_status(context, learner.learner_id, row.t),
            )
        )
    return cards


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
        context = await _run_context(
            session, pipeline_run_id, student_ids=[l.learner_id for l in roster]
        )
    return _cards_from_roster(roster, classroom_id, context)


def _stats_for(cards: Sequence[LearnerCard]) -> CohortStats:
    """Invariant 3. `watch_count` and `getting_started_count` are disjoint by construction:
    a below-floor learner cannot carry a watch flag (the decision layer forces it false)."""

    return CohortStats(
        learner_count=len(cards),
        watch_count=sum(1 for c in cards if c.watch_flag),
        # A subset of watch_count, never subtracted from it (decision B).
        handled_count=sum(1 for c in cards if c.watch_flag and c.suggestion_status),
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
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)

    # One roster read for every class, not one per class.
    roster_rows = await data_access.rosters_for_classrooms(
        session, [c.classroom_id for c in classrooms]
    )
    rosters: dict[uuid.UUID, list[Any]] = {}
    for row in roster_rows:
        rosters.setdefault(row.classroom_id, []).append(row)

    # Three reads for the whole page, scoped to this teacher's learners. No explanations:
    # this page counts cards, it never renders one.
    context = await _run_context(
        session, run, student_ids=[r.learner_id for r in roster_rows]
    )
    pending = await data_access.pending_request_counts(
        session, [c.classroom_id for c in classrooms]
    )
    teacher_name = await data_access.teacher_display_name(session, teacher_profile_id)

    class_cards: list[ClassCard] = []
    watch_total = 0
    active_total = 0
    getting_started_total = 0

    for classroom in classrooms:
        cards = _cards_from_roster(
            rosters.get(classroom.classroom_id, []), classroom.classroom_id, context
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
                handled_count=stats.handled_count,
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
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    cards = await _cards_for_classroom(session, classroom_id, run)

    # Name and grade come from the teacher's own classroom list, which is already filtered to
    # REAL. Reusing it keeps one definition of "a classroom this teacher may see".
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)
    this_class = next(
        (c for c in classrooms if c.classroom_id == classroom_id), None
    )
    pending = await data_access.pending_request_counts(session, [classroom_id])
    # Absent from the mapping => no key has ever been minted for this classroom. Do not
    # mint one here: this is a GET, and a read that writes is a side effect someone will
    # trip over. D1 calls the key permanent, which argues for creating it once, explicitly.
    keys = await data_access.class_keys_for_classrooms(session, [classroom_id])

    return CohortResponse(
        classroom_id=classroom_id,
        class_name=None if this_class is None else this_class.name,
        grade=None if this_class is None else this_class.grade,
        class_key=keys.get(classroom_id),
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
        await run_cache.active_run(session, model_version=model_version)
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
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)

    # One roster read for every class, then one context scoped to those learners -- the same
    # shape as `/home`, for the same reason.
    roster_rows = await data_access.rosters_for_classrooms(
        session, [c.classroom_id for c in classrooms]
    )
    rosters: dict[uuid.UUID, list[Any]] = {}
    for row in roster_rows:
        rosters.setdefault(row.classroom_id, []).append(row)
    context = await _run_context(
        session, run, student_ids=[r.learner_id for r in roster_rows]
    )

    cards: list[LearnerCard] = []
    total_students = 0
    for classroom in classrooms:
        classroom_cards = _cards_from_roster(
            rosters.get(classroom.classroom_id, []), classroom.classroom_id, context
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
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    if run_cache.has_predictions(run):
        rows = [
            row
            for row in await run_cache.predictions(session, run)
            if row.student_id == student_id
        ]
    else:
        # A cold cache: one learner's rows, rather than loading the whole run to open one page.
        rows = await data_access.predictions_for_run(session, run, student_id=student_id)
    latest = _latest_by_student(rows).get(student_id)
    roster_name = await _display_name_for(session, student_id)

    if latest is None:
        # On the teacher's roster, not in this run -- a child who just joined, or one the demo
        # map does not reach. `_cards_for_classroom` ALREADY shows them, as getting-started, so
        # 404 here made the same learner two different answers: present in the class list,
        # "couldn't load this student" when opened. Found on the first real join, 2026-09-14.
        #
        # This is not the empty 200 the route's 404 exists to prevent. That warning is about a
        # learner who looks *judged and fine*; this reply carries `insufficient_exposure`, so
        # every screen renders Getting Started -- "we cannot tell yet", which is the truth.
        classroom_row = await data_access.classroom_for_learner(
            session, teacher_profile_id, student_id
        )
        return _getting_started_detail(
            student_id,
            roster_name,
            None if classroom_row is None else classroom_row.classroom_id,
            None if classroom_row is None else classroom_row.name,
        )

    # `StudentDetail` carries no classroom context of its own, and the student-overview screen
    # has no other source for a class name. Scoped to this teacher so it cannot surface a class
    # the caller could not otherwise see -- `learner_visible_to_teacher` above remains the
    # ownership guard; this is a display read, not a second gate.
    classroom_row = await data_access.classroom_for_learner(
        session, teacher_profile_id, student_id
    )

    return _detail_from(
        student_id,
        roster_name,
        None if classroom_row is None else classroom_row.classroom_id,
        None if classroom_row is None else classroom_row.name,
        latest,
    )


def _detail_from(
    student_id: uuid.UUID,
    display_name: str,
    classroom_id: uuid.UUID | None,
    class_name: str | None,
    latest: Any,
) -> StudentDetail:
    """A scored learner's `StudentDetail`, from their latest prediction row. Shared by the
    single-learner endpoint and the class overview, so the two cannot describe one learner
    differently."""

    # `shap_top3` stores the raw feature key alongside the display name; only the display
    # name crosses the wire (filter 3). `SignalOut` forbids extras, so a future change that
    # widens the stored shape cannot leak the key by accident.
    signals = [
        SignalOut(display_name=s["display_name"], direction=s["direction"])
        for s in (latest.shap_top3 or [])
    ]
    return StudentDetail(
        student_id=student_id,
        display_name=display_name,
        classroom_id=classroom_id,
        class_name=class_name,
        t=latest.t,
        evidence_status=latest.evidence_status,
        sessions_completed=latest.sessions_completed,
        watch_flag=latest.watch_flag,
        rank_within_t=latest.rank_within_t,
        practice_trajectory=latest.practice_trajectory,
        explanation=latest.risk_explanation,
        signals=signals,
    )


def _getting_started_detail(
    student_id: uuid.UUID,
    display_name: str,
    classroom_id: uuid.UUID | None,
    class_name: str | None,
) -> StudentDetail:
    """A learner on a roster but not in the run: `insufficient_exposure`, which every screen
    renders as Getting Started -- "we cannot tell yet", never "no concern"."""

    return StudentDetail(
        student_id=student_id,
        display_name=display_name,
        classroom_id=classroom_id,
        class_name=class_name,
        t=0,
        evidence_status="insufficient_exposure",
        sessions_completed=0,
        watch_flag=False,
        rank_within_t=None,
        practice_trajectory="unknown",
        explanation=None,
        signals=[],
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
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    rows = await run_cache.history_for_student(session, run, student_id)

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


#: D38 (ML team ruling, ANSWERS_TO_APP_TEAM_4 section 6.1). The skill chip used to apply
#: `EPSILON_PRACTICE` to `b_mastery_slope_w4`. That threshold was derived in D11 for
#: `b_accuracy_rate` -- a 2-4-item ratio -- and on a BKT mastery slope (cohort median +0.031 per
#: session) it read 76.1% of practised skills as "stable" and 0.24% as "needs attention": a chip
#: that almost never says a skill is not progressing. Until the chip is re-specified on the D35
#: stagnation definition and has had its own D16 check, direction is WITHHELD for every skill.
#: `unknown` is the honest value: the client already renders it without a bar or a verdict.
SKILL_DIRECTION_WITHHELD: str = "unknown"


def _mastery_level(value: Any) -> float | None:
    """D42. Two decimals: the underlying posterior is uncalibrated, and more digits would claim
    a precision it does not have. Anything missing, non-numeric or outside [0, 1] is None --
    no bar -- rather than a clamped value that looks like a measurement."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0.0 <= float(value) <= 1.0:
        return None
    return round(float(value), 2)


def _ever_practised(rows: Sequence[Any]) -> set[str]:
    """D46 (ML team, ANSWERS_TO_APP_TEAM_5 Q4): the skills with at least one opportunity in ANY
    panel row up to the learner's current session.

    Every practised session appears in at least one trailing `w = 4` window, so "zero in every
    window so far" is exactly "never practised". Implemented on OPPORTUNITIES, never on the value
    test `mastery == 0.15`: 0.15 is a fixture parameter that real BKT settings will change, and
    float equality on a posterior is fragile. The ML team measured the two as equivalent on
    13,084 of 13,084 cohort skill-sessions; reproduced here on the demo, 9,324 of 9,324.
    """

    practised: set[str] = set()
    for row in rows:
        for skill, count in (getattr(row, "b_opportunities_w4", None) or {}).items():
            if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0:
                practised.add(skill)
    return practised


async def skill_progress(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    student_id: uuid.UUID,
    *,
    model_version: str,
) -> SkillProgressResponse:
    """Direction (withheld, D38), practice count, and the latest mastery value for the bar
    (D42). The mastery value is served only here, only as `mastery_level`, rounded."""

    if not await data_access.learner_visible_to_teacher(
        session, teacher_profile_id, student_id
    ):
        raise LearnerNotVisibleError(str(student_id))

    run = (
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    rows = await run_cache.history_for_student(session, run, student_id)
    return _skills_from(student_id, await _display_name_for(session, student_id), rows)


def _skills_from(
    student_id: uuid.UUID, display_name: str, rows: Sequence[Any]
) -> SkillProgressResponse:
    """Skill progress from one learner's session history, oldest first. Shared by the
    single-learner endpoint and the class overview."""

    if not rows:
        # A child who has not practised yet has no skills to report -- that is an empty list,
        # not a failure. 404 here took down the whole student screen (the client fetches the
        # detail and the skills together), so a brand-new learner rendered as "couldn't load
        # this student" instead of Getting Started. The sessions route already answers an empty
        # history with 200; this now matches it.
        return SkillProgressResponse(student_id=student_id, display_name=display_name, skills=[])

    latest = rows[-1]
    slopes = latest.b_mastery_slope_w4 or {}
    opportunities = latest.b_opportunities_w4 or {}
    mastery = getattr(latest, "b_mastery", None) or {}
    practised = _ever_practised(rows)

    skills = []
    for skill in sorted(set(slopes) | set(opportunities) | set(mastery)):
        observations = int(opportunities.get(skill) or 0)
        never_practised = skill not in practised  # D46
        skills.append(
            SkillProgress(
                skill=skill,
                direction=SKILL_DIRECTION_WITHHELD,  # D38
                practice_count=observations,
                relative_level=None,
                # D46: a never-practised skill has NO measurement -- its stored value is the
                # model's starting prior. Serving the level would draw the shortest bar on the
                # screen for a skill that was simply never tested.
                mastery_level=(
                    None if never_practised else _mastery_level(mastery.get(skill))
                ),
                never_practised=never_practised,
            )
        )

    return SkillProgressResponse(
        student_id=student_id, display_name=display_name, skills=skills
    )


#: Bands for the participation histogram. Chosen around D6's warm-up floor of three sessions
#: rather than as even arithmetic ranges: "below the floor" is a state the product already
#: treats as distinct, so the first band means something a teacher can act on. The upper bands
#: are even so the shape is not an artefact of the bucketing.
PARTICIPATION_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("Fewer than 3 sessions", 0, 2),
    ("3-5 sessions", 3, 5),
    ("6-10 sessions", 6, 10),
    ("11-15 sessions", 11, 15),
    ("16+ sessions", 16, 10**6),
)


def _participation(sessions_completed: Sequence[int]) -> list[ParticipationBucket]:
    """Bucket learners by sessions completed, keeping empty bands."""

    return [
        ParticipationBucket(
            bucket_label=label,
            student_count=sum(1 for n in sessions_completed if low <= n <= high),
        )
        for label, low, high in PARTICIPATION_BUCKETS
    ]


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
        await run_cache.active_run(session, model_version=model_version)
    ).pipeline_run_id
    roster = await data_access.classroom_roster(session, classroom_id)
    roster_ids = {learner.learner_id for learner in roster}

    predictions = [
        row
        for row in await run_cache.predictions(session, run)
        if row.student_id in roster_ids
    ]

    # The histogram counts LEARNERS, so it uses each learner's latest snapshot -- not every
    # prediction row, which would count a learner once per session and turn a class of 20 into
    # a bar chart of 606.
    latest = _latest_by_student(predictions)
    participation = _participation([row.sessions_completed for row in latest.values()])

    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)
    this_class = next((c for c in classrooms if c.classroom_id == classroom_id), None)

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
        class_name=None if this_class is None else this_class.name,
        participation=participation,
        learner_count=len(roster_ids),
        early_warning_curve=curve,
        practice_trajectory_trend=trend,
    )


async def class_student_overviews(
    session: AsyncSession,
    teacher_profile_id: uuid.UUID,
    classroom_id: uuid.UUID,
    *,
    model_version: str,
) -> "ClassStudentOverviewsResponse":
    """Every learner's student screen for one class, in one response (2026-09-16).

    Same ownership rule as the single-learner endpoints, decided ONCE: the teacher must own the
    class, and a learner appears only if APPROVED on its roster -- which is precisely what
    `learner_visible_to_teacher` answers per learner. Every part of each overview is built by
    the same builder the single-learner endpoint uses.

    Reads: the class check, the roster, the class name, and the class's suggestions are live;
    predictions and session history come from `run_cache` (one query for the whole class when
    cold).
    """

    from app.application import recommendation_service
    from app.domain.overviews import ClassStudentOverviewsResponse, StudentOverviewOut

    if not await data_access.teacher_owns_classroom(session, teacher_profile_id, classroom_id):
        raise ClassroomNotVisibleError(str(classroom_id))

    run = (await run_cache.active_run(session, model_version=model_version)).pipeline_run_id
    roster = await data_access.classroom_roster(session, classroom_id)
    student_ids = [learner.learner_id for learner in roster]

    classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)
    this_class = next((c for c in classrooms if c.classroom_id == classroom_id), None)
    class_name = None if this_class is None else this_class.name

    wanted = set(student_ids)
    latest = _latest_by_student(
        [row for row in await run_cache.predictions(session, run) if row.student_id in wanted]
    )
    histories = await run_cache.history_for_students(session, run, student_ids)
    latest_sessions = {
        sid: (rows[-1].intervention_session_number if rows else None)
        for sid, rows in histories.items()
    }
    suggestions = await recommendation_service.active_for_students(
        session, run, student_ids, latest_sessions
    )

    students = []
    for learner in roster:
        sid = learner.learner_id
        row = latest.get(sid)
        detail = (
            _getting_started_detail(sid, learner.name, classroom_id, class_name)
            if row is None
            else _detail_from(sid, learner.name, classroom_id, class_name, row)
        )
        students.append(
            StudentOverviewOut(
                detail=detail,
                skills=_skills_from(sid, learner.name, histories.get(sid, [])),
                recommendations=suggestions[sid],
            )
        )
    return ClassStudentOverviewsResponse(classroom_id=classroom_id, students=students)
