"""Live-schema guards for the B3.4 tables (work order B3.4).

Introspects and exercises the ACTUAL database. Skips cleanly when the tooling or a database
is not available -- always the case in the pinned `c3-ews` env (no SQLAlchemy, no driver,
and the local Docker DB publishes no host port). To run it:

    T3_LIVE_DB_URL=postgresql://upadya:...@127.0.0.1:5432/upadya \\
        python -m pytest --noconftest tests/test_t3_predictions_live.py
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
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the live B3.4 gates",
)

_FORBIDDEN = {"population", "dd_subtype"}
_ARTEFACT_SHA = "019f000be16f533630b6e5d3215bf86597745a725cb13c5b989d03f45769db15"


def _normalise(url: str) -> str:
    try:
        from app.infrastructure.db_url import normalise_async_url

        return normalise_async_url(url)
    except Exception:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _engine():
    return create_async_engine(_normalise(_LIVE_URL))


def test_no_population_or_dd_subtype_column() -> None:
    async def go() -> None:
        engine = _engine()
        try:
            async with engine.connect() as conn:
                for table in ("t3_predictions", "t3_model_versions"):
                    cols = await conn.run_sync(
                        lambda c, t=table: [x["name"] for x in inspect(c).get_columns(t)]
                    )
                    assert _FORBIDDEN.isdisjoint(cols), (table, sorted(_FORBIDDEN & set(cols)))
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_model_version_seed_row_present() -> None:
    async def go() -> None:
        engine = _engine()
        try:
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT model_name, artefact_sha256, sklearn_version, training_seed "
                            "FROM t3_model_versions WHERE model_version = '1.0.0'"
                        )
                    )
                ).one()
                assert row.model_name == "component3_target_a_logreg"
                assert row.artefact_sha256 == _ARTEFACT_SHA
                assert row.sklearn_version == "1.9.0"
                assert row.training_seed == 20260828
        finally:
            await engine.dispose()

    asyncio.run(go())


def _insert_prediction_sql() -> str:
    return (
        "INSERT INTO t3_predictions (student_id, t, model_version, evidence_status, "
        "sessions_completed, predicted_class, watch_flag, practice_trajectory, "
        "engagement_trajectory, risk_level, feature_version, artefact_sha256, "
        "inference_timestamp, pipeline_run_id, source_class, source_system, "
        "parameter_source_status) "
        "VALUES (:sid, :t, '1.0.0', :evidence, :sc, :pc, :wf, 'unknown', 'unknown', :rl, "
        "'1.0.0', 'sha', now(), :run, 'SYNTHETIC', 't3_pipeline', 'TEST_FIXTURE_ONLY')"
    )


async def _run_insert(params: dict) -> None:
    """Insert one prediction row inside a transaction that is ALWAYS rolled back.

    Any IntegrityError from the insert propagates out (through the rollback) for the caller
    to assert on; nothing is ever committed.
    """

    engine = _engine()
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                sid = (
                    await conn.execute(text("SELECT learner_id FROM b_learners LIMIT 1"))
                ).scalar_one()
                run = uuid.uuid4()
                await conn.execute(
                    text(
                        "INSERT INTO t3_pipeline_runs (pipeline_run_id, dataset_manifest, "
                        "model_version, source_class, source_system, parameter_source_status) "
                        "VALUES (:run, '{}'::jsonb, '1.0.0', 'SYNTHETIC', 't3_pipeline', "
                        "'TEST_FIXTURE_ONLY')"
                    ),
                    {"run": run},
                )
                await conn.execute(
                    text(_insert_prediction_sql()),
                    {
                        "sid": sid,
                        "run": run,
                        "t": 3,
                        "evidence": "sufficient_evidence",
                        "rl": None,
                        **params,
                    },
                )
            finally:
                await trans.rollback()
    finally:
        await engine.dispose()


def test_watch_flag_check_rejects_null_predicted_class_flagged() -> None:
    # THE TRAP: predicted_class NULL, sessions_completed >= 3, watch_flag TRUE.
    # The COALESCE form forces this FALSE and rejects the row; the bare docs/04 form would
    # evaluate NULL and let it through.
    with pytest.raises(IntegrityError):
        asyncio.run(_run_insert({"sc": 5, "pc": None, "wf": True}))


def test_watch_flag_check_allows_null_predicted_class_unflagged() -> None:
    asyncio.run(_run_insert({"sc": 5, "pc": None, "wf": False}))  # must not raise


def test_no_high_tier_rejected() -> None:
    with pytest.raises(IntegrityError):
        asyncio.run(_run_insert({"sc": 5, "pc": 0, "wf": False, "rl": "High"}))
