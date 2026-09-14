"""Migration 0010 (expiry closure, D47) against the real database.

Round trip, the constraint NAMES at head, and the one behaviour the migration itself owns: the
downgrade REFUSES to run while closure events exist, rather than silently deleting rows from a
research log. Helpers are shared with the 0008 module. Ends at `head`, pass or fail.
"""

from __future__ import annotations

import asyncio
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

pytest.importorskip("asyncpg")
import asyncpg  # noqa: E402

EXPECTED_TRANSITION_CONSTRAINTS = {
    "ck_t3_reco_transition_actor",
    "ck_t3_reco_transition_event_type",
    "ck_t3_reco_transition_from_pending",
    "ck_t3_reco_transition_modified",
    "ck_t3_reco_transition_to_status",
    "ck_t3_recommendation_transitions_source_class",
    "fk_t3_reco_transitions_recommendation_id",
    "pk_t3_recommendation_transitions",
}
EXPECTED_INDEXES = {"uq_t3_reco_transition_once", "uq_t3_reco_closure_once"}
_PROV = ("TEST", "b7_live_0010", "TEST_FIXTURE_ONLY")


@pytest.fixture(autouse=True)
def _restore_head_afterwards():
    try:
        yield
    finally:
        with _database_url_env(_LIVE_URL):
            command.upgrade(_alembic_config(), "head")


def _plain() -> str:
    return _LIVE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def _query(sql: str, *args):
    async def go():
        conn = await asyncpg.connect(_plain())
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(go())


def test_0010_round_trip_and_closure_columns() -> None:
    with _database_url_env(_LIVE_URL):
        cfg = _alembic_config()
        command.upgrade(cfg, "head")

        columns = {
            r["column_name"]
            for r in _query(
                "select column_name from information_schema.columns "
                "where table_name = 't3_recommendations'"
            )
        }
        assert {"closed_at_session", "closed_at_utc"} <= columns

        command.downgrade(cfg, "0009_reco_transitions")
        after = {
            r["column_name"]
            for r in _query(
                "select column_name from information_schema.columns "
                "where table_name = 't3_recommendations'"
            )
        }
        assert not {"closed_at_session", "closed_at_utc"} & after
        # The table and its parent survive.
        assert _table_exists(_LIVE_URL, "t3_recommendation_transitions") is True
        assert _table_exists(_LIVE_URL, "t3_recommendations") is True

        command.upgrade(cfg, "head")
        assert {"closed_at_session", "closed_at_utc"} <= {
            r["column_name"]
            for r in _query(
                "select column_name from information_schema.columns "
                "where table_name = 't3_recommendations'"
            )
        }


def test_0010_constraint_and_index_names_are_exactly_as_written() -> None:
    with _database_url_env(_LIVE_URL):
        command.upgrade(_alembic_config(), "head")

    names = {
        r["conname"]
        for r in _query(
            "select conname from pg_constraint "
            "where conrelid = 't3_recommendation_transitions'::regclass"
        )
    }
    assert names == EXPECTED_TRANSITION_CONSTRAINTS
    indexes = {
        r["indexname"]
        for r in _query(
            "select indexname from pg_indexes where tablename = 't3_recommendation_transitions'"
        )
    }
    assert EXPECTED_INDEXES <= indexes


def test_the_downgrade_refuses_while_closure_events_exist() -> None:
    """A closure is a row in a research log (`docs/13` §6). The downgrade cannot represent it, so
    it raises rather than deleting it. Committed, then cleaned up -- a rolled-back transaction
    could not be seen by Alembic's own connection."""

    async def seed() -> tuple:
        conn = await asyncpg.connect(_plain())
        try:
            learner = await conn.fetchval("select learner_id from b_learners limit 1")
            if learner is None:
                pytest.skip("no b_learners row available")
            run, reco = uuid.uuid4(), uuid.uuid4()
            await conn.execute(
                "insert into t3_pipeline_runs (pipeline_run_id, dataset_manifest, model_version, "
                "source_class, source_system, parameter_source_status) values ($1,$2,$3,$4,$5,$6)",
                run, json.dumps({"seed": "0010"}), "0010-live", *_PROV,
            )
            await conn.execute(
                "insert into t3_recommendations (recommendation_id, student_id, "
                "issued_at_intervention_session, expires_after_session, target_component, trigger, "
                "proposed_action, evidence_summary, teacher_status, pipeline_run_id, source_class, "
                "source_system, parameter_source_status) "
                "values ($1,$2,3,8,'C',$3,$4,'s','pending',$5,$6,$7,$8)",
                reco, learner, json.dumps({"type": "watch_flag", "evidence": {}}),
                json.dumps({"kind": "monitor_progress", "detail": {}}), run, *_PROV,
            )
            await conn.execute(
                "insert into t3_recommendation_transitions (transition_id, recommendation_id, "
                "teacher_profile_id, event_type, from_status, to_status, source_class, "
                "source_system, parameter_source_status, pipeline_run_id) "
                "values ($1,$2,NULL,'expiry_closure','pending','pending',$3,$4,$5,$6)",
                uuid.uuid4(), reco, *_PROV, run,
            )
            return run, reco
        finally:
            await conn.close()

    async def cleanup(run, reco) -> None:
        conn = await asyncpg.connect(_plain())
        try:
            await conn.execute(
                "delete from t3_recommendation_transitions where recommendation_id=$1", reco
            )
            await conn.execute("delete from t3_recommendations where recommendation_id=$1", reco)
            await conn.execute("delete from t3_pipeline_runs where pipeline_run_id=$1", run)
        finally:
            await conn.close()

    run, reco = asyncio.run(seed())
    try:
        with _database_url_env(_LIVE_URL):
            with pytest.raises(Exception) as caught:
                command.downgrade(_alembic_config(), "0009_reco_transitions")
        assert "downgrade refused" in str(caught.value)
        # And the closure row is still there.
        assert len(_query(
            "select 1 from t3_recommendation_transitions where recommendation_id=$1", reco
        )) == 1
    finally:
        asyncio.run(cleanup(run, reco))
