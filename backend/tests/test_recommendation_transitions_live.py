"""The recommendation state machine against the REAL database (work order B7, migration 0009).

`tests/test_recommendations_api.py` pins the HTTP mapping with the service stubbed. This module
pins what a stub cannot: that the constraints exist and fire, that a decision and its log row
commit together or not at all, and that the write-back columns stay NULL (D10).

Every gate here is a committed test that RUNS when `T3_LIVE_DB_URL` is set. The service commits,
so rows cannot be rolled back; each test creates its own `TEST`-provenance pipeline run and
recommendation and deletes them in teardown.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest

pytest.importorskip("asyncpg")
pytest.importorskip("sqlalchemy")

import asyncpg  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.application import data_access, recommendation_service  # noqa: E402
from app.domain.recommendations import ActionOut  # noqa: E402
from app.infrastructure.db_url import normalise_async_url  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct Postgres URL to run the live B7 state-machine gates",
)

_PROV = ("TEST", "b7_live", "TEST_FIXTURE_ONLY")
TEACHER = uuid.UUID("aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa")


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _run(coro):
    return asyncio.run(coro)


async def _seed(conn: asyncpg.Connection, *, trigger_type: str | None = "stagnation") -> tuple:
    learner = await conn.fetchval("select learner_id from b_learners limit 1")
    if learner is None:
        pytest.skip("no b_learners row to attach a recommendation to")
    run = uuid.uuid4()
    await conn.execute(
        "insert into t3_pipeline_runs (pipeline_run_id, dataset_manifest, model_version, "
        "source_class, source_system, parameter_source_status) values ($1,$2,$3,$4,$5,$6)",
        run, json.dumps({"seed": "b7-live"}), "b7-live", *_PROV,
    )
    reco = uuid.uuid4()
    trigger = {"evidence": {"opportunities_w4": 12}}
    if trigger_type is not None:
        trigger["type"] = trigger_type
    # A fresh student_id is not available, and uq_t3_reco_active allows one active
    # recommendation per (student, target). Use a target no fixture uses for this learner.
    await conn.execute(
        "delete from t3_recommendations where student_id=$1 and target_component='both' "
        "and source_system=$2",
        learner, _PROV[1],
    )
    await conn.execute(
        "insert into t3_recommendations (recommendation_id, student_id, "
        "issued_at_intervention_session, expires_after_session, target_component, trigger, "
        "proposed_action, evidence_summary, teacher_status, pipeline_run_id, source_class, "
        "source_system, parameter_source_status) "
        "values ($1,$2,3,8,'both',$3,$4,'s','pending',$5,$6,$7,$8)",
        reco, learner, json.dumps(trigger),
        json.dumps({"kind": "practice", "detail": {"skill": "subtraction"}}), run, *_PROV,
    )
    return learner, run, reco


async def _cleanup(conn: asyncpg.Connection, run: uuid.UUID, reco: uuid.UUID) -> None:
    await conn.execute("delete from t3_recommendation_transitions where recommendation_id=$1", reco)
    await conn.execute("delete from t3_recommendations where recommendation_id=$1", reco)
    await conn.execute("delete from t3_pipeline_runs where pipeline_run_id=$1", run)


async def _with_service(monkeypatch, body):
    """Seed, run `body(session, learner, run, reco, conn)`, always clean up.

    Visibility is stubbed to True: `learner_visible_to_teacher` has its own live gates in
    `test_data_access_live.py`, and this module is about the state machine, not ownership.
    """

    async def _visible(_session, _teacher, _learner):
        return True

    monkeypatch.setattr(data_access, "learner_visible_to_teacher", _visible)

    conn = await asyncpg.connect(_plain(_LIVE_URL))
    engine = create_async_engine(normalise_async_url(_LIVE_URL))
    learner, run, reco = await _seed(conn)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await body(session, learner, run, reco, conn)
    finally:
        await _cleanup(conn, run, reco)
        await conn.close()
        await engine.dispose()


async def _insert_second(conn: asyncpg.Connection, learner, run) -> None:
    """A second `both`-targeted suggestion for the same learner -- what uq_t3_reco_active
    permits or refuses."""

    await conn.execute(
        "insert into t3_recommendations (recommendation_id, student_id, "
        "issued_at_intervention_session, expires_after_session, target_component, trigger, "
        "proposed_action, evidence_summary, teacher_status, pipeline_run_id, source_class, "
        "source_system, parameter_source_status) "
        "values ($1,$2,9,14,'both',$3,$4,'s','pending',$5,$6,$7,$8)",
        uuid.uuid4(), learner, json.dumps({"type": "watch_flag", "evidence": {}}),
        json.dumps({"kind": "monitor_progress", "detail": {}}), run, *_PROV,
    )


# --- the service, end to end ------------------------------------------------------------


def test_accept_changes_status_and_logs_exactly_one_transition(monkeypatch):
    async def body(session, learner, run, reco, conn):
        out = await recommendation_service.decide(session, TEACHER, reco, "accepted")
        assert out.teacher_status == "accepted"

        row = await conn.fetchrow(
            "select teacher_status, decided_at_utc, b_applied_at_intervention_session b, "
            "c_applied_at_intervention_session c from t3_recommendations "
            "where recommendation_id=$1",
            reco,
        )
        assert row["teacher_status"] == "accepted"
        assert row["decided_at_utc"] is not None
        # D10: a decision never populates write-back.
        assert row["b"] is None and row["c"] is None

        log = await conn.fetch(
            "select from_status, to_status, trigger_type, teacher_profile_id, "
            "teacher_modified_action, pipeline_run_id from t3_recommendation_transitions "
            "where recommendation_id=$1",
            reco,
        )
        assert len(log) == 1
        assert (log[0]["from_status"], log[0]["to_status"]) == ("pending", "accepted")
        assert log[0]["trigger_type"] == "stagnation"
        assert log[0]["teacher_profile_id"] == TEACHER
        assert log[0]["teacher_modified_action"] is None
        assert log[0]["pipeline_run_id"] == run

    _run(_with_service(monkeypatch, body))


def test_modify_stores_the_teachers_action_on_both_rows(monkeypatch):
    async def body(session, learner, run, reco, conn):
        action = ActionOut(kind="review", detail={"skill": "place_value"})
        out = await recommendation_service.decide(
            session, TEACHER, reco, "modified", modified_action=action
        )
        assert out.teacher_modified_action == action
        stored = await conn.fetchval(
            "select teacher_modified_action from t3_recommendations where recommendation_id=$1",
            reco,
        )
        logged = await conn.fetchval(
            "select teacher_modified_action from t3_recommendation_transitions "
            "where recommendation_id=$1",
            reco,
        )
        assert json.loads(stored) == json.loads(logged) == {
            "kind": "review",
            "detail": {"skill": "place_value"},
        }

    _run(_with_service(monkeypatch, body))


def test_a_second_decision_is_refused_and_logs_nothing(monkeypatch):
    async def body(session, learner, run, reco, conn):
        await recommendation_service.decide(session, TEACHER, reco, "dismissed")
        with pytest.raises(recommendation_service.RecommendationConflictError) as caught:
            await recommendation_service.decide(session, TEACHER, reco, "accepted")
        assert caught.value.reason == "already_decided"
        assert await conn.fetchval(
            "select teacher_status from t3_recommendations where recommendation_id=$1", reco
        ) == "dismissed"
        assert await conn.fetchval(
            "select count(*) from t3_recommendation_transitions where recommendation_id=$1", reco
        ) == 1

    _run(_with_service(monkeypatch, body))


def test_an_expired_recommendation_cannot_be_decided(monkeypatch):
    async def body(session, learner, run, reco, conn):
        async def _late(_session, _run, _student):
            return 9  # expires_after_session is 8

        monkeypatch.setattr(recommendation_service, "_latest_session", _late)
        with pytest.raises(recommendation_service.RecommendationConflictError) as caught:
            await recommendation_service.decide(session, TEACHER, reco, "accepted")
        assert caught.value.reason == "expired"
        assert await conn.fetchval(
            "select teacher_status from t3_recommendations where recommendation_id=$1", reco
        ) == "pending"

    _run(_with_service(monkeypatch, body))


def test_a_closed_suggestion_cannot_be_decided(monkeypatch):
    """D47: closure ends the active period, so the teacher actions refuse it -- even though the
    learner's session (unknown here) would not, by itself, make it expired."""

    async def body(session, learner, run, reco, conn):
        await conn.execute(
            "update t3_recommendations set closed_at_session=9, closed_at_utc=now() "
            "where recommendation_id=$1",
            reco,
        )
        with pytest.raises(recommendation_service.RecommendationConflictError) as caught:
            await recommendation_service.decide(session, TEACHER, reco, "accepted")
        assert caught.value.reason == "expired"
        assert await conn.fetchval(
            "select teacher_status from t3_recommendations where recommendation_id=$1", reco
        ) == "pending"

    _run(_with_service(monkeypatch, body))


