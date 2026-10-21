"""CompD's teacher side, served by Component 3 (owner direction 2026-10-21: "the teachers dashboard
should be independent even with compD that is a must").

The students dashboard and one student's profiles READ the student app's compD tables through
`data_access` (read-only, REAL learners only). The question bank is Component 3's own
`t3_compd_questions`. AI drafts call Gemini with the dashboard's own key. Nothing here calls the
student app's API, so CompD keeps working whenever the dashboard and the database do.

compD's simpler behaviour is kept: every teacher sees every REAL child (owner Q10) and every
question (one shared bank, Q8); a delete is hard; there is no idempotency key -- a duplicate
`question_code` is the 409.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import compd_maths, data_access
from app.domain.compd import (
    CompdDashboardResponse,
    CompdDrafts,
    CompdDraftRequest,
    CompdMessage,
    CompdProfile,
    CompdProfileStats,
    CompdQuestion,
    CompdQuestionCreate,
    CompdQuestionList,
    CompdQuestionUpdate,
    CompdStudentProfiles,
    CompdStudentSummary,
    with_answer,
)
from app.infrastructure import compd_ai
from app.infrastructure.db.models import CompdQuestionRecord

# The same provenance the other non-pipeline `t3_` tables write (`class_key_service`): a question
# is a teacher's own record, not a pipeline output.
QUESTION_PIPELINE_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
SOURCE_CLASS = "REAL"
SOURCE_SYSTEM = "t3-compd-questions"
PARAMETER_SOURCE_STATUS = "OPERATOR_ASSIGNED"
CODE_INDEX = "uq_t3_compd_questions_question_code"


class CompdNotFoundError(LookupError):
    """An unknown or TEST learner, or an unknown question -- one answer for all of them."""


class CompdConflictError(RuntimeError):
    """Another question already holds this `question_code`."""


class CompdOptionsError(ValueError):
    """The options rule failed on an update's merged question."""


class CompdDraftsUnusableError(RuntimeError):
    """The AI answered, but nothing in it passed the bank's rules."""


# ---------------------------------------------------------------- reads


def _profile(row) -> CompdProfile:
    """The teacher view of one stored profile: the levels as stored, five activity statistics and
    the recommendation built now. The stored confidence value and model version are never read."""

    stored = row.features or {}
    stats = CompdProfileStats(
        accuracy=float(stored.get("accuracy", 0.0)),
        avg_response_time_ms=float(stored.get("avg_response_time_ms", 0.0)),
        retry_rate=float(stored.get("retry_rate", 0.0)),
        hint_rate=float(stored.get("hint_rate", 0.0)),
        total_questions=int(stored.get("total_questions", 0)),
    )
    levels = {
        "memory_level": row.memory_level,
        "attention_level": row.attention_level,
        "number_sense_level": row.number_sense_level,
        "processing_speed_level": row.processing_speed_level,
    }
    return CompdProfile(
        session_id=row.session_id,
        **levels,
        recommendation=compd_maths.recommendation(levels, stats.accuracy, stats.avg_response_time_ms),
        features=stats,
        generated_at=row.generated_at,
    )


def _name_order(learner) -> tuple:
    """By name, case-insensitively; unnamed learners last; the id breaks ties (compD returned them
    unsorted)."""

    return (learner.name is None, (learner.name or "").casefold(), str(learner.learner_id))


def _grade(value) -> str | None:
    return str(value) if value is not None else None


async def dashboard(session: AsyncSession) -> CompdDashboardResponse:
    """compD `GET /teacher/dashboard`. Three queries however many learners there are."""

    learners = sorted(await data_access.compd_learners(session), key=_name_order)
    answers: dict[uuid.UUID, list[compd_maths.Answer]] = defaultdict(list)
    last_seen: dict[uuid.UUID, dt.datetime] = {}
    for row in await data_access.compd_interactions(session):
        answers[row.learner_id].append(
            compd_maths.Answer(
                session_id=row.session_id,
                topic=row.topic,
                response_time_sec=row.response_time_sec,
                attempts=row.attempts,
                response_matched=row.response_matched,
                assist_used=row.assist_used,
            )
        )
        # Rows arrive oldest first, so the last one seen is the newest.
        last_seen[row.learner_id] = row.created_at_utc
    latest = {row.learner_id: _profile(row) for row in await data_access.compd_latest_profiles(session)}

    students = [
        CompdStudentSummary(
            student_id=learner.learner_id,
            name=learner.name,
            grade=_grade(learner.grade),
            classroom_name=learner.classroom_name,
            total_interactions=len(answers.get(learner.learner_id, [])),
            latest_profile=latest.get(learner.learner_id),
            last_activity_date=last_seen.get(learner.learner_id),
            performance=compd_maths.performance(answers.get(learner.learner_id, [])),
        )
        for learner in learners
    ]
    return CompdDashboardResponse(stats=compd_maths.dashboard_stats(students), students=students)


