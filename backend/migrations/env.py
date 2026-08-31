"""Component 3 Alembic environment -- async PostgreSQL, with safety rails.

Component 3 shares one database with the live student app. Two settings on every
``context.configure(...)`` call below keep the two migration chains apart:

* ``version_table="t3_alembic_version"`` -- Component 3 never reads or writes the default
  ``alembic_version`` table, which the student app owns.
* ``include_object=component3_include_object`` -- autogenerate and upgrade only ever see
  objects whose name starts with ``t3_``. Everything else in the database is invisible to
  this chain, so no student-app table can be dropped by a Component 3 migration.

The configured URL is taken from ``DATABASE_URL`` and refused if it resolves to the
Supabase transaction pooler (port 6543 / ``pooler`` host) -- migrations run on the direct
connection only (backend_plan.md section 2).
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.infrastructure.migration_guard import (  # noqa: E402
    OWNED_VERSION_TABLE,
    assert_direct_connection,
    component3_include_object,
    normalise_async_url,
    redact_url,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Component 3 owns zero tables at B3.1. An empty MetaData (rather than None) still lets
# `--autogenerate` run -- it compares nothing against the whole database, and
# `component3_include_object` filters every student-app object out of the diff. That is the
# guard-check demonstration.
target_metadata = MetaData()

_BANNER_SHOWN = False


def _resolved_url() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is not set. Component 3's Alembic has no database to target; "
            "refusing to fall back to the alembic.ini placeholder."
        )
    url = normalise_async_url(raw)
    assert_direct_connection(url)
    return url


def _print_target_banner(url: str) -> None:
    global _BANNER_SHOWN
    if _BANNER_SHOWN:
        return
    _BANNER_SHOWN = True
    safe = redact_url(url)
    line = "=" * 70
    sys.stderr.write(
        f"\n{line}\n"
        f"  Component 3 / Alembic -- about to run migrations against:\n"
        f"    connection   : {safe}\n"
        f"    version table: {OWNED_VERSION_TABLE}  "
        f"(the student app's 'alembic_version' is NOT touched)\n"
        f"  Confirm this is the intended database before proceeding.\n"
        f"{line}\n\n"
    )
    sys.stderr.flush()


def run_migrations_offline() -> None:
    url = _resolved_url()
    _print_target_banner(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=OWNED_VERSION_TABLE,
        include_object=component3_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=OWNED_VERSION_TABLE,
        include_object=component3_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = _resolved_url()
    _print_target_banner(url)
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
