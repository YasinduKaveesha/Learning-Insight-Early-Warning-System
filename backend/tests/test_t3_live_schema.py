"""Live-schema guards for the B3.3 tables (work order B3.3, gate 4; also 5 and 6 live).

Gate 4 requires introspecting the ACTUAL database, not the model classes: a model-only
check passes even if `population` / `dd_subtype` is slipped in through a hand-written
migration. This module reflects `t3_panel` and `t3_features_at_t` from a running Postgres
and asserts those columns do not exist.

Skips cleanly when the tooling or a database is not available -- which is always the case in
the pinned `c3-ews` env (no SQLAlchemy, no driver, and the local Docker DB publishes no host
port). To run it, point `T3_LIVE_DB_URL` at a direct (5432) connection, e.g.:

    T3_LIVE_DB_URL=postgresql://upadya:...@127.0.0.1:5432/upadya \\
        conda run -n <env-with-sqlalchemy+asyncpg> python -m pytest tests/test_t3_live_schema.py
"""

from __future__ import annotations

import asyncio
import os
import re

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the live-schema gates",
)

_TABLES = ("t3_panel", "t3_features_at_t")
_FORBIDDEN = {"population", "dd_subtype"}
_COLLISION_PRONE = re.compile(r"accuracy|response_time|latency|duration", re.IGNORECASE)


def _normalise(url: str) -> str:
    try:
        from app.infrastructure.db_url import normalise_async_url

        return normalise_async_url(url)
    except Exception:
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


def _reflect() -> dict[str, dict]:
    async def go() -> dict[str, dict]:
        engine = create_async_engine(_normalise(_LIVE_URL))
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda sync_conn: {
                        table: {
                            "columns": [c["name"] for c in inspect(sync_conn).get_columns(table)],
                            "pk": inspect(sync_conn).get_pk_constraint(table)["constrained_columns"],
                        }
                        for table in _TABLES
                    }
                )
        finally:
            await engine.dispose()

    return asyncio.run(go())


@pytest.fixture(scope="module")
def schema() -> dict[str, dict]:
    return _reflect()


def test_gate4_no_population_or_dd_subtype_column(schema: dict[str, dict]) -> None:
    for table in _TABLES:
        cols = set(schema[table]["columns"])
        leaked = _FORBIDDEN & cols
        assert not leaked, f"{table} has audit-only label column(s) in the LIVE schema: {sorted(leaked)}"


def test_gate5_live_panel_bc_measures_keep_their_prefix(schema: dict[str, dict]) -> None:
    offenders = [
        name
        for name in schema["t3_panel"]["columns"]
        if _COLLISION_PRONE.search(name) and not name.startswith(("b_", "c_"))
    ]
    assert offenders == [], f"unprefixed B/C-collision-prone columns on live t3_panel: {offenders}"


def test_gate6_live_features_primary_key_contains_t(schema: dict[str, dict]) -> None:
    pk = schema["t3_features_at_t"]["pk"]
    assert "t" in pk, f"live t3_features_at_t PK does not contain 't': {pk}"
