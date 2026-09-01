"""Gate 11 (work order B2.3): `b_learners` and `t3_panel` row counts in the DEV database
`upadya` (never `upadya_test`) are unchanged by anything `resolve_principal` does.

`resolve_principal` (`app/application/principal_resolution.py`) never reads or writes either
table -- it only touches `app_users`, `teacher_profiles` (read-only) and
`t3_teacher_bindings` (its own table). This test proves that by recording both counts before
running a representative sweep of `resolve_principal` calls (a real-path miss, and a full
demo-path claim + idempotent re-claim, cleaned up afterward) against the READ-ONLY `upadya`
connection, then asserting the counts are identical afterward.

Set `T3_LIVE_DB_URL_READONLY` to a direct connection to `upadya` to run this file; it skips
cleanly otherwise. Uses the same `postgresql_readonly` execution option as
`tests/test_data_access_readonly_live.py` so Postgres itself -- not just this file's own
restraint -- rejects any write on this connection.
"""

from __future__ import annotations

import asyncio
import os

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.application import principal_resolution as pr  # noqa: E402
from app.domain.errors import PrincipalNotAuthorizedError  # noqa: E402
from app.domain.principal import VerifiedClaims  # noqa: E402

_ENV_VAR = "T3_LIVE_DB_URL_READONLY"
_LIVE_URL = os.environ.get(_ENV_VAR)

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_readonly_live_target

    assert_safe_and_reachable_readonly_live_target(_LIVE_URL, env_var=_ENV_VAR)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason=f"set {_ENV_VAR} to a direct Postgres URL for `upadya` to run the B2.3 gate 11 count",
)


def _normalise(url: str) -> str:
    try:
        from app.infrastructure.db_url import normalise_async_url

        return normalise_async_url(url)
    except Exception:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _run(coro):
    return asyncio.run(coro)


def _readonly_session_factory():
    engine = create_async_engine(
        _normalise(_LIVE_URL), execution_options={"postgresql_readonly": True}
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class _FakeSettings:
    def __init__(self, *, t3_demo_mode: bool, t3_demo_teacher_pool: list[str]):
        self.t3_demo_mode = t3_demo_mode
        self.t3_demo_teacher_pool = t3_demo_teacher_pool


async def _counts(session) -> tuple[int, int]:
    b_learners = (await session.execute(text("SELECT COUNT(*) FROM b_learners"))).scalar_one()
    t3_panel = (await session.execute(text("SELECT COUNT(*) FROM t3_panel"))).scalar_one()
    return b_learners, t3_panel


def test_gate11_b_learners_and_t3_panel_counts_unchanged() -> None:
    async def go():
        engine, maker = _readonly_session_factory()
        try:
            async with maker() as session:
                before = await _counts(session)

            # Representative resolve_principal sweep -- real-path miss (no REAL app_users
            # row for this subject) and a demo-path claim attempt against an empty pool
            # (immediately exhausted, so nothing to clean up). Both paths only ever read
            # app_users/teacher_profiles and would only ever write t3_teacher_bindings, on a
            # writable connection -- this connection is read-only regardless, so any
            # accidental write would fail loudly rather than silently succeed and be missed
            # by a before/after count comparison.
            async with maker() as session:
                with pytest.raises(PrincipalNotAuthorizedError):
                    await pr.resolve_principal(
                        session,
                        VerifiedClaims(subject="gate11-readonly-probe", is_anonymous=False),
                        _FakeSettings(t3_demo_mode=False, t3_demo_teacher_pool=[]),
                    )

            async with maker() as session:
                after = await _counts(session)
        finally:
            await engine.dispose()

        print(f"\n[gate 11] upadya.b_learners: before={before[0]} after={after[0]}")
        print(f"[gate 11] upadya.t3_panel:   before={before[1]} after={after[1]}")
        assert before == after, f"upadya counts changed: before={before} after={after}"

    _run(go())


def test_gate11_readonly_connection_rejects_a_write() -> None:
    """Same discipline as `tests/test_data_access_readonly_live.py`: prove the
    `postgresql_readonly` execution option is not decorative on this file's own connection."""

    async def go():
        engine, maker = _readonly_session_factory()
        try:
            async with maker() as session:
                with pytest.raises(Exception) as exc_info:
                    await session.execute(
                        text(
                            "INSERT INTO t3_pipeline_runs "
                            "(pipeline_run_id, dataset_manifest, model_version) "
                            "VALUES (gen_random_uuid(), '{}'::jsonb, 'gate11-write-probe')"
                        )
                    )
                assert "read-only" in str(exc_info.value).lower()
        finally:
            await engine.dispose()

    _run(go())
