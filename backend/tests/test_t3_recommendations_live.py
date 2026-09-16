"""Live-schema gates for the B3.5 table (work order B3.5, gates 1, 3-6 live).

Introspects and exercises the ACTUAL database. Skips cleanly when the tooling or a database
is not available -- always the case in the pinned `c3-ews` env (no SQLAlchemy, no driver,
and the local Docker DB publishes no host port). To run it against the demo DB:

    docker run -d --rm --name c3-pgproxy --network upadya-be1_default \\
        -p 127.0.0.1:55432:5432 alpine/socat \\
        tcp-listen:5432,fork,reuseaddr tcp-connect:upadya-be1-db-1:5432
    T3_LIVE_DB_URL=postgresql://upadya:local-development-only@127.0.0.1:55432/upadya \\
        python -m pytest --noconftest tests/test_t3_recommendations_live.py
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest

pytest.importorskip("asyncpg")
import asyncpg  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the live B3.5 gates",
)

_PROV = dict(source_class="TEST", source_system="b3.5_live", parameter_source_status="TEST_FIXTURE_ONLY")


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_plain(_LIVE_URL))


def _run(coro):
    return asyncio.run(coro)


async def _fixture_ctx(conn):
    """A rolled-back transaction holding one learner id and one seeded pipeline run."""

    tx = conn.transaction()
    await tx.start()
    learner = await conn.fetchval("select learner_id from b_learners limit 1")
    run = uuid.uuid4()
    await conn.execute(
        "insert into t3_pipeline_runs (pipeline_run_id, dataset_manifest, model_version, "
        "source_class, source_system, parameter_source_status) values ($1,$2,$3,$4,$5,$6)",
        run, json.dumps({"seed": "b3.5-live"}), "1.0.0",
        _PROV["source_class"], _PROV["source_system"], _PROV["parameter_source_status"],
    )
    return tx, learner, run


async def _insert(conn, learner, run, **kw):
    cols = dict(
        recommendation_id=uuid.uuid4(), student_id=learner,
        issued_at_intervention_session=3, expires_after_session=8, target_component="B",
        trigger={"type": "x", "evidence": {"a": 1}},
        proposed_action={"kind": "practice", "detail": "d"},
        evidence_summary="s", teacher_status="pending",
        pipeline_run_id=run, **_PROV,
    )
    cols.update(kw)
    keys = list(cols)
    ph = ", ".join(f"${i + 1}" for i in range(len(keys)))
    vals = [json.dumps(v) if isinstance(v, dict) else v for v in (cols[k] for k in keys)]
    await conn.execute(f"insert into t3_recommendations ({', '.join(keys)}) values ({ph})", *vals)


def test_gate1_table_exists_and_student_app_untouched() -> None:
    async def go() -> None:
        conn = await _connect()
        try:
            assert await conn.fetchval("select to_regclass('public.t3_recommendations') is not null")
            non_t3 = await conn.fetchval(
                "select count(*) from information_schema.tables where table_schema='public' "
                "and table_type='BASE TABLE' and table_name not like 't3_%'"
            )
            assert non_t3 == 36, non_t3
            # Updated for each new migration -- 0012 added the run-scoped indexes.
            assert await conn.fetchval("select version_num from t3_alembic_version") == "0012_run_scoped_indexes"
        finally:
            await conn.close()

    _run(go())


@pytest.mark.parametrize(
    "kw, should_pass, constraint",
    [
        (dict(teacher_status="pending", b_applied_at_intervention_session=7), False, "ck_t3_reco_ethical_gate"),
        (dict(teacher_status="accepted", b_applied_at_intervention_session=7), True, None),
        (dict(teacher_status="dismissed", c_applied_at_intervention_session=4), False, "ck_t3_reco_ethical_gate"),
        (dict(teacher_status="modified", teacher_modified_action=None), False, "ck_t3_reco_modified"),
        (dict(teacher_status="pending", teacher_modified_action={"k": 1}), False, "ck_t3_reco_modified"),
        (dict(teacher_status="modified", teacher_modified_action={"k": 1}), True, None),
        (dict(expires_after_session=9), False, "ck_t3_reco_expiry"),  # issued 3 + 6
        (dict(expires_after_session=8), True, None),                  # issued 3 + 5
    ],
)
def test_gates_3_5_6_check_constraints(kw, should_pass, constraint) -> None:
    async def go() -> None:
        conn = await _connect()
        try:
            tx, learner, run = await _fixture_ctx(conn)
            try:
                await _insert(conn, learner, run, **kw)
                assert should_pass, f"expected {constraint} to reject {kw}"
            except asyncpg.exceptions.IntegrityConstraintViolationError as e:
                assert not should_pass, f"unexpected reject: {e}"
                assert e.constraint_name == constraint, (e.constraint_name, constraint)
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    _run(go())


def test_gate4_partial_unique_index() -> None:
    async def go() -> None:
        conn = await _connect()
        try:
            tx, learner, run = await _fixture_ctx(conn)
            try:
                await _insert(conn, learner, run, teacher_status="pending", target_component="C")
                with pytest.raises(asyncpg.exceptions.UniqueViolationError):
                    await _insert(conn, learner, run, teacher_status="pending", target_component="C")
            finally:
                await tx.rollback()

            tx, learner, run = await _fixture_ctx(conn)
            try:
                await _insert(conn, learner, run, teacher_status="dismissed", target_component="C")
                # a dismissed row must NOT block a new pending one for the same pair
                await _insert(conn, learner, run, teacher_status="pending", target_component="C")
            finally:
                await tx.rollback()
        finally:
            await conn.close()

    _run(go())
