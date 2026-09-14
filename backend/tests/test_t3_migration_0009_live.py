"""Migration 0009 (`t3_recommendation_transitions`) against the real database (work order B7).

Upgrade -> downgrade -> upgrade, then the constraint NAMES. The names are pinned because the first
draft of this migration passed bare strings, and the MetaData naming convention silently rewrote
`ck_t3_reco_transition_from_pending` into `ck_t3_recommendation_transitions_ck_t3_reco_transition__f369`.
Autogenerate did not notice -- it does not compare CHECK names -- but the live state-machine tests
did. Helpers are shared with the 0008 module rather than copied.

Ends at `head`, pass or fail.
"""

from __future__ import annotations

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
    "ck_t3_reco_transition_from_pending",
    "ck_t3_reco_transition_modified",
    "ck_t3_reco_transition_to_status",
    "ck_t3_recommendation_transitions_source_class",
    "fk_t3_reco_transitions_recommendation_id",
    "pk_t3_recommendation_transitions",
    "uq_t3_reco_transition_once",
}


@pytest.fixture(autouse=True)
def _restore_head_afterwards():
    try:
        yield
    finally:
        with _database_url_env(_LIVE_URL):
            command.upgrade(_alembic_config(), "head")


def _constraint_names() -> set[str]:
    import asyncio

    import asyncpg

    async def go() -> set[str]:
        conn = await asyncpg.connect(_LIVE_URL.replace("postgresql+asyncpg://", "postgresql://", 1))
        try:
            rows = await conn.fetch(
                "select conname from pg_constraint "
                "where conrelid = 't3_recommendation_transitions'::regclass"
            )
            return {r["conname"] for r in rows}
        finally:
            await conn.close()

    return asyncio.run(go())


def test_0009_round_trip_touches_only_its_own_table() -> None:
    with _database_url_env(_LIVE_URL):
        cfg = _alembic_config()

        command.upgrade(cfg, "head")
        assert _table_exists(_LIVE_URL, "t3_recommendation_transitions") is True

        command.downgrade(cfg, "0008_teacher_bindings")
        assert _table_exists(_LIVE_URL, "t3_recommendation_transitions") is False
        # Its parent and its predecessor survive the downgrade.
        assert _table_exists(_LIVE_URL, "t3_recommendations") is True
        assert _table_exists(_LIVE_URL, "t3_teacher_bindings") is True

        command.upgrade(cfg, "head")
        assert _table_exists(_LIVE_URL, "t3_recommendation_transitions") is True


def test_0009_constraint_names_are_exactly_as_written() -> None:
    """Asserted at 0009, not at head: 0010 (D47) deliberately replaces three of these CHECKs and
    turns the unique constraint into a partial index. What this pins is that 0009 itself still
    creates the names it wrote -- the naming-convention bug it was added for."""

    with _database_url_env(_LIVE_URL):
        cfg = _alembic_config()
        command.downgrade(cfg, "0009_reco_transitions")
        try:
            assert _constraint_names() == EXPECTED_CONSTRAINTS
        finally:
            command.upgrade(cfg, "head")
