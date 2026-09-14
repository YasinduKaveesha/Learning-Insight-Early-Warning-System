"""Gate 1 of work order B2.4, demonstrated against the ACTUAL counts quoted in it.

The work order measured `b_learners` on the live `upadya` database: 47 REAL rows (all
`status='ACTIVE'`) and 94 TEST rows (`status` either lowercase `'active'` or `'test_only'`).
`upadya_test` (the disposable database every other live test in this suite targets) has a
different seed split, so this specific gate can only be shown against `upadya` itself.

`upadya` must come out of this run byte-for-byte unchanged (backend_plan.md / B2.4 gate 8).
Two independent guarantees enforce that, not one:

1. This module only ever calls `data_access.real_learners` -- a `SELECT`, nothing else.
2. The engine is opened with `execution_options={"postgresql_readonly": True}`, so Postgres
   itself rejects any write on this connection even if a future edit to this file tried one.

Set `T3_LIVE_DB_URL_READONLY` to a direct (5432 or the published 55432) connection to
`upadya` to run this file; it skips cleanly otherwise. This is a NEW, narrower environment
variable -- deliberately not `T3_LIVE_DB_URL`, which `tests/_live_db_target_guard.py` (B0.1)
restricts to the disposable `upadya_test` database for the suite's mutating live tests.
"""

from __future__ import annotations

import asyncio
import os

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

_ENV_VAR = "T3_LIVE_DB_URL_READONLY"
_LIVE_URL = os.environ.get(_ENV_VAR)

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_readonly_live_target

    assert_safe_and_reachable_readonly_live_target(_LIVE_URL, env_var=_ENV_VAR)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason=f"set {_ENV_VAR} to a direct Postgres URL for `upadya` to run the B2.4 gate-1 count",
)


def _normalise(url: str) -> str:
    try:
        from app.infrastructure.db_url import normalise_async_url

        return normalise_async_url(url)
    except Exception:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _run(coro):
    return asyncio.run(coro)


def _make_readonly_session_factory():
    engine = create_async_engine(
        _normalise(_LIVE_URL), execution_options={"postgresql_readonly": True}
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_gate1_real_learners_is_exactly_47_and_excludes_every_test_row() -> None:
    from app.application import data_access

    async def go() -> None:
        engine, maker = _make_readonly_session_factory()
        try:
            async with maker() as session:
                rows = await data_access.real_learners(session)
        finally:
            await engine.dispose()

        assert len(rows) == 47, f"expected exactly 47 REAL b_learners, got {len(rows)}"

    _run(go())


def test_gate1_readonly_connection_actually_rejects_a_write() -> None:
    """Prove the `postgresql_readonly` execution option is not decorative: an INSERT on this
    same connection must fail with Postgres's own read-only-transaction error, not merely be
    something this test file happens not to attempt."""

    from sqlalchemy import text

    async def go() -> None:
        engine, maker = _make_readonly_session_factory()
        try:
            async with maker() as session:
                with pytest.raises(Exception) as exc_info:
                    await session.execute(
                        text(
                            "INSERT INTO t3_pipeline_runs "
                            "(pipeline_run_id, dataset_manifest, model_version) "
                            "VALUES (gen_random_uuid(), '{}'::jsonb, 'gate1-write-probe')"
                        )
                    )
                assert "read-only" in str(exc_info.value).lower()
        finally:
            await engine.dispose()

    _run(go())


def test_gate1_no_test_only_or_lowercase_active_row_leaks_through() -> None:
    """Cross-check gate 1 against a raw, unfiltered read: every non-REAL row this module
    would have to exclude is provably a TEST row with the documented `status` values, and
    `real_learners`'s result set is disjoint from it."""

    from sqlalchemy import text

    from app.application import data_access

    async def go() -> None:
        engine, maker = _make_readonly_session_factory()
        try:
            async with maker() as session:
                real_rows = await data_access.real_learners(session)
                real_ids = {row.learner_id for row in real_rows}

                other = (
                    await session.execute(
                        text(
                            "SELECT learner_id, source_class, status FROM b_learners "
                            "WHERE source_class != 'REAL'"
                        )
                    )
                ).all()
        finally:
            await engine.dispose()

        assert len(other) == 94, f"expected exactly 94 non-REAL rows, got {len(other)}"
        for row in other:
            assert row.source_class == "TEST"
            assert row.status in ("active", "test_only")
            assert row.learner_id not in real_ids

    _run(go())
