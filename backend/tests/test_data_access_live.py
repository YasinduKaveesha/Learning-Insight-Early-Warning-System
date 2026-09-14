"""Live-DB gates for `app.application.data_access` (work order B2.4), gates 2-6.

Runs against the disposable `upadya_test` database via `T3_LIVE_DB_URL` -- the same
variable and the same `tests/_live_db_target_guard.assert_safe_and_reachable_live_target`
every other mutating live test in this suite already uses (see `README.md`, "Live database
gates"). Skips cleanly when `T3_LIVE_DB_URL` is unset or the target is unreachable.

Fixture IDs below (classroom/teacher/learner uuids) are rows that already exist in
`upadya_test`'s seed data -- picked, not inserted, by inspecting
`classroom_memberships`/`classrooms`/`b_learners` directly with `psql` before writing this
file. `t3_pipeline_runs` / `t3_panel` / `t3_features_at_t` rows ARE inserted by this module
(gate 2, gate 3) because `upadya_test` currently has zero of them; each test that inserts
cleans up in a `finally` so `upadya_test`'s `t3_panel` / `t3_pipeline_runs` counts return to
what they were before the run (gate 8 also covers this file, not just the readonly one).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432/55432) Postgres URL for upadya_test",
)

# Fixture ids -- pre-existing rows in upadya_test's seed data (see module docstring).
_APPROVED_CLASSROOM = uuid.UUID("20c01a32-dc88-465f-9466-16f2522f87bf")
_APPROVED_CLASSROOM_TEACHER = uuid.UUID("0ed94f84-f5bb-4a8e-9c8d-60dbed326682")
_APPROVED_LEARNER = uuid.UUID("daa990a0-0cf0-4612-ae4e-231ce5dd598b")

_PENDING_ONLY_CLASSROOM = uuid.UUID("0258d220-3d5e-49bf-a601-70cb226145f1")
_PENDING_ONLY_LEARNER = uuid.UUID("0e3e6ff6-70c9-42e5-a905-db0ab685d2a9")

_REJECTED_ONLY_CLASSROOM = uuid.UUID("5541162e-b227-4ba9-9816-bdeeddc9a9eb")
_REJECTED_ONLY_LEARNER = uuid.UUID("6ca361e7-d346-4fd9-83dc-8a7fdd4ee6f1")

#: Owns a DIFFERENT classroom -- the "wrong teacher" for every negative-ownership case.
_OTHER_TEACHER = uuid.UUID("b1ae18aa-5a91-43fa-ab73-c4808a521c1a")

_NONEXISTENT_CLASSROOM = uuid.UUID("00000000-0000-0000-0000-000000000000")
_NONEXISTENT_LEARNER = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _normalise(url: str) -> str:
    try:
        from app.infrastructure.db_url import normalise_async_url

        return normalise_async_url(url)
    except Exception:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _session_factory():
    engine = create_async_engine(_normalise(_LIVE_URL))
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _run(coro):
    return asyncio.run(coro)


# ==========================================================================================
# Gate 4 -- roster resolution returns only APPROVED members.
# ==========================================================================================


def test_gate4_roster_returns_approved_member() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                rows = await data_access.classroom_roster(session, _APPROVED_CLASSROOM)
        finally:
            await engine.dispose()
        return rows

    rows = _run(go())
    learner_ids = {row.learner_id for row in rows}
    assert _APPROVED_LEARNER in learner_ids


def test_gate4_roster_excludes_pending() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.classroom_roster(session, _PENDING_ONLY_CLASSROOM)
        finally:
            await engine.dispose()

    rows = _run(go())
    assert rows == []


def test_gate4_roster_excludes_rejected() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.classroom_roster(session, _REJECTED_ONLY_CLASSROOM)
        finally:
            await engine.dispose()

    rows = _run(go())
    assert rows == []


# ==========================================================================================
# Gate 5 -- teacher_owns_classroom.
# ==========================================================================================


def test_gate5_owner_matches() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.teacher_owns_classroom(
                    session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_CLASSROOM
                )
        finally:
            await engine.dispose()

    assert _run(go()) is True


def test_gate5_wrong_teacher_is_false() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.teacher_owns_classroom(
                    session, _OTHER_TEACHER, _APPROVED_CLASSROOM
                )
        finally:
            await engine.dispose()

    assert _run(go()) is False


def test_gate5_nonexistent_classroom_is_false() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.teacher_owns_classroom(
                    session, _APPROVED_CLASSROOM_TEACHER, _NONEXISTENT_CLASSROOM
                )
        finally:
            await engine.dispose()

    assert _run(go()) is False


def test_a_deleted_classroom_disappears_from_every_classroom_reader_and_guard() -> None:
    """Student-app migration 20260914_0009: a teacher's soft delete sets `deleted_at_utc` and
    keeps the row. Each classroom reader and guard must treat it as gone.

    The delete is made inside a transaction that is ROLLED BACK -- this suite never commits a
    write to a student-app table. The membership is left APPROVED on purpose (the real delete
    would make it REMOVED), so the guards are shown to filter on the deletion itself rather than
    relying on the membership state alone."""

    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                before = (
                    await data_access.teacher_owns_classroom(session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_CLASSROOM),
                    _APPROVED_CLASSROOM in {r.classroom_id for r in await data_access.classrooms_for_teacher(session, _APPROVED_CLASSROOM_TEACHER)},
                    await data_access.learner_visible_to_teacher(session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_LEARNER),
                    await data_access.classroom_for_learner(session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_LEARNER) is not None,
                )
                await session.execute(
                    text(
                        "UPDATE classrooms SET deleted_at_utc = now(), deleted_by_user_id = "
                        "(SELECT user_id FROM teacher_profiles WHERE teacher_profile_id = :t) "
                        "WHERE classroom_id = :c"
                    ),
                    {"t": _APPROVED_CLASSROOM_TEACHER, "c": _APPROVED_CLASSROOM},
                )
                after = (
                    await data_access.teacher_owns_classroom(session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_CLASSROOM),
                    _APPROVED_CLASSROOM in {r.classroom_id for r in await data_access.classrooms_for_teacher(session, _APPROVED_CLASSROOM_TEACHER)},
                    await data_access.learner_visible_to_teacher(session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_LEARNER),
                    await data_access.classroom_for_learner(session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_LEARNER) is not None,
                )
                await session.rollback()
        finally:
            await engine.dispose()
        return before, after

    before, after = _run(go())
    assert before == (True, True, True, True)
    assert after == (False, False, False, False)


# ==========================================================================================
# Gate 6 -- learner_visible_to_teacher, the cross-tenant case.
# ==========================================================================================


def test_gate6_owning_teacher_sees_learner() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.learner_visible_to_teacher(
                    session, _APPROVED_CLASSROOM_TEACHER, _APPROVED_LEARNER
                )
        finally:
            await engine.dispose()

    assert _run(go()) is True


def test_gate6_cross_tenant_is_false() -> None:
    """The one that leaks a child's data if wrong: a learner APPROVED in a DIFFERENT
    teacher's classroom must not be visible to `_OTHER_TEACHER`."""

    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.learner_visible_to_teacher(
                    session, _OTHER_TEACHER, _APPROVED_LEARNER
                )
        finally:
            await engine.dispose()

    assert _run(go()) is False


