"""CompD against a real database (owner direction 2026-10-21: the dashboard serves compD itself).

Skipped unless `T3_LIVE_DB_URL` names the disposable `upadya_test` database (the same B0.1 guard
as every live test here). Needs the student app's schema in that database too, because the CompD
readers select from its tables and the bank references `teacher_profiles`.

Covers what the offline suite cannot: migration 0013's cycle and constraint names, the readers'
SQL (REAL only, the class join's three "no class" cases, the newest-first history), and the bank's
real constraints (the partial unique code -> 409, `options` NULL stored as SQL NULL, the hard
delete). Ends at `head`, pass or fail. Every row it writes is `source_class = 'TEST'` except the
learners and classrooms the REAL-only readers must see, which carry `source_system = 'pytest'`.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid

import pytest

from tests.test_t3_migration_0008_live import (  # noqa: F401  (pytestmark is re-used)
    _LIVE_URL,
    _alembic_config,
    _database_url_env,
    _table_exists,
    command,
    pytestmark,
)

EXPECTED_CONSTRAINTS = {
    "ck_t3_compd_questions_topic",
    "ck_t3_compd_questions_difficulty",
    "ck_t3_compd_questions_question_text_nonblank",
    "ck_t3_compd_questions_correct_answer_nonblank",
    "ck_t3_compd_questions_options_array",
    "ck_t3_compd_questions_source_class",
    "fk_t3_compd_questions_created_by_teacher_profiles",
    "fk_t3_compd_questions_updated_by_teacher_profiles",
    "pk_t3_compd_questions",
}


@pytest.fixture(autouse=True)
def _restore_head_afterwards():
    try:
        yield
    finally:
        with _database_url_env(_LIVE_URL):
            command.upgrade(_alembic_config(), "head")


def _asyncpg_url() -> str:
    return _LIVE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _fetch(sql: str, *args):
    import asyncpg

    connection = await asyncpg.connect(_asyncpg_url())
    try:
        return await connection.fetch(sql, *args)
    finally:
        await connection.close()


def _constraint_names() -> set[str]:
    rows = asyncio.run(_fetch(
        "SELECT conname FROM pg_constraint WHERE conrelid = 't3_compd_questions'::regclass"
    ))
    return {row["conname"] for row in rows}


def test_migration_0013_cycles_and_names_its_constraints():
    with _database_url_env(_LIVE_URL):
        command.upgrade(_alembic_config(), "head")
        assert _table_exists(_LIVE_URL, "t3_compd_questions")
        assert _constraint_names() == EXPECTED_CONSTRAINTS
        indexes = asyncio.run(_fetch(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 't3_compd_questions'"
        ))
        partial = {r["indexname"]: r["indexdef"] for r in indexes}["uq_t3_compd_questions_question_code"]
        assert "UNIQUE" in partial and "question_code IS NOT NULL" in partial

        command.downgrade(_alembic_config(), "0012_run_scoped_indexes")
        assert not _table_exists(_LIVE_URL, "t3_compd_questions")
        command.upgrade(_alembic_config(), "head")
        assert _table_exists(_LIVE_URL, "t3_compd_questions")


# ---------------------------------------------------------------- seeding the student-app side

_HOST_PROVENANCE = (
    "request_id, operation_or_event_type, reason_code, resource_type, resource_id, "
    "source_class, source_system, environment, schema_revision, system_actor"
)


def _prov(source_class: str) -> tuple:
    return ("req-t3-compd-live", "test.seed", "TEST_FIXTURE", "fixture", uuid.uuid4(),
            source_class, "pytest", "test", "t3-compd-live", "pytest")


async def _seed() -> dict:
    """One teacher; four REAL learners (in this teacher's class; in a deleted class; REMOVED; none)
    and one TEST learner; two runs for the first learner. Returns the ids."""

    import asyncpg

    ids = {k: uuid.uuid4() for k in (
        "user", "teacher", "class_live", "class_deleted", "invite_live", "invite_deleted",
        "amal", "bimal", "chamal", "dinal", "test_learner", "run_old", "run_new",
    )}
    now = dt.datetime.now(dt.timezone.utc)
    c = await asyncpg.connect(_asyncpg_url())
    try:
        async with c.transaction():
            async def insert(table, cols, vals, source_class="TEST"):
                n = len(vals)
                placeholders = ", ".join(f"${i}" for i in range(1, n + 1))
                prov_placeholders = ", ".join(f"${i}" for i in range(n + 1, n + 11))
                await c.execute(
                    f"INSERT INTO {table} ({cols}, {_HOST_PROVENANCE}) VALUES ({placeholders}, {prov_placeholders})",
                    *vals, *_prov(source_class),
                )

            await insert("app_users", "user_id, supabase_subject, status, profile_type",
                         (ids["user"], f"t3-compd-{ids['user']}", "ACTIVE", "TEACHER"))
            await insert("teacher_profiles", "teacher_profile_id, user_id, name",
                         (ids["teacher"], ids["user"], "Live Teacher"))
            for key, name in (("amal", "Amal Live"), ("bimal", "Bimal Live"), ("chamal", "Chamal Live"), ("dinal", "Dinal Live")):
                await insert("b_learners", "learner_id, status, name, grade", (ids[key], "ACTIVE", name, 2), "REAL")
            await insert("b_learners", "learner_id, status, name, grade", (ids["test_learner"], "test_only", "Test Row", 2))
            await insert("classrooms", "classroom_id, teacher_profile_id, name, grade",
                         (ids["class_live"], ids["teacher"], f"Live Class {ids['class_live'].hex[:6]}", "GRADE_2"), "REAL")
            await insert("classrooms", "classroom_id, teacher_profile_id, name, grade, deleted_at_utc, deleted_by_user_id",
                         (ids["class_deleted"], ids["teacher"], None, "GRADE_2", now, ids["user"]), "REAL")
            for invite, room in (("invite_live", "class_live"), ("invite_deleted", "class_deleted")):
                await insert("classroom_invites", "classroom_invite_id, classroom_id, token_hash, created_by_user_id",
                             (ids[invite], ids[room], uuid.uuid4().hex + uuid.uuid4().hex, ids["user"]))
            for learner, room, invite, state in (
                ("amal", "class_live", "invite_live", "APPROVED"),
                ("bimal", "class_deleted", "invite_deleted", "REMOVED"),
                ("chamal", "class_live", "invite_live", "REMOVED"),
            ):
                await insert(
                    "classroom_memberships",
                    "classroom_membership_id, classroom_id, learner_id, classroom_invite_id, state, "
                    "requested_at_utc, decided_at_utc, decided_by_user_id",
                    (uuid.uuid4(), ids[room], ids[learner], ids[invite], state, now, now, ids["user"]),
                )
            for run, when, matched in (("run_old", now - dt.timedelta(days=1), False), ("run_new", now, True)):
                for n, topic in enumerate(("Counting", "Addition", "Subtraction")):
                    await insert(
                        "d_interactions",
                        "d_interaction_id, learner_id, session_id, question_id, topic, difficulty, "
                        "response_time_sec, attempts, response_matched, assist_used, click_count, "
                        "session_time_sec, time_between_actions, error_type, created_at_utc",
                        (uuid.uuid4(), ids["amal"], ids[run], f"q{n}", topic, "Easy", 3.0, 1,
                         matched, False, 1, 30.0, 1.0, "none" if matched else "calculation", when),
                        "REAL",
                    )
                await insert(
                    "d_cognitive_profiles",
                    "d_cognitive_profile_id, learner_id, session_id, memory_level, attention_level, "
                    "number_sense_level, processing_speed_level, confidence_score, model_version, "
                    "features, generated_at",
                    (uuid.uuid4(), ids["amal"], ids[run], "high" if matched else "low", "medium", "medium",
                     "Moderate", 0.7, "rule-based-v2",
                     json.dumps({"accuracy": 1.0 if matched else 0.0, "avg_response_time_ms": 3000.0,
                                 "retry_rate": 0.0, "hint_rate": 0.0, "total_questions": 3}), when),
                    "REAL",
                )
    finally:
        await c.close()
    return ids


async def _with_session(work):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.infrastructure.db_url import normalise_async_url

    engine = create_async_engine(normalise_async_url(_LIVE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            return await work(session)
    finally:
        await engine.dispose()


def test_the_readers_and_the_bank_against_real_tables():
    from app.application import compd_service
    from app.domain.compd import CompdQuestionCreate, CompdQuestionUpdate

    with _database_url_env(_LIVE_URL):
        command.upgrade(_alembic_config(), "head")
    ids = asyncio.run(_seed())

    async def work(session):
        dashboard = await compd_service.dashboard(session)
        by_id = {s.student_id: s for s in dashboard.students}
        assert ids["test_learner"] not in by_id, "a TEST learner is never listed"
        amal = by_id[ids["amal"]]
        assert amal.classroom_name.startswith("Live Class")
        assert by_id[ids["bimal"]].classroom_name is None, "REMOVED from a deleted class"
        assert by_id[ids["chamal"]].classroom_name is None, "REMOVED"
        assert by_id[ids["dinal"]].classroom_name is None, "never in a class"
        assert amal.performance.total_questions == 6 and amal.performance.completed_sessions == 2
        assert amal.latest_profile.memory_level == "high", "the NEWEST profile"
        assert amal.performance.last_topic == "Subtraction", "q2 is last in (created_at, question_id) order"

        history = await compd_service.student_profiles(session, ids["amal"], 20)
        assert [p.session_id for p in history.items] == [ids["run_new"], ids["run_old"]]
        with pytest.raises(compd_service.CompdNotFoundError):
            await compd_service.student_profiles(session, ids["test_learner"], 20)

        code = f"LIVE-{uuid.uuid4().hex[:8]}"
        created = await compd_service.create_question(session, ids["teacher"], CompdQuestionCreate(
            question_code=code, topic="Addition", difficulty="Easy", question_text="2 + 3 = ?",
            correct_answer="5", options=["4", "6"],
        ))
        assert created.options == ["4", "6", "5"]
        no_options = await compd_service.create_question(session, ids["teacher"], CompdQuestionCreate(
            topic="Counting", difficulty="Easy", question_text="Count to 3", correct_answer="3",
        ))
        assert no_options.options is None
        stored = await _fetch("SELECT options IS NULL AS sql_null FROM t3_compd_questions WHERE question_id = $1", no_options.id)
        assert stored[0]["sql_null"], "None is SQL NULL, not the JSON value null"

        with pytest.raises(compd_service.CompdConflictError):
            await compd_service.create_question(session, ids["teacher"], CompdQuestionCreate(
                question_code=code, topic="Addition", difficulty="Easy", question_text="x", correct_answer="1",
                options=["1", "2"],
            ))

        updated = await compd_service.update_question(
            session, ids["teacher"], created.id, CompdQuestionUpdate(correct_answer="9")
        )
        assert updated.options == ["4", "6", "5", "9"]
        listed = await compd_service.list_questions(session, topic="Addition", difficulty=None, limit=100)
        assert created.id in {q.id for q in listed.items}

        await compd_service.delete_question(session, created.id)
        await compd_service.delete_question(session, no_options.id)
        assert not await _fetch("SELECT 1 FROM t3_compd_questions WHERE question_id = $1", created.id), "hard delete"
        with pytest.raises(compd_service.CompdNotFoundError):
            await compd_service.delete_question(session, created.id)

    asyncio.run(_with_session(work))
