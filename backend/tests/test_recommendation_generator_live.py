"""The D35 generator's queries EXECUTE against the real schema (work order B7).

The rule itself is pinned offline in `tests/test_recommendation_generator.py`. This module
catches the failure class that suite is structurally blind to -- a column that is not on the
model, a `DISTINCT ON` that does not compile, the `Row.t` shadowing -- by running the pipeline
step for real, in dry-run mode, against a run id that has no rows. It writes nothing.

Issuing against real data is verified on the demo run and recorded in the handover; it is not
repeated here because it commits rows.
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.application import recommendation_generator as gen  # noqa: E402
from app.infrastructure.db_url import normalise_async_url  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


pytestmark = pytest.mark.skipif(
    not _LIVE_URL, reason="set T3_LIVE_DB_URL to run the live generator schema gate"
)


def test_the_generator_runs_against_the_real_schema_and_writes_nothing_in_dry_run():
    async def go():
        engine = create_async_engine(normalise_async_url(_LIVE_URL))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                result = await gen.run_generator(
                    session, pipeline_run_id=uuid.uuid4(), dry_run=True
                )
        finally:
            await engine.dispose()
        return result

    result = asyncio.run(go())
    assert result == gen.GeneratorResult(
        learners=0, issued=0, skipped_active=0, skipped_not_eligible=0
    )


def test_the_generator_closes_an_expired_suggestion_without_touching_the_decision():
    """D47 end to end. A learner at session 15 holding an ACCEPTED suggestion that expired at 9:
    the generator closes it, logs a system event, and leaves `teacher_status` alone.

    The learner is not watch-flagged here (no prediction row), so nothing new is issued -- this
    test is about closure only.
    """

    async def go():
        conn = await asyncpg.connect(_plain(_LIVE_URL))
        engine = create_async_engine(normalise_async_url(_LIVE_URL))
        learner = await conn.fetchval("select learner_id from b_learners limit 1")
        if learner is None:
            pytest.skip("no b_learners row available")
        run, reco = uuid.uuid4(), uuid.uuid4()
        prov = ("TEST", "b7_live_d47", "TEST_FIXTURE_ONLY")
        try:
            await conn.execute(
                "insert into t3_pipeline_runs (pipeline_run_id, dataset_manifest, model_version, "
                "source_class, source_system, parameter_source_status) values ($1,$2,$3,$4,$5,$6)",
                run, json.dumps({"seed": "d47"}), "d47-live", *prov,
            )
            await conn.execute(
                "insert into t3_panel (student_id, intervention_session_number, "
                "intervention_session_date, b_present, c_present, pipeline_run_id, source_class, "
                "source_system, parameter_source_status) "
                "values ($1,15,'2026-05-04',true,true,$2,$3,$4,$5)",
                learner, run, *prov,
            )
            await conn.execute(
                "insert into t3_recommendations (recommendation_id, student_id, "
                "issued_at_intervention_session, expires_after_session, target_component, trigger, "
                "proposed_action, evidence_summary, teacher_status, pipeline_run_id, source_class, "
                "source_system, parameter_source_status) "
                "values ($1,$2,4,9,'both',$3,$4,'s','accepted',$5,$6,$7,$8)",
                reco, learner, json.dumps({"type": "watch_flag", "evidence": {}}),
                json.dumps({"kind": "monitor_progress", "detail": {}}), run, *prov,
            )

            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                result = await gen.run_generator(session, pipeline_run_id=run)

            assert result.closed == 1
            assert result.issued == 0

            row = await conn.fetchrow(
                "select teacher_status, closed_at_session, closed_at_utc from t3_recommendations "
                "where recommendation_id=$1",
                reco,
            )
            # Rule 2: the decision is untouched. Rule 1: the active period is closed.
            assert row["teacher_status"] == "accepted"
            assert row["closed_at_session"] == 15
            assert row["closed_at_utc"] is not None

            log = await conn.fetch(
                "select event_type, from_status, to_status, teacher_profile_id, trigger_type "
                "from t3_recommendation_transitions where recommendation_id=$1",
                reco,
            )
            assert len(log) == 1
            assert log[0]["event_type"] == "expiry_closure"
            assert log[0]["from_status"] == log[0]["to_status"] == "accepted"
            assert log[0]["teacher_profile_id"] is None  # a system event
            assert log[0]["trigger_type"] == "watch_flag"

            # Idempotent: a second run closes nothing more.
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                assert (await gen.run_generator(session, pipeline_run_id=run)).closed == 0
        finally:
            await conn.execute(
                "delete from t3_recommendation_transitions where recommendation_id=$1", reco
            )
            await conn.execute("delete from t3_recommendations where student_id=$1 and pipeline_run_id=$2", learner, run)
            await conn.execute("delete from t3_panel where pipeline_run_id=$1", run)
            await conn.execute("delete from t3_pipeline_runs where pipeline_run_id=$1", run)
            await conn.close()
            await engine.dispose()

    asyncio.run(go())