def test_an_unknown_recommendation_is_not_visible(monkeypatch):
    async def body(session, learner, run, reco, conn):
        with pytest.raises(recommendation_service.LearnerNotVisibleError):
            await recommendation_service.decide(session, TEACHER, uuid.uuid4(), "accepted")

    _run(_with_service(monkeypatch, body))


def test_status_and_log_commit_together_or_not_at_all(monkeypatch):
    """Atomicity. Force the LOG insert to violate a constraint; the status change must roll
    back with it, and the fault must propagate rather than read as 'already decided'."""

    async def body(session, learner, run, reco, conn):
        monkeypatch.setattr(recommendation_service, "TRANSITION_SOURCE_CLASS", "NOT_A_CLASS")
        with pytest.raises(IntegrityError):
            await recommendation_service.decide(session, TEACHER, reco, "accepted")
        assert await conn.fetchval(
            "select teacher_status from t3_recommendations where recommendation_id=$1", reco
        ) == "pending"
        assert await conn.fetchval(
            "select count(*) from t3_recommendation_transitions where recommendation_id=$1", reco
        ) == 0

    _run(_with_service(monkeypatch, body))


def test_latest_session_reader_executes_against_the_real_schema():
    async def go():
        engine = create_async_engine(normalise_async_url(_LIVE_URL))
        try:
            async with async_sessionmaker(engine)() as session:
                assert await recommendation_service._latest_session(
                    session, uuid.UUID(int=0), uuid.UUID(int=0)
                ) is None
        finally:
            await engine.dispose()

    _run(go())


