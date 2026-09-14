"""`resolve_principal` (work order B2.3) -- gates 4-7 and 9, plus mutation test 13b/13c targets.

Runs against an isolated, private, in-memory SQLite database (`aiosqlite`) built from a
minimal replica of the three shadow tables (`app_users`, `teacher_profiles`,
`t3_teacher_bindings`) that `app.application.principal_resolution` reads and writes. This is
DELIBERATE, not a shortcut around a live-DB requirement: gate 7 needs a TEST-provenance
`teacher_profiles` row to prove the REAL-only filter, and this project's live `upadya_test`
database currently has zero non-REAL teacher rows (verified: 49/49 REAL) -- inserting one
into the SHARED `teacher_profiles` table (even from a test, even cleaned up afterward) would
be exactly the kind of write to a student-app table rule 5 forbids Component 3's own code
from doing, and this suite avoids it by never touching the shared database at all. Gates that
DO need the real shared schema and real REAL-provenance rows (5, 6, and the live counterparts
of 4 and 9) live in `tests/test_principal_resolution_live.py` against `T3_LIVE_DB_URL`.

The schema replicated here matches `app/infrastructure/db/models.py`'s shadow tables and
`migrations/versions/0008_teacher_bindings.py` closely enough to exercise the real SQL this
module issues (the `source_class = 'REAL'` filters, the `UNIQUE` constraint on
`teacher_profile_id`) without depending on a live Postgres server. `teacher_profile_id` /
`user_id` columns are genuine UUID strings (not arbitrary text) because the ORM columns this
module queries through (`app/infrastructure/db/models.py`'s `PgUUID(as_uuid=True)` columns)
expect that shape even against the SQLite dialect used here.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application import principal_resolution as pr
from app.domain.errors import DemoPoolExhaustedError, PrincipalNotAuthorizedError
from app.domain.principal import VerifiedClaims
from app.infrastructure.db.models import app_users as app_users_table
from app.infrastructure.db.models import teacher_profiles as teacher_profiles_table

pytest.importorskip("aiosqlite")

_SCHEMA = """
CREATE TABLE app_users (
    user_id TEXT PRIMARY KEY,
    supabase_subject TEXT,
    profile_type TEXT,
    source_class TEXT
);
CREATE TABLE teacher_profiles (
    teacher_profile_id TEXT PRIMARY KEY,
    user_id TEXT,
    source_class TEXT
);
CREATE TABLE t3_teacher_bindings (
    supabase_subject TEXT PRIMARY KEY,
    teacher_profile_id TEXT NOT NULL UNIQUE,
    created_at_utc TEXT,
    updated_at_utc TEXT,
    source_class TEXT NOT NULL,
    source_system TEXT NOT NULL,
    parameter_source_status TEXT NOT NULL,
    pipeline_run_id TEXT NOT NULL
);
"""

# Fixed, readable UUIDs for fixture rows -- real UUID shape, not arbitrary text (see module
# docstring: the ORM columns this module queries through expect it even on SQLite).
U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"
U3 = "33333333-3333-3333-3333-333333333333"
TP1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TP2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TP_TEST = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TP_UNTOUCHED = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _run(coro):
    return asyncio.run(coro)


async def _fresh_engine():
    # A unique in-memory DB per call (`uri=true` + a random name) so tests never share state.
    name = f"file:pr_{uuid.uuid4().hex}?mode=memory&cache=shared"
    engine = create_async_engine(f"sqlite+aiosqlite:///{name}?uri=true")
    async with engine.begin() as conn:
        for statement in _SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))
    return engine


class _FakeSettings:
    def __init__(self, *, t3_demo_mode: bool, t3_demo_teacher_pool: list[str]):
        self.t3_demo_mode = t3_demo_mode
        self.t3_demo_teacher_pool = t3_demo_teacher_pool


async def _seed(session, *, app_user=None, teacher_profile=None) -> None:
    # Deliberately via the ORM `Table` objects (`app_users`/`teacher_profiles` from
    # `app/infrastructure/db/models.py`), NOT raw `text()` INSERTs: those tables' id columns
    # are typed `postgresql.UUID(as_uuid=True)`, whose bind processor is emulated (non-native)
    # on SQLite and stores a uuid.UUID's *32-char hex, no dashes* form -- different from a
    # dashed-string literal inserted via raw SQL. The app code under test always reads these
    # columns back through the same ORM Table objects (`principal_resolution.py`'s
    # `teacher_profiles.c...` selects), so seeding through the ORM too keeps both sides using
    # the same UUID representation; seeding via raw dashed-string text() silently produced a
    # row the app's own `WHERE teacher_profile_id IN (...)` / `== ...` could never match.
    if app_user is not None:
        await session.execute(
            insert(app_users_table).values(
                user_id=uuid.UUID(app_user["user_id"]),
                supabase_subject=app_user["subject"],
                profile_type=app_user["profile_type"],
                source_class=app_user["source_class"],
            )
        )
    if teacher_profile is not None:
        await session.execute(
            insert(teacher_profiles_table).values(
                teacher_profile_id=uuid.UUID(teacher_profile["teacher_profile_id"]),
                user_id=uuid.UUID(teacher_profile["user_id"]),
                source_class=teacher_profile["source_class"],
            )
        )
    await session.commit()


def _claims(subject: str, *, is_anonymous: bool = False) -> VerifiedClaims:
    return VerifiedClaims(subject=subject, is_anonymous=is_anonymous)


# ==========================================================================================
# Gate 4 -- a valid token whose sub has no app_users row -> 403, no row count change.
# ==========================================================================================


def test_gate4_missing_app_users_row_is_403_no_insert() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
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
                        _claims("no-such-subject"),
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


def test_gate4_non_teacher_profile_type_is_403() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    app_user={
                        "user_id": U1,
                        "subject": "learner-subject",
                        "profile_type": "LEARNER",
                        "source_class": "REAL",
                    },
                )
                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session,
                        _claims("learner-subject"),
                        _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=[]),
                    )
        finally:
            await engine.dispose()

    _run(go())


def test_gate4_test_provenance_app_user_is_403() -> None:
    """A TEST-class app_users row must never authorize -- the REAL filter, not just presence."""

    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    app_user={
                        "user_id": U1,
                        "subject": "test-fixture-subject",
                        "profile_type": "TEACHER",
                        "source_class": "TEST",
                    },
                )
                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session,
                        _claims("test-fixture-subject"),
                        _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=[]),
                    )
        finally:
            await engine.dispose()

    _run(go())


def test_real_path_resolves_to_teacher_profile_id() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    app_user={
                        "user_id": U1,
                        "subject": "teacher-subject",
                        "profile_type": "TEACHER",
                        "source_class": "REAL",
                    },
                    teacher_profile={
                        "teacher_profile_id": TP1,
                        "user_id": U1,
                        "source_class": "REAL",
                    },
                )
                principal = await pr.resolve_principal(
                    session,
                    _claims("teacher-subject"),
                    _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=[]),
                )
            assert str(principal.teacher_profile_id) == TP1
            assert principal.resolution == "real"
        finally:
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 5 -- demo mode: first call claims + inserts one row; second call is idempotent.
# ==========================================================================================


def test_gate5_first_call_claims_second_call_is_idempotent() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    teacher_profile={
                        "teacher_profile_id": TP1,
                        "user_id": U3,
                        "source_class": "REAL",
                    },
                )
                settings = _FakeSettings(t3_demo_mode=True, t3_demo_teacher_pool=[TP1])

                before = (
                    await session.execute(text("SELECT COUNT(*) FROM t3_teacher_bindings"))
                ).scalar_one()
                assert before == 0

                first = await pr.resolve_principal(
                    session, _claims("anon-subject-1", is_anonymous=True), settings
                )
                after_first = (
                    await session.execute(text("SELECT COUNT(*) FROM t3_teacher_bindings"))
                ).scalar_one()
                assert after_first == 1
                assert str(first.teacher_profile_id) == TP1

                second = await pr.resolve_principal(
                    session, _claims("anon-subject-1", is_anonymous=True), settings
                )
                after_second = (
                    await session.execute(text("SELECT COUNT(*) FROM t3_teacher_bindings"))
                ).scalar_one()
                assert after_second == 1, "second call must not insert a new row"
                assert second.teacher_profile_id == first.teacher_profile_id
        finally:
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 6 -- two different anonymous subjects get two different teachers; exhausted -> 409.
# ==========================================================================================


def test_gate6_two_subjects_get_different_teachers_then_pool_exhausted() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    teacher_profile={
                        "teacher_profile_id": TP1,
                        "user_id": U1,
                        "source_class": "REAL",
                    },
                )
                await session.execute(
                    insert(teacher_profiles_table).values(
                        teacher_profile_id=uuid.UUID(TP2),
                        user_id=uuid.UUID(U2),
                        source_class="REAL",
                    )
                )
                await session.commit()

                settings = _FakeSettings(t3_demo_mode=True, t3_demo_teacher_pool=[TP1, TP2])

                first = await pr.resolve_principal(
                    session, _claims("anon-1", is_anonymous=True), settings
                )
                second = await pr.resolve_principal(
                    session, _claims("anon-2", is_anonymous=True), settings
                )
                assert first.teacher_profile_id != second.teacher_profile_id
                assert {str(first.teacher_profile_id), str(second.teacher_profile_id)} == {
                    TP1,
                    TP2,
                }

                with pytest.raises(DemoPoolExhaustedError) as excinfo:
                    await pr.resolve_principal(
                        session, _claims("anon-3", is_anonymous=True), settings
                    )
                assert excinfo.value.error_code == "demo_pool_exhausted"
        finally:
            await engine.dispose()

    _run(go())


def test_gate6_empty_pool_is_409_not_500() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                with pytest.raises(DemoPoolExhaustedError) as excinfo:
                    await pr.resolve_principal(
                        session,
                        _claims("anon-lonely", is_anonymous=True),
                        _FakeSettings(t3_demo_mode=True, t3_demo_teacher_pool=[]),
                    )
                assert excinfo.value.error_code == "demo_pool_exhausted"
        finally:
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 7 -- a pool entry referencing a non-REAL teacher_profile_id is rejected as a candidate.
#
# DECISION (stated per the work order): enforced at CLAIM TIME, not at startup. `settings.py`
# validates only that pool entries are well-formed UUIDs (fail-fast on a typo); it does not
# reach into the database to check `source_class`, because `get_settings()` is required to be
# import-safe/side-effect-free with respect to the database. Candidate filtering to REAL-only
# happens in `principal_resolution.real_candidate_teacher_ids`, called from
# `_claim_demo_teacher` before any INSERT is attempted, so a TEST-provenance pool entry is
# silently skipped -- never a 500, never a bound teacher, never an inserted row referencing it.
# ==========================================================================================


def test_gate7_non_real_pool_entry_is_never_claimed() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    teacher_profile={
                        "teacher_profile_id": TP_TEST,
                        "user_id": U1,
                        "source_class": "TEST",
                    },
                )
                settings = _FakeSettings(t3_demo_mode=True, t3_demo_teacher_pool=[TP_TEST])
                with pytest.raises(DemoPoolExhaustedError):
                    await pr.resolve_principal(
                        session, _claims("anon-vs-test-pool", is_anonymous=True), settings
                    )
                count = (
                    await session.execute(text("SELECT COUNT(*) FROM t3_teacher_bindings"))
                ).scalar_one()
                assert count == 0, "a TEST-provenance candidate must never be inserted"
        finally:
            await engine.dispose()

    _run(go())


def test_gate7_real_candidates_filtered_correctly() -> None:
    """Direct unit test of the filter helper itself: REAL passes, TEST is dropped, order kept."""

    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await session.execute(
                    insert(teacher_profiles_table),
                    [
                        {
                            "teacher_profile_id": uuid.UUID(TP1),
                            "user_id": uuid.UUID(U1),
                            "source_class": "REAL",
                        },
                        {
                            "teacher_profile_id": uuid.UUID(TP_TEST),
                            "user_id": uuid.UUID(U2),
                            "source_class": "TEST",
                        },
                    ],
                )
                await session.commit()
                result = await pr.real_candidate_teacher_ids(
                    session, [uuid.UUID(TP_TEST), uuid.UUID(TP1)]
                )
            assert [str(r) for r in result] == [TP1]
        finally:
            await engine.dispose()

    _run(go())


# ==========================================================================================
# Gate 9 -- T3_DEMO_MODE=false: an anonymous token is refused entirely; demo code unreached.
# ==========================================================================================


def test_gate9_anonymous_with_demo_mode_off_is_403_and_claims_no_binding() -> None:
    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                await _seed(
                    session,
                    teacher_profile={
                        "teacher_profile_id": TP_UNTOUCHED,
                        "user_id": U1,
                        "source_class": "REAL",
                    },
                )
                settings = _FakeSettings(
                    t3_demo_mode=False, t3_demo_teacher_pool=[TP_UNTOUCHED]
                )
                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session, _claims("anon-blocked", is_anonymous=True), settings
                    )
                count = (
                    await session.execute(text("SELECT COUNT(*) FROM t3_teacher_bindings"))
                ).scalar_one()
                assert count == 0
        finally:
            await engine.dispose()

    _run(go())


def test_gate9_demo_claim_function_is_never_called_when_demo_mode_off(monkeypatch) -> None:
    """Asserts the demo claiming code path is provably unreached, not merely "happens to
    leave no row" -- patches `_claim_demo_teacher` to raise if it is ever invoked."""

    async def _boom(*args, **kwargs):
        raise AssertionError("_claim_demo_teacher must not run when T3_DEMO_MODE is off")

    monkeypatch.setattr(pr, "_claim_demo_teacher", _boom)

    async def go():
        engine = await _fresh_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session,
                        _claims("anon-patched", is_anonymous=True),
                        _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=[]),
                    )
        finally:
            await engine.dispose()

    _run(go())
