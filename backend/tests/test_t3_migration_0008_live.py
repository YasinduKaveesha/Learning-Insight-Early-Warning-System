"""Live migration-reversibility gate for `t3_teacher_bindings` (work order B2.3, gate 1).

Runs the actual Alembic upgrade/downgrade/upgrade sequence against the disposable
`upadya_test` database (never `upadya` -- `tests/_live_db_target_guard.assert_safe_and_
reachable_live_target` enforces that before a single Alembic command runs), then asserts the
table is present/absent/present by reflecting the live schema. This is a COMMITTED, RUNNABLE
test file, not a manual CLI demo: it executes automatically whenever `T3_LIVE_DB_URL` is set
and skips cleanly otherwise, matching every other live-DB gate in this suite.

Uses Alembic's own `Config`/`command` API (not a subprocess) so failures surface as normal
pytest assertions/exceptions rather than being swallowed in captured subprocess output.
`sys.argv`/`os.environ["DATABASE_URL"]` are untouched by this file outside the one call that
needs it -- `env.py` reads `DATABASE_URL` (or `T3_LIVE_DB_URL` as a migrations-only fallback
here), so this module sets `DATABASE_URL` for the duration of each Alembic call only, via a
context manager that always restores whatever was there before (including "unset").

Ends by leaving the database at `head` (0008 present) regardless of pass/fail, via a
module-scoped fixture's `finally`, so a failed run does not leave `upadya_test` stuck one
migration behind for the next test file in the suite.
"""

from __future__ import annotations

import contextlib
import os

import pytest

pytest.importorskip("alembic")
sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

import asyncio  # noqa: E402
from pathlib import Path  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432/55432) Postgres URL for upadya_test",
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _sync_url(url: str) -> str:
    """Alembic's `env.py` runs synchronously; strip any `+asyncpg` so the plain
    `postgresql://` driver `psycopg2`/`psycopg` picks up applies, matching how every other
    manual `alembic upgrade` invocation in this project's README is run (a bare
    `postgresql://` URL, not `+asyncpg`)."""

    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@contextlib.contextmanager
def _database_url_env(url: str):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _sync_url(url)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    return cfg


def _table_exists(url: str, table_name: str) -> bool:
    async def go() -> bool:
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://", 1)
            if not url.startswith("postgresql+asyncpg://")
            else url
        )
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda sync_conn: table_name in inspect(sync_conn).get_table_names()
                )
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _restore_head_afterwards():
    """Every test in this module ends with the DB back at `head` (0008 present), pass or
    fail -- this file must never be the reason a later live test in the suite finds the
    schema one migration behind."""

    try:
        yield
    finally:
        with _database_url_env(_LIVE_URL):
            command.upgrade(_alembic_config(), "head")


def test_gate1_upgrade_downgrade_upgrade_round_trip() -> None:
    with _database_url_env(_LIVE_URL):
        cfg = _alembic_config()

        command.upgrade(cfg, "head")
        assert _table_exists(_LIVE_URL, "t3_teacher_bindings") is True, (
            "upgrade head must create t3_teacher_bindings"
        )
        head_revision = command.heads(cfg)  # smoke: does not raise
        del head_revision

        command.downgrade(cfg, "-1")
        assert _table_exists(_LIVE_URL, "t3_teacher_bindings") is False, (
            "downgrade -1 must drop t3_teacher_bindings"
        )

        command.upgrade(cfg, "head")
        assert _table_exists(_LIVE_URL, "t3_teacher_bindings") is True, (
            "a second upgrade head must restore t3_teacher_bindings"
        )
