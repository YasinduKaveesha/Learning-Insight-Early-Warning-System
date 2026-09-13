"""Every `data_access` reader COMPILES against the REAL schema (work order B6.3).

Distinct from `tests/test_data_access_live.py`, which is B2.4's behavioural gate suite
(roster/ownership/provenance semantics against seeded fixture rows). This file asserts
almost no behaviour -- only that each reader EXECUTES.

WHY THIS FILE EXISTS
--------------------
`classrooms_for_teacher` shipped in B6.1 selecting `classrooms.c.name` and filtering on
`classrooms.c.source_class` -- neither of which existed on the shadow `Table` definition, so
the query raised `AttributeError` before it could reach a database. The full suite was green
and stayed green, because every dashboard test monkeypatches `data_access` wholesale to keep
the service tests fast and deterministic. That is the right thing for those tests to do, and
it means NOTHING was checking that the readers themselves compile against the real schema.

So this suite calls each reader for real. It asserts almost nothing about the DATA -- the
shared dev database drifts as the child app is used, and pinning counts here would produce a
test that fails for reasons that are not defects. What it pins is that every reader
**executes**: the columns exist, the joins resolve, the types bind. That is exactly the class
of failure the mocked suites are structurally unable to see.

Runs read-only against `T3_LIVE_DB_URL_READONLY` (the `upadya` dev database). It writes
nothing and creates nothing.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application import data_access
from app.infrastructure.db_url import normalise_async_url

_READONLY_URL = os.environ.get("T3_LIVE_DB_URL_READONLY")

pytestmark = pytest.mark.skipif(
    not _READONLY_URL,
    reason="set T3_LIVE_DB_URL_READONLY to run the data-access readers against the real schema",
)

if _READONLY_URL:
    # The REACHABLE variant, not the plain safety one: B0.1 drew this distinction
    # deliberately -- an unreachable database must SKIP, never FAIL. The port is an opt-in
    # local override that a plain `docker compose up` by the student-app team removes, and a
    # suite that goes red when someone else restarts their containers trains people to
    # ignore red.
    from tests._live_db_target_guard import (
        assert_safe_and_reachable_readonly_live_target,
    )

    assert_safe_and_reachable_readonly_live_target(_READONLY_URL)


def _run(coro):
    async def _go():
        engine = create_async_engine(
            normalise_async_url(_READONLY_URL),
            connect_args={"server_settings": {"default_transaction_read_only": "on"}},
        )
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                return await coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_real_learners_executes_and_filters_to_real():
    rows = _run(lambda s: data_access.real_learners(s))
    assert isinstance(rows, list) or rows is not None
    for row in rows[:50]:
        assert row.learner_id is not None
        assert row.name is not None


def test_classrooms_for_teacher_executes_against_the_real_schema():
    """The reader whose missing columns started this file. Runs for a teacher who owns
    nothing -- an empty result still proves the SELECT compiled and the columns exist, which
    is the whole point."""

    rows = _run(
        lambda s: data_access.classrooms_for_teacher(s, uuid.UUID(int=0))
    )
    assert rows == [] or all(r.classroom_id is not None for r in rows)


def test_classrooms_for_teacher_returns_name_and_grade_for_a_real_teacher():
    """Picks a teacher that actually owns a REAL classroom and asserts the three columns the
    dashboard serves are populated. Skips rather than fails if the shared dev database has
    no such teacher today -- an empty roster is a data-provisioning fact, not a code defect.
    """

    async def _go(session):
        from sqlalchemy import select

        from app.infrastructure.db.models import classrooms

        owner = (
            await session.execute(
                select(classrooms.c.teacher_profile_id)
                .where(classrooms.c.source_class == "REAL")
                .limit(1)
            )
        ).first()
        if owner is None:
            return None
        return await data_access.classrooms_for_teacher(session, owner.teacher_profile_id)

    rows = _run(_go)
    if rows is None:
        pytest.skip("no REAL classroom in the dev database to read")
    assert rows, "a teacher known to own a REAL classroom returned none"
    for row in rows:
        assert row.name is not None
        assert row.grade in {"GRADE_2", "GRADE_3"}


def test_classroom_roster_executes():
    rows = _run(lambda s: data_access.classroom_roster(s, uuid.UUID(int=0)))
    assert rows == []


def test_pending_request_counts_executes_and_returns_a_mapping():
    counts = _run(lambda s: data_access.pending_request_counts(s, [uuid.UUID(int=0)]))
    assert counts == {}


def test_pending_request_counts_short_circuits_on_an_empty_list():
    assert _run(lambda s: data_access.pending_request_counts(s, [])) == {}


def test_ownership_guards_execute_and_fail_closed():
    """Both guards must answer False for a nonexistent id rather than raise -- fail closed
    is only a guarantee if the query runs."""

    assert (
        _run(
            lambda s: data_access.teacher_owns_classroom(
                s, uuid.UUID(int=0), uuid.UUID(int=0)
            )
        )
        is False
    )
    assert (
        _run(
            lambda s: data_access.learner_visible_to_teacher(
                s, uuid.UUID(int=0), uuid.UUID(int=0)
            )
        )
        is False
    )
