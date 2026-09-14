"""The shared async engine and session factory -- work order B2.2.

Gate 6 lives here: a pooler URL (port 6543, or a `pooler` hostname) must produce an engine
that will call asyncpg with `statement_cache_size=0`, and a direct 5432 URL must not.

The assertion is deliberately made on the **connect parameters the driver will actually
receive**, not on `NormalisedUrl` -- `test_db_url.py` already covers that dataclass, and it
was precisely the gap between "the normaliser computed the right thing" and "the engine was
built with it" that hid a `TypeError` here: `prepared_statement_cache_size` is a *DBAPI*
argument in SQLAlchemy's asyncpg dialect, so passing it to `create_async_engine` as a
keyword raises `Invalid argument(s)`. A test that stopped at the dataclass would have
passed against an engine that could not be constructed at all.

No connection is opened anywhere in this module: SQLAlchemy builds engines lazily.
"""

from __future__ import annotations

import ssl

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: E402

from app.infrastructure.db import engine as db_engine  # noqa: E402
from app.infrastructure.db_url import InvalidDatabaseUrl  # noqa: E402

_PW = "s3cr3t-p@ss"
_DIRECT = f"postgresql://appuser:{_PW}@db.example.supabase.co:5432/postgres"
_POOLER_PORT = f"postgresql://appuser:{_PW}@db.example.supabase.co:6543/postgres"
_POOLER_HOST = f"postgresql://appuser:{_PW}@aws-0-eu-west-2.pooler.supabase.com:5432/postgres"


def _driver_connect_params(engine: AsyncEngine) -> dict:
    """The exact kwargs SQLAlchemy will hand the asyncpg DBAPI for this engine.

    SQLAlchemy exposes no public accessor for the merged `create_connect_args` +
    `connect_args` dict; it is captured in the pool creator's closure. Reaching for it is
    the only way to assert on what the driver really gets rather than on what we hoped we
    passed. If a future SQLAlchemy moves it, this helper fails loudly (below) instead of
    silently asserting nothing.
    """

    for cell in engine.sync_engine.pool._creator.__closure__ or ():
        contents = cell.cell_contents
        if isinstance(contents, dict) and "host" in contents:
            return contents
    raise AssertionError(
        "could not find the merged connect parameters in the pool creator closure; "
        "SQLAlchemy's internals moved and this gate is no longer asserting anything"
    )


# --------------------------------------------------------------------------------------
# Gate 6: prepared-statement caching off for the pooler, untouched for a direct connection
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", [_POOLER_PORT, _POOLER_HOST], ids=["port-6543", "pooler-host"])
def test_pooler_engine_disables_both_statement_caches(url: str) -> None:
    params = _driver_connect_params(db_engine._build_engine(url))

    # asyncpg's own cache.
    assert params["statement_cache_size"] == 0
    # SQLAlchemy's statement-cache emulation, delivered as a DBAPI argument.
    assert params["prepared_statement_cache_size"] == 0


def test_direct_engine_leaves_the_statement_cache_alone() -> None:
    params = _driver_connect_params(db_engine._build_engine(_DIRECT))

    assert "statement_cache_size" not in params
    assert "prepared_statement_cache_size" not in params


def test_the_engine_can_actually_be_constructed_for_a_pooler_url() -> None:
    """Regression: `prepared_statement_cache_size` is not a `create_engine()` keyword.

    Passing `NormalisedUrl.dialect_kwargs` straight to `create_async_engine` raises
    `TypeError: Invalid argument(s) 'prepared_statement_cache_size'`, which no test that
    stops at the normaliser can see.
    """

    assert isinstance(db_engine._build_engine(_POOLER_PORT), AsyncEngine)


def test_pooler_engine_carries_no_password_in_its_log_target(caplog) -> None:
    import logging

    with caplog.at_level(logging.INFO):
        db_engine._build_engine(_POOLER_PORT)
    for record in caplog.records:
        assert _PW not in record.getMessage()
        assert _PW not in str(getattr(record, "target", ""))


# --------------------------------------------------------------------------------------
# The SSL translation reaches the driver on the API path too
# --------------------------------------------------------------------------------------
def test_sslmode_require_reaches_the_driver_as_a_non_verifying_context() -> None:
    params = _driver_connect_params(db_engine._build_engine(f"{_DIRECT}?sslmode=require"))

    ctx = params["ssl"]
    assert ctx is not True
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode is ssl.CERT_NONE


def test_sslmode_verify_full_reaches_the_driver_as_verifying() -> None:
    params = _driver_connect_params(db_engine._build_engine(f"{_DIRECT}?sslmode=verify-full"))
    assert params["ssl"] is True


# --------------------------------------------------------------------------------------
# The direct-connection shape used by the two CLI entry points
# --------------------------------------------------------------------------------------
def test_create_direct_engine_returns_a_redacted_target() -> None:
    engine, target = db_engine.create_direct_engine(_DIRECT)

    assert isinstance(engine, AsyncEngine)
    assert _PW not in target
    assert target == "postgresql+asyncpg://***:***@db.example.supabase.co:5432/postgres"


@pytest.mark.parametrize("url", [_POOLER_PORT, _POOLER_HOST], ids=["port-6543", "pooler-host"])
def test_create_direct_engine_refuses_the_pooler(url: str) -> None:
    """The CLI callers do bulk writes. `assert_direct_connection` must still fire after
    the B2.2 repoint -- this is the rail that keeps Alembic and the loader off 6543."""

    with pytest.raises(Exception) as excinfo:
        db_engine.create_direct_engine(url)
    assert _PW not in str(excinfo.value)


def test_create_direct_engine_does_not_disable_the_statement_cache() -> None:
    """It is on the direct connection, so the cache is a win, not a hazard. This also
    pins that the CLI callers' engine shape is unchanged by the repoint."""

    engine, _ = db_engine.create_direct_engine(_DIRECT)
    params = _driver_connect_params(engine)
    assert "statement_cache_size" not in params
    assert "prepared_statement_cache_size" not in params


def test_create_direct_engine_rejects_a_nonsense_sslmode_without_echoing_it() -> None:
    with pytest.raises(InvalidDatabaseUrl) as excinfo:
        db_engine.create_direct_engine(f"{_DIRECT}?sslmode={_PW}")
    assert _PW not in str(excinfo.value)


# --------------------------------------------------------------------------------------
# Secret scrubbing (trap 4)
# --------------------------------------------------------------------------------------
def test_scrub_secret_removes_the_engine_password_from_a_driver_message(monkeypatch) -> None:
    monkeypatch.setattr(db_engine, "_engine_source_url", _DIRECT)
    leaked = f"connection to server failed: postgresql://appuser:{_PW}@host:5432/postgres"

    scrubbed = db_engine.scrub_secret(leaked)

    assert _PW not in scrubbed
    assert "***" in scrubbed


def test_scrub_secret_also_removes_the_percent_decoded_form(monkeypatch) -> None:
    """asyncpg is handed the DECODED password, so an exception can quote either form."""

    monkeypatch.setattr(
        db_engine, "_engine_source_url", "postgresql://u:p%40ss@h:5432/db"
    )
    assert "p@ss" not in db_engine.scrub_secret("auth failed for password p@ss")
    assert "p%40ss" not in db_engine.scrub_secret("auth failed for password p%40ss")
