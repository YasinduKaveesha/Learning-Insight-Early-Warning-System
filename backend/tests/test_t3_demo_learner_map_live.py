"""Live-schema guards for `t3_demo_learner_map` (work order B4.1).

Introspects and exercises the ACTUAL database. Skips cleanly when the tooling or a database
is not available. Same pattern as `test_t3_predictions_live.py`: every mutating test runs
inside a transaction that is ALWAYS rolled back, so nothing here needs its own cleanup step.

    T3_LIVE_DB_URL=postgresql://upadya:...@127.0.0.1:55432/upadya_test \\
        python -m pytest --noconftest tests/test_t3_demo_learner_map_live.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the live B4.1 gates",
)


def _normalise(url: str) -> str:
    try:
        from app.infrastructure.db_url import normalise_async_url

        return normalise_async_url(url)
    except Exception:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _engine():
    return create_async_engine(_normalise(_LIVE_URL))


def _seed_learner_sql() -> str:
    return (
        "INSERT INTO b_learners (learner_id, status, request_id, operation_or_event_type, "
        "reason_code, resource_type, resource_id, source_class, source_system, environment, "
        "schema_revision, system_actor, name) "
        "VALUES (:lid, 'active', :rid, 'create', 'b4_1_live_gate', 'learner', :lid, 'TEST', "
        "'t3_demo_fixture', 'test', '1', 't3_demo_fixture', :name)"
    )


async def _run_in_rolled_back_txn(body) -> None:
    """Run `body(conn)` inside a transaction that is ALWAYS rolled back afterwards.

    Any exception `body` raises propagates out (through the rollback) for the caller to
    assert on; nothing is ever committed.
    """

    engine = _engine()
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                await body(conn)
            finally:
                await trans.rollback()
    finally:
        await engine.dispose()


def test_table_and_constraints_present() -> None:
    async def go() -> None:
        engine = _engine()
        try:
            async with engine.connect() as conn:
                cols = await conn.run_sync(
                    lambda c: {x["name"] for x in inspect(c).get_columns("t3_demo_learner_map")}
                )
                expected = {
                    "learner_id",
                    "research_student_id",
                    "created_at_utc",
                    "updated_at_utc",
                    "source_class",
                    "source_system",
                    "parameter_source_status",
                    "pipeline_run_id",
                }
                assert expected <= cols, sorted(expected - cols)

                pk = await conn.run_sync(
                    lambda c: inspect(c).get_pk_constraint("t3_demo_learner_map")
                )
                assert pk["constrained_columns"] == ["learner_id"]

                uniques = await conn.run_sync(
                    lambda c: inspect(c).get_unique_constraints("t3_demo_learner_map")
                )
                assert any(
                    u["column_names"] == ["research_student_id"] for u in uniques
                ), uniques
        finally:
            await engine.dispose()

    asyncio.run(go())


def _map_insert_sql() -> str:
    return (
        "INSERT INTO t3_demo_learner_map (learner_id, research_student_id, source_class, "
        "source_system, parameter_source_status, pipeline_run_id) "
        "VALUES (:lid, :sid, 'TEST', 't3_demo_fixture', 'TEST_FIXTURE_ONLY', :run)"
    )


async def _seed_two_learners(conn) -> tuple:
    l1, l2 = uuid.uuid4(), uuid.uuid4()
    await conn.execute(text(_seed_learner_sql()), {"lid": l1, "rid": f"g-{l1}", "name": "g1"})
    await conn.execute(text(_seed_learner_sql()), {"lid": l2, "rid": f"g-{l2}", "name": "g2"})
    return l1, l2


def test_two_learners_mapped_to_the_same_research_student_id_is_rejected() -> None:
    """Uniqueness direction (a): research_student_id must map to at most one learner."""

    async def body(conn) -> None:
        l1, l2 = await _seed_two_learners(conn)
        sid = "STU-9001"
        await conn.execute(
            text(_map_insert_sql()), {"lid": l1, "sid": sid, "run": uuid.uuid4()}
        )
        # second learner, SAME research_student_id -- must violate the UNIQUE constraint.
        await conn.execute(
            text(_map_insert_sql()), {"lid": l2, "sid": sid, "run": uuid.uuid4()}
        )

    with pytest.raises(IntegrityError) as excinfo:
        asyncio.run(_run_in_rolled_back_txn(body))
    assert "research_student_id" in str(excinfo.value) or "uq_t3_demo_learner_map" in str(
        excinfo.value
    )


def test_one_learner_mapped_to_two_research_student_ids_is_rejected() -> None:
    """Uniqueness direction (b): a learner must map to at most one research_student_id."""

    async def body(conn) -> None:
        l1, _ = await _seed_two_learners(conn)
        await conn.execute(
            text(_map_insert_sql()), {"lid": l1, "sid": "STU-9002", "run": uuid.uuid4()}
        )
        # SAME learner, a different research_student_id -- must violate the PRIMARY KEY.
        await conn.execute(
            text(_map_insert_sql()), {"lid": l1, "sid": "STU-9003", "run": uuid.uuid4()}
        )

    with pytest.raises(IntegrityError) as excinfo:
        asyncio.run(_run_in_rolled_back_txn(body))
    assert "learner_id" in str(excinfo.value) or "pk_t3_demo_learner_map" in str(excinfo.value)


@pytest.mark.parametrize("bad_id", ["STU-1", "stu-0001"])
def test_format_check_rejects_malformed_research_student_id(bad_id: str) -> None:
    async def body(conn) -> None:
        l1, _ = await _seed_two_learners(conn)
        await conn.execute(
            text(_map_insert_sql()), {"lid": l1, "sid": bad_id, "run": uuid.uuid4()}
        )

    with pytest.raises(IntegrityError) as excinfo:
        asyncio.run(_run_in_rolled_back_txn(body))
    assert "ck_t3_demo_learner_map_format" in str(excinfo.value) or "format" in str(
        excinfo.value
    ).lower()