def test_gate6_nonexistent_learner_is_false() -> None:
    from app.application import data_access

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                return await data_access.learner_visible_to_teacher(
                    session, _APPROVED_CLASSROOM_TEACHER, _NONEXISTENT_LEARNER
                )
        finally:
            await engine.dispose()

    assert _run(go()) is False


# ==========================================================================================
# Gate 3 -- active_pipeline_run resolves exactly one run; two candidates raise.
# ==========================================================================================


async def _insert_pipeline_run(session, model_version: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO t3_pipeline_runs "
            "(pipeline_run_id, dataset_manifest, model_version, "
            "source_class, source_system, parameter_source_status) "
            "VALUES (:id, '{}'::jsonb, :mv, 'SYNTHETIC', 'b2.4-test', 'test')"
        ),
        {"id": run_id, "mv": model_version},
    )
    return run_id


async def _delete_pipeline_runs(session, run_ids: list[uuid.UUID]) -> None:
    if not run_ids:
        return
    await session.execute(
        text("DELETE FROM t3_pipeline_runs WHERE pipeline_run_id = ANY(:ids)"),
        {"ids": run_ids},
    )


def test_gate3_resolves_exactly_one_run() -> None:
    from app.application import data_access

    model_version = f"b2.4-gate3-single-{uuid.uuid4().hex[:8]}"

    async def go():
        engine, maker = _session_factory()
        run_ids: list[uuid.UUID] = []
        try:
            async with maker() as session:
                run_ids.append(await _insert_pipeline_run(session, model_version))
                await session.commit()

            async with maker() as session:
                row = await data_access.active_pipeline_run(
                    session, active_model_version=model_version
                )
                assert row.pipeline_run_id == run_ids[0]
        finally:
            async with maker() as session:
                await _delete_pipeline_runs(session, run_ids)
                await session.commit()
            await engine.dispose()

    go_ = go()
    _run(go_)


