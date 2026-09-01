"""Live counterparts of `resolve_principal` gates 4, 5, 6, 9 (work order B2.3).

`tests/test_principal_resolution.py` (in-memory SQLite) already exercises gates 4-7 and 9
against a private replica schema -- deliberately, so gate 7's non-REAL pool entry never has
to be inserted into the SHARED `teacher_profiles` table (see that module's docstring:
`upadya_test` currently has 49/49 REAL teacher_profiles rows and zero non-REAL ones, and
inserting one -- even from a test, even cleaned up afterward -- would be exactly the kind of
write to a student-app table Component 3's own code must never make). This module is the
live counterpart promised by that docstring: gates 5 and 6 (which claim a REAL pool teacher
via this module's OWN `t3_teacher_bindings` table -- never `app_users`/`teacher_profiles`)
and the live re-demonstration of gates 4 and 9 against the real shared schema and real
REAL-provenance rows, rather than the SQLite replica.

Every test here writes only to `t3_teacher_bindings` (Component 3's own table) and always
cleans its own row(s) up in a `finally`, scoped to a subject prefix unique to this file
(`_SUBJECT_PREFIX`) so a concurrent run of the shared `upadya_test` database by another agent
is never touched. `app_users` / `teacher_profiles` are read-only here, exactly as
`principal_resolution.py` itself only ever reads them.

    T3_LIVE_DB_URL=postgresql://upadya:...@127.0.0.1:55432/upadya_test \\
        python -m pytest tests/test_principal_resolution_live.py
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

from app.application import principal_resolution as pr  # noqa: E402
from app.domain.errors import DemoPoolExhaustedError, PrincipalNotAuthorizedError  # noqa: E402
from app.domain.principal import VerifiedClaims  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432/55432) Postgres URL for upadya_test",
)

# Every subject this file inserts starts with this prefix -- cleanup below only ever deletes
# rows matching it, so a concurrent agent's own t3_teacher_bindings rows are never touched.
_SUBJECT_PREFIX = "b2.3-live-test-"


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


def _claims(subject: str, *, is_anonymous: bool = False) -> VerifiedClaims:
    return VerifiedClaims(subject=subject, is_anonymous=is_anonymous)


class _FakeSettings:
    def __init__(self, *, t3_demo_mode: bool, t3_demo_teacher_pool: list[str]):
        self.t3_demo_mode = t3_demo_mode
        self.t3_demo_teacher_pool = t3_demo_teacher_pool


async def _two_real_teacher_pool(session) -> list[str]:
    rows = (
        await session.execute(
            text(
                "SELECT teacher_profile_id FROM teacher_profiles "
                "WHERE source_class = 'REAL' ORDER BY teacher_profile_id LIMIT 2"
            )
        )
    ).all()
    assert len(rows) == 2, "upadya_test must seed at least 2 REAL teacher_profiles rows"
    return [str(row.teacher_profile_id) for row in rows]


async def _delete_bindings(session, subjects: list[str]) -> None:
    if not subjects:
        return
    await session.execute(
        text("DELETE FROM t3_teacher_bindings WHERE supabase_subject = ANY(:subs)"),
        {"subs": subjects},
    )
    await session.commit()


# ==========================================================================================
# Gate 4 (live) -- a valid token whose sub has no REAL app_users row -> 403, no writes.
# ==========================================================================================


def test_gate4_live_missing_app_users_row_is_403_no_writes() -> None:
    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                before_users = (
                    await session.execute(text("SELECT COUNT(*) FROM app_users"))
                ).scalar_one()
                before_teachers = (
                    await session.execute(text("SELECT COUNT(*) FROM teacher_profiles"))
                ).scalar_one()

                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session,
                        _claims(f"{_SUBJECT_PREFIX}gate4-no-such-subject"),
                        _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=[]),
                    )

                after_users = (
                    await session.execute(text("SELECT COUNT(*) FROM app_users"))
                ).scalar_one()
                after_teachers = (
                    await session.execute(text("SELECT COUNT(*) FROM teacher_profiles"))
                ).scalar_one()
            assert before_users == after_users
            assert before_teachers == after_teachers
        finally:
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 5 (live) -- demo mode: first call claims a REAL pool teacher + inserts one row;
# second call for the same subject is idempotent (no second row, same teacher).
# ==========================================================================================


def test_gate5_live_first_call_claims_second_call_is_idempotent() -> None:
    subject = f"{_SUBJECT_PREFIX}gate5-{uuid.uuid4().hex}"

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                pool = await _two_real_teacher_pool(session)
                settings = _FakeSettings(t3_demo_mode=True, t3_demo_teacher_pool=[pool[0]])

                before = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM t3_teacher_bindings "
                            "WHERE supabase_subject = :s"
                        ),
                        {"s": subject},
                    )
                ).scalar_one()
                assert before == 0

                first = await pr.resolve_principal(session, _claims(subject, is_anonymous=True), settings)
                after_first = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM t3_teacher_bindings "
                            "WHERE supabase_subject = :s"
                        ),
                        {"s": subject},
                    )
                ).scalar_one()
                assert after_first == 1
                assert str(first.teacher_profile_id) == pool[0]

                second = await pr.resolve_principal(session, _claims(subject, is_anonymous=True), settings)
                after_second = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM t3_teacher_bindings "
                            "WHERE supabase_subject = :s"
                        ),
                        {"s": subject},
                    )
                ).scalar_one()
                assert after_second == 1, "second call must not insert a new row"
                assert second.teacher_profile_id == first.teacher_profile_id
        finally:
            async with maker() as cleanup_session:
                await _delete_bindings(cleanup_session, [subject])
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 6 (live) -- two different anonymous subjects get two different REAL teachers;
# exhausted pool -> 409 with the distinct machine-readable code.
# ==========================================================================================


def test_gate6_live_two_subjects_get_different_teachers_then_pool_exhausted() -> None:
    subjects = [
        f"{_SUBJECT_PREFIX}gate6-a-{uuid.uuid4().hex}",
        f"{_SUBJECT_PREFIX}gate6-b-{uuid.uuid4().hex}",
        f"{_SUBJECT_PREFIX}gate6-c-{uuid.uuid4().hex}",
    ]

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                pool = await _two_real_teacher_pool(session)
                settings = _FakeSettings(t3_demo_mode=True, t3_demo_teacher_pool=pool)

                first = await pr.resolve_principal(
                    session, _claims(subjects[0], is_anonymous=True), settings
                )
                second = await pr.resolve_principal(
                    session, _claims(subjects[1], is_anonymous=True), settings
                )
                assert first.teacher_profile_id != second.teacher_profile_id
                assert {str(first.teacher_profile_id), str(second.teacher_profile_id)} == set(pool)

                with pytest.raises(DemoPoolExhaustedError) as excinfo:
                    await pr.resolve_principal(
                        session, _claims(subjects[2], is_anonymous=True), settings
                    )
                assert excinfo.value.error_code == "demo_pool_exhausted"

                exhausted_count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM t3_teacher_bindings "
                            "WHERE supabase_subject = :s"
                        ),
                        {"s": subjects[2]},
                    )
                ).scalar_one()
                assert exhausted_count == 0, "an exhausted claim must never insert a row"
        finally:
            async with maker() as cleanup_session:
                await _delete_bindings(cleanup_session, subjects)
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 9 (live) -- T3_DEMO_MODE=false: an anonymous token is refused entirely against the
# real shared schema; no binding row, demo claiming path unreachable.
# ==========================================================================================


def test_gate9_live_anonymous_with_demo_mode_off_is_403_and_claims_no_binding() -> None:
    subject = f"{_SUBJECT_PREFIX}gate9-{uuid.uuid4().hex}"

    async def go():
        engine, maker = _session_factory()
        try:
            async with maker() as session:
                pool = await _two_real_teacher_pool(session)
                settings = _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=pool)

                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session, _claims(subject, is_anonymous=True), settings
                    )

                count = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM t3_teacher_bindings "
                            "WHERE supabase_subject = :s"
                        ),
                        {"s": subject},
                    )
                ).scalar_one()
                assert count == 0
        finally:
            async with maker() as cleanup_session:
                await _delete_bindings(cleanup_session, [subject])
            await engine.dispose()

    _run(go())
