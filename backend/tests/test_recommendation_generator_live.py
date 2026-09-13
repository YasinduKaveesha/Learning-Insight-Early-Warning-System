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
import os
import uuid

import pytest

pytest.importorskip("asyncpg")
pytest.importorskip("sqlalchemy")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.application import recommendation_generator as gen  # noqa: E402
from app.infrastructure.db_url import normalise_async_url  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

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