def test_gate3_two_candidates_raise_rather_than_pick_one() -> None:
    from app.application import data_access

    model_version = f"b2.4-gate3-ambiguous-{uuid.uuid4().hex[:8]}"

    async def go():
        engine, maker = _session_factory()
        run_ids: list[uuid.UUID] = []
        try:
            async with maker() as session:
                run_ids.append(await _insert_pipeline_run(session, model_version))
                run_ids.append(await _insert_pipeline_run(session, model_version))
                await session.commit()

            async with maker() as session:
                with pytest.raises(data_access.ActivePipelineRunError):
                    await data_access.active_pipeline_run(
                        session, active_model_version=model_version
                    )
        finally:
            async with maker() as session:
                await _delete_pipeline_runs(session, run_ids)
                await session.commit()
            await engine.dispose()

    _run(go())


def test_gate3_zero_candidates_raise() -> None:
    from app.application import data_access

    model_version = f"b2.4-gate3-missing-{uuid.uuid4().hex[:8]}"

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                with pytest.raises(data_access.ActivePipelineRunError):
                    await data_access.active_pipeline_run(
                        session, active_model_version=model_version
                    )
        finally:
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 2 -- a t3_* read returns rows; applying source_class = 'REAL' to the same query
# returns ZERO. Proves the two provenance rules are genuinely distinct.
# ==========================================================================================


def test_gate2_t3_read_returns_rows_but_real_filter_zeroes_it() -> None:
    from app.application import data_access

    model_version = f"b2.4-gate2-{uuid.uuid4().hex[:8]}"
    student_id = _APPROVED_LEARNER  # any real b_learners.learner_id satisfies the FK

    async def go():
        engine, maker = _session_factory()
        run_id: uuid.UUID | None = None
        try:
            async with maker() as session:
                run_id = await _insert_pipeline_run(session, model_version)
                await session.execute(
                    text(
                        "INSERT INTO t3_panel "
                        "(student_id, intervention_session_number, "
                        "intervention_session_date, b_present, c_present, "
                        "source_class, source_system, parameter_source_status, "
                        "pipeline_run_id) "
                        "VALUES (:sid, 1, CURRENT_DATE, true, false, "
                        "'SYNTHETIC', 'b2.4-test', 'test', :run_id)"
                    ),
                    {"sid": student_id, "run_id": run_id},
                )
                await session.commit()

            # (a) the t3 reader this module ships: no source_class filter -- returns the row.
            async with maker() as session:
                rows = await data_access.panel_rows_for_run(session, run_id)
            assert len(rows) == 1, "t3 reader without source_class filter must return the row"

            # (b) applying the STUDENT-APP rule to this table returns zero -- proving the
            # two rules are distinct, not proving data_access does this (it never does).
            async with maker() as session:
                zeroed = (
                    await session.execute(
                        text(
                            "SELECT 1 FROM t3_panel WHERE pipeline_run_id = :run_id "
                            "AND source_class = 'REAL'"
                        ),
                        {"run_id": run_id},
                    )
                ).all()
            assert zeroed == [], (
                "t3_panel rows are SYNTHETIC by design; source_class = 'REAL' must return "
                "zero rows here, or this test (and the module's own separation) is wrong"
            )
        finally:
            async with maker() as session:
                if run_id is not None:
                    await session.execute(
                        text("DELETE FROM t3_panel WHERE pipeline_run_id = :run_id"),
                        {"run_id": run_id},
                    )
                    await _delete_pipeline_runs(session, [run_id])
                await session.commit()
            await engine.dispose()

    _run(go())