# --- the constraints themselves, independent of the service ------------------------------


@pytest.mark.parametrize(
    "from_status, to_status, modified, constraint",
    [
        ("accepted", "dismissed", None, "ck_t3_reco_transition_from_pending"),
        ("pending", "pending", None, "ck_t3_reco_transition_to_status"),
        ("pending", "modified", None, "ck_t3_reco_transition_modified"),
        ("pending", "accepted", {"kind": "x"}, "ck_t3_reco_transition_modified"),
    ],
)
def test_transition_check_constraints(from_status, to_status, modified, constraint):
    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            _learner, run, reco = await _seed(conn)
            with pytest.raises(asyncpg.exceptions.CheckViolationError) as caught:
                await conn.execute(
                    "insert into t3_recommendation_transitions (transition_id, "
                    "recommendation_id, teacher_profile_id, from_status, to_status, "
                    "teacher_modified_action, source_class, source_system, "
                    "parameter_source_status, pipeline_run_id) "
                    "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                    uuid.uuid4(), reco, TEACHER, from_status, to_status,
                    None if modified is None else json.dumps(modified), *_PROV, run,
                )
            assert caught.value.constraint_name == constraint
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())


def test_one_transition_per_recommendation_is_a_database_rule():
    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            _learner, run, reco = await _seed(conn)
            insert = (
                "insert into t3_recommendation_transitions (transition_id, recommendation_id, "
                "teacher_profile_id, from_status, to_status, source_class, source_system, "
                "parameter_source_status, pipeline_run_id) "
                "values ($1,$2,$3,'pending',$4,$5,$6,$7,$8)"
            )
            await conn.execute(insert, uuid.uuid4(), reco, TEACHER, "accepted", *_PROV, run)
            with pytest.raises(asyncpg.exceptions.UniqueViolationError) as caught:
                await conn.execute(insert, uuid.uuid4(), reco, TEACHER, "dismissed", *_PROV, run)
            assert caught.value.constraint_name == "uq_t3_reco_transition_once"
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())

# --- D47: expiry closure ------------------------------------------------------------------


def _closure_sql() -> str:
    return (
        "insert into t3_recommendation_transitions (transition_id, recommendation_id, "
        "teacher_profile_id, event_type, from_status, to_status, source_class, source_system, "
        "parameter_source_status, pipeline_run_id) values ($1,$2,$3,'expiry_closure',$4,$5,$6,$7,$8,$9)"
    )


