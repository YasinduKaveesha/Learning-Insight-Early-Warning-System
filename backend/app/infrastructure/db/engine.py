"""The one async engine and session factory for Component 3 (work order B2.2).

Before this module every caller that needed a database built its own
``create_async_engine`` -- the loader, the feature-persistence CLI, and (still, by design)
Alembic's ``env.py``. That is how the two normalisation paths in ``db_url`` were able to
drift apart unnoticed. There is now exactly one place that turns a URL into an engine for
the API, and exactly one place that does it for the direct-connection CLI entry points.

Two shapes, deliberately, because the two callers are on different ports:

* :func:`get_engine` / :func:`get_session` -- **the API path.** Built from
  ``settings.api_database_url``, which is the Supabase *transaction pooler* (port 6543) in
  any deployment that sets ``DATABASE_URL_POOLED``. Normalised through
  :func:`app.infrastructure.db_url.normalise_database_url`, so ``sslmode`` becomes a real
  ``ssl.SSLContext`` and a pooler target disables prepared-statement caching.
* :func:`create_direct_engine` -- **the CLI / migration path** (port 5432). Refuses the
  pooler outright via ``assert_direct_connection``. ``t3_loader`` and
  ``feature_persistence`` use this; it is byte-for-byte the engine they used to build
  inline, just in one named place.

Why the two are not merged: forcing the loader onto the API engine would point a bulk
insert at the transaction pooler, which ``migration_guard.assert_direct_connection``
exists specifically to prevent, and would silently disable the statement cache for a
workload that benefits from it. See backend_plan.md section 2.

Import-safe without a database: nothing here connects at import time.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.db_url import (
    normalise_async_url,
    normalise_database_url,
    redact_url,
)
from app.infrastructure.settings import get_settings

__all__ = [
    "check_database_reachable",
    "create_direct_engine",
    "dispose",
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "scrub_secret",
]

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

#: The raw URL the current ``_engine`` was built from. Kept only so :func:`scrub_secret`
#: can strip its password out of a driver exception before it reaches a log or a response
#: body. Never returned, never logged.
_engine_source_url: str | None = None


def _build_engine(raw_url: str) -> AsyncEngine:
    """Create the API engine for ``raw_url``. No I/O -- SQLAlchemy connects lazily."""

    normalised = normalise_database_url(raw_url)

    # `prepared_statement_cache_size` is a DBAPI argument, NOT a `create_engine()` kwarg:
    # SQLAlchemy's asyncpg dialect pops it inside `AsyncAdapt_asyncpg_dbapi.connect`
    # (asyncpg.py, "Prepared Statement Cache"). Passing it to `create_async_engine`
    # directly raises `TypeError: Invalid argument(s) 'prepared_statement_cache_size'`.
    # `NormalisedUrl` keeps it in a separate bucket because the two caches are different
    # things -- asyncpg's own (`statement_cache_size`) and SQLAlchemy's emulation layer's --
    # but both are delivered the same way, so they are merged here.
    connect_args = dict(normalised.connect_args)
    connect_args.update(normalised.dialect_kwargs)

    if normalised.pooler_detected:
        # Both caches are now 0. The transaction pooler multiplexes many clients onto few
        # server connections, so a prepared statement created on one checkout is gone on
        # the next. The symptom is an INTERMITTENT `InvalidSQLStatementNameError` /
        # `prepared statement "__asyncpg_stmt_x__" does not exist` under concurrency -- not
        # a clean failure at startup, which is the worst way to find out.
        # (backend_plan.md section 2, trap 2.)
        logger.info(
            "API engine target is the transaction pooler; prepared-statement caching "
            "disabled",
            extra={"target": redact_url(normalised.async_url)},
        )
    else:
        logger.info(
            "API engine target is a direct connection",
            extra={"target": redact_url(normalised.async_url)},
        )

    return create_async_engine(
        normalised.async_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


def get_engine() -> AsyncEngine:
    """The process-wide API engine, created on first use."""

    global _engine, _engine_source_url

    if _engine is None:
        raw_url = get_settings().api_database_url
        _engine = _build_engine(raw_url)
        _engine_source_url = raw_url
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """The process-wide session factory, created on first use."""

    global _sessionmaker

    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session and always close it.

    Does not commit. Component 3's read endpoints are read-only (rule 6); the few writing
    paths manage their own ``session.begin()`` block, the same discipline ``t3_loader``
    and ``feature_persistence`` already follow.
    """

    async with get_sessionmaker()() as session:
        yield session


async def dispose() -> None:
    """Close the engine's pool and forget it. Called from the app lifespan on shutdown.

    Resetting the module state (rather than only disposing) matters for tests: each
    ``TestClient`` builds a fresh app with its own settings, and a stale engine here would
    silently serve the previous test's ``DATABASE_URL``.
    """

    global _engine, _sessionmaker, _engine_source_url

    engine, _engine, _sessionmaker, _engine_source_url = _engine, None, None, None
    if engine is not None:
        await engine.dispose()


def scrub_secret(message: str) -> str:
    """Remove the live database password from ``message``.

    A driver exception can quote the connection string it failed on, and that string
    carries a real credential. Anything derived from an exception must pass through here
    before it reaches a response body or a log line (trap 4).
    """

    from urllib.parse import unquote, urlsplit

    source = _engine_source_url
    if not source:
        # The engine may have failed before it was ever assigned (an unparseable URL, or a
        # constructor error). The credential still exists in settings, so still scrub it.
        try:
            source = get_settings().api_database_url
        except Exception:  # pragma: no cover - settings already failed fast at startup
            return message

    password = urlsplit(source).password
    if not password:
        return message

    for variant in {password, unquote(password)}:
        if variant:
            message = message.replace(variant, "***")
    return message


async def check_database_reachable() -> None:
    """Run ``SELECT 1`` on the shared engine. Raises on any failure -- never swallows.

    A readiness probe that catches its own exception and reports ready is worse than no
    probe at all: it converts a hard outage into a silent one. The caller
    (``/health/ready``) is the only place allowed to catch this, and it answers 503.
    """

    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT 1"))
        if result.scalar_one() != 1:  # pragma: no cover - a server that answers wrongly
            raise RuntimeError("database answered SELECT 1 with an unexpected value")


# ======================================================================================
# The direct-connection (port 5432) path used by the CLI entry points.
# ======================================================================================


def create_direct_engine(raw_url: str) -> tuple[AsyncEngine, str]:
    """Build an engine on the **direct** connection and return it with a redacted target.

    Refuses the transaction pooler outright (``assert_direct_connection``). This is what
    ``python -m app.application.t3_loader`` and
    ``python -m app.application.feature_persistence`` run on: bulk writes, on 5432, with
    the prepared-statement cache left at its default because there is no pooler in the way.

    Unlike :func:`get_engine` this is NOT process-wide -- each CLI invocation owns and
    disposes its engine, and each ``asyncio.run`` needs its own (asyncpg connections are
    bound to the loop that created them).
    """

    # Imported here, not at module scope: `migration_guard` imports from `db_url`, and
    # keeping this local avoids tying the API engine's import graph to the Alembic rails.
    from app.infrastructure.migration_guard import assert_direct_connection

    url = normalise_async_url(raw_url)
    assert_direct_connection(url)
    return create_async_engine(url, poolclass=None), redact_url(url)