async def student_profiles(session: AsyncSession, learner_id: uuid.UUID, limit: int) -> CompdStudentProfiles:
    """compD's `/profiles/{id}/latest` and `/history`, newest first."""

    learner = await data_access.compd_learner(session, learner_id)
    if learner is None:
        raise CompdNotFoundError()
    rows = await data_access.compd_profile_history(session, learner_id, limit)
    return CompdStudentProfiles(
        student_id=learner.learner_id,
        name=learner.name,
        classroom_name=learner.classroom_name,
        items=[_profile(row) for row in rows],
    )


# ---------------------------------------------------------------- the question bank


def _public(record: CompdQuestionRecord) -> CompdQuestion:
    return CompdQuestion(
        id=record.question_id,
        question_code=record.question_code,
        topic=record.topic,
        difficulty=record.difficulty,
        question_text=record.question_text,
        correct_answer=record.correct_answer,
        options=record.options,
        created_at=record.created_at_utc,
    )


def _is_code_clash(exc: IntegrityError) -> bool:
    """Only a code clash is the 409. Any other integrity failure is a defect and stays a 500."""

    return CODE_INDEX in str(exc.orig)


async def list_questions(
    session: AsyncSession, *, topic: str | None, difficulty: str | None, limit: int
) -> CompdQuestionList:
    """compD `get_questions`: optional exact filters, newest first; the id breaks ties."""

    stmt = select(CompdQuestionRecord)
    if topic is not None:
        stmt = stmt.where(CompdQuestionRecord.topic == topic)
    if difficulty is not None:
        stmt = stmt.where(CompdQuestionRecord.difficulty == difficulty)
    stmt = stmt.order_by(
        CompdQuestionRecord.created_at_utc.desc(), CompdQuestionRecord.question_id.desc()
    ).limit(limit)
    return CompdQuestionList(items=[_public(r) for r in (await session.scalars(stmt))])


async def create_question(
    session: AsyncSession, teacher_profile_id: uuid.UUID, body: CompdQuestionCreate
) -> CompdQuestion:
    """compD `create_question`. The options rule already ran in the request model."""

    record = CompdQuestionRecord(
        question_id=uuid.uuid4(),
        question_code=body.question_code,
        topic=body.topic,
        difficulty=body.difficulty,
        question_text=body.question_text,
        correct_answer=body.correct_answer,
        options=body.options,
        created_by_teacher_profile_id=teacher_profile_id,
        # Set here, not left to the server default, so the response can carry it.
        created_at_utc=dt.datetime.now(dt.timezone.utc),
        source_class=SOURCE_CLASS,
        source_system=SOURCE_SYSTEM,
        parameter_source_status=PARAMETER_SOURCE_STATUS,
        pipeline_run_id=QUESTION_PIPELINE_RUN_ID,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_code_clash(exc):
            raise CompdConflictError() from exc
        raise
    return _public(record)


async def update_question(
    session: AsyncSession, teacher_profile_id: uuid.UUID, question_id: uuid.UUID, body: CompdQuestionUpdate
) -> CompdQuestion:
    """compD `update_question`: only the fields sent, `null` ignored. The options rule runs on the
    MERGED question, so changing only the answer still appends it to the stored options."""

    record = await session.get(CompdQuestionRecord, question_id, with_for_update=True)
    if record is None:
        raise CompdNotFoundError()
    changes = body.model_dump(exclude_none=True)
    if "options" in changes or "correct_answer" in changes:
        try:
            changes["options"] = with_answer(
                changes.get("options", record.options),
                changes.get("correct_answer", record.correct_answer),
            )
        except ValueError as exc:
            raise CompdOptionsError(str(exc)) from exc
    for field, value in changes.items():
        setattr(record, field, value)
    record.updated_by_teacher_profile_id = teacher_profile_id
    record.updated_at_utc = dt.datetime.now(dt.timezone.utc)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_code_clash(exc):
            raise CompdConflictError() from exc
        raise
    return _public(record)


async def delete_question(session: AsyncSession, question_id: uuid.UUID) -> CompdMessage:
    """compD `delete_question`: a HARD delete, as compD's was."""

    record = await session.get(CompdQuestionRecord, question_id, with_for_update=True)
    if record is None:
        raise CompdNotFoundError()
    await session.delete(record)
    await session.commit()
    return CompdMessage(message="Question deleted", id=question_id)


async def draft_questions(
    body: CompdDraftRequest, *, api_key: str | None, transport=None
) -> CompdDrafts:
    """compD `generate_questions_simple`: drafts only, NOTHING saved. Takes no database session,
    so a 30-second wait for the model never holds a pooled connection."""

    text = await compd_ai.request_draft_text(
        api_key=api_key,
        prompt=compd_ai.build_prompt(body.topic, body.difficulty, body.count, body.instructions),
        transport=transport,
    )
    drafts = compd_ai.parse_drafts(text, topic=body.topic, difficulty=body.difficulty, count=body.count)
    if not drafts:
        raise CompdDraftsUnusableError()
    return CompdDrafts(drafts=drafts)