@pytest.mark.parametrize(
    "from_status, to_status, teacher, constraint",
    [
        # Rule 2 as a DATABASE rule: a closure may not rewrite the teacher's decision.
        ("accepted", "dismissed", None, "ck_t3_reco_transition_to_status"),
        ("pending", "accepted", None, "ck_t3_reco_transition_to_status"),
        # Rule 3: a closure is a SYSTEM event and carries no teacher id.
        ("accepted", "accepted", TEACHER, "ck_t3_reco_transition_actor"),
    ],
)
def test_a_closure_cannot_rewrite_a_decision_or_carry_a_teacher(
    from_status, to_status, teacher, constraint
):
    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            _learner, run, reco = await _seed(conn)
            with pytest.raises(asyncpg.exceptions.CheckViolationError) as caught:
                await conn.execute(
                    _closure_sql(), uuid.uuid4(), reco, teacher, from_status, to_status, *_PROV, run
                )
            assert caught.value.constraint_name == constraint
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())


def test_a_closure_and_a_teacher_decision_can_both_exist_but_only_one_each():
    """`uq_t3_reco_transition_once` is now partial: one teacher decision AND one closure per
    recommendation -- an accepted suggestion that later expires has both rows."""

    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            _learner, run, reco = await _seed(conn)
            await conn.execute(
                "insert into t3_recommendation_transitions (transition_id, recommendation_id, "
                "teacher_profile_id, from_status, to_status, source_class, source_system, "
                "parameter_source_status, pipeline_run_id) values ($1,$2,$3,'pending','accepted',$4,$5,$6,$7)",
                uuid.uuid4(), reco, TEACHER, *_PROV, run,
            )
            await conn.execute(
                _closure_sql(), uuid.uuid4(), reco, None, "accepted", "accepted", *_PROV, run
            )
            assert await conn.fetchval(
                "select count(*) from t3_recommendation_transitions where recommendation_id=$1", reco
            ) == 2
            with pytest.raises(asyncpg.exceptions.UniqueViolationError) as caught:
                await conn.execute(
                    _closure_sql(), uuid.uuid4(), reco, None, "accepted", "accepted", *_PROV, run
                )
            assert caught.value.constraint_name == "uq_t3_reco_closure_once"
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())


def test_closing_a_suggestion_frees_the_learner_for_the_next_one():
    """The whole point of D47: `uq_t3_reco_active` covers OPEN suggestions only, so an ACCEPTED
    suggestion no longer blocks its learner forever."""

    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            learner, run, reco = await _seed(conn)
            await conn.execute(
                "update t3_recommendations set teacher_status='accepted' where recommendation_id=$1",
                reco,
            )
            # The refused insert aborts the enclosing transaction, so it runs inside its own
            # savepoint -- the point is that the SECOND attempt, after closure, succeeds.
            inner = conn.transaction()
            await inner.start()
            with pytest.raises(asyncpg.exceptions.UniqueViolationError):
                await _insert_second(conn, learner, run)
            await inner.rollback()

            await conn.execute(
                "update t3_recommendations set closed_at_session=9, closed_at_utc=now() "
                "where recommendation_id=$1",
                reco,
            )
            await _insert_second(conn, learner, run)  # now permitted
            assert await conn.fetchval(
                "select count(*) from t3_recommendations where student_id=$1 and target_component='both'",
                learner,
            ) == 2
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())


def test_a_closure_cannot_predate_expiry():
    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            _learner, _run, reco = await _seed(conn)  # expires_after_session = 8
            with pytest.raises(asyncpg.exceptions.CheckViolationError) as caught:
                await conn.execute(
                    "update t3_recommendations set closed_at_session=8, closed_at_utc=now() "
                    "where recommendation_id=$1",
                    reco,
                )
            assert caught.value.constraint_name == "ck_t3_reco_closure_after_expiry"
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())


def test_a_closure_session_needs_its_timestamp():
    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        tx = conn.transaction()
        await tx.start()
        try:
            _learner, _run, reco = await _seed(conn)
            with pytest.raises(asyncpg.exceptions.CheckViolationError) as caught:
                await conn.execute(
                    "update t3_recommendations set closed_at_session=9 where recommendation_id=$1",
                    reco,
                )
            assert caught.value.constraint_name == "ck_t3_reco_closure_pair"
        finally:
            await tx.rollback()
            await conn.close()

    _run(go())
