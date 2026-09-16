"""In-process cache for a pipeline run's IMMUTABLE data (2026-09-16).

WHY THIS EXISTS
---------------
With the database hosted in Supabase, every query is a round trip to Singapore, and a class page
spent most of its seconds re-downloading data that had not changed since the run was produced.

WHAT IS SAFE TO CACHE, AND WHAT IS NOT
--------------------------------------
Cached here, keyed by ``pipeline_run_id``:

* the run's predictions (``t3_predictions``),
* its panel trajectory feed (``t3_panel``, narrow),
* its per-learner session history (``t3_panel``, wide -- the sessions and skills screens).

The offline pipeline writes all three once, for a NEW run id. A new run is a new key, so this can
never serve a previous run's predictions as the current one. A TTL bounds the rare case of a
pipeline stage being re-run in place for the same id.

NEVER cached -- read live on every request, because a teacher changes them while working:
rosters and memberships, join requests, class keys, and suggestions (a decision must show at
once, and `handled` counts depend on it). Ownership guards are never cached either: access is
decided per request.

The cached values are the reader layer's own rows. Callers filter them to the learners a page
shows, in memory, after the ownership check -- exactly as the SQL filter did.

ONE PROCESS. The cache lives in the API process, which runs a single uvicorn worker
(`compose.yaml`). Several workers would each hold their own copy, which is correct (the data is
immutable) but warms more slowly.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application import data_access

logger = logging.getLogger("t3.run_cache")

#: How long run data may be served from memory. Long, because the data is immutable per run;
#: finite, so an in-place re-run is picked up without restarting the API.
RUN_DATA_TTL_SECONDS = 600.0
#: The active run is re-resolved often: that read is what notices a NEW run.
ACTIVE_RUN_TTL_SECONDS = 60.0


class _Entry:
    __slots__ = ("value", "stored_at")

    def __init__(self, value: Any) -> None:
        self.value = value
        self.stored_at = time.monotonic()

    def fresh(self, ttl: float) -> bool:
        return time.monotonic() - self.stored_at < ttl


class RunCache:
    def __init__(self) -> None:
        self._entries: dict[tuple, _Entry] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()

    async def _get(
        self, key: tuple, ttl: float, load: Callable[[], Awaitable[Any]]
    ) -> Any:
        entry = self._entries.get(key)
        if entry is not None and entry.fresh(ttl):
            return entry.value
        # One loader per key: twelve concurrent requests on a cold cache issue one query,
        # not twelve.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._entries.get(key)
            if entry is not None and entry.fresh(ttl):
                return entry.value
            value = await load()
            self._entries[key] = _Entry(value)
            return value

    # ---- the active run -----------------------------------------------------------------

    async def active_run(self, session: AsyncSession, *, model_version: str) -> Any:
        """`data_access.active_pipeline_run`, remembered briefly. An error (no run, or two) is
        raised and NOT cached, so the fix is seen on the next request."""

        return await self._get(
            ("active_run", model_version),
            ACTIVE_RUN_TTL_SECONDS,
            lambda: data_access.active_pipeline_run(
                session, active_model_version=model_version
            ),
        )

    # ---- run-wide immutable data --------------------------------------------------------

    async def predictions(self, session: AsyncSession, run_id: uuid.UUID) -> list[Any]:
        return await self._get(
            ("predictions", run_id),
            RUN_DATA_TTL_SECONDS,
            lambda: _as_list(data_access.predictions_for_run(session, run_id)),
        )

    async def panel(self, session: AsyncSession, run_id: uuid.UUID) -> list[Any]:
        return await self._get(
            ("panel", run_id),
            RUN_DATA_TTL_SECONDS,
            lambda: _as_list(data_access.panel_rows_for_run(session, run_id)),
        )

    def has_predictions(self, run_id: uuid.UUID) -> bool:
        entry = self._entries.get(("predictions", run_id))
        return entry is not None and entry.fresh(RUN_DATA_TTL_SECONDS)

    # ---- per-learner session history ----------------------------------------------------

    async def history_for_student(
        self, session: AsyncSession, run_id: uuid.UUID, student_id: uuid.UUID
    ) -> list[Any]:
        """One learner's wide panel history. Served from memory when a class read has already
        loaded it (`history_for_students`); otherwise read for this learner alone."""

        return await self._get(
            ("history", run_id, student_id),
            RUN_DATA_TTL_SECONDS,
            lambda: _as_list(
                data_access.session_history_for_student(session, run_id, student_id)
            ),
        )

    async def history_for_students(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        student_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, list[Any]]:
        """Many learners' histories in ONE query for whichever of them are not cached yet.
        Each is stored under its own key, so a later single-learner read is a cache hit."""

        missing = [
            sid
            for sid in student_ids
            if not (
                (entry := self._entries.get(("history", run_id, sid))) is not None
                and entry.fresh(RUN_DATA_TTL_SECONDS)
            )
        ]
        if missing:
            rows = await data_access.session_history_for_students(session, run_id, missing)
            grouped: dict[uuid.UUID, list[Any]] = {sid: [] for sid in missing}
            for row in rows:
                grouped.setdefault(row.student_id, []).append(row)
            for sid, learner_rows in grouped.items():
                learner_rows.sort(key=lambda r: r.intervention_session_number)
                self._entries[("history", run_id, sid)] = _Entry(learner_rows)
        return {
            sid: self._entries[("history", run_id, sid)].value for sid in student_ids
        }

    # ---- warming ------------------------------------------------------------------------

    async def warm(self, session: AsyncSession, *, model_version: str) -> None:
        """Load the active run's immutable data before the first teacher asks for it.
        Best-effort: a failure here is logged and simply leaves the cache cold."""

        started = time.monotonic()
        run = await self.active_run(session, model_version=model_version)
        await self.predictions(session, run.pipeline_run_id)
        await self.panel(session, run.pipeline_run_id)
        logger.info(
            "run cache warmed",
            extra={"elapsed_ms": round(1000 * (time.monotonic() - started))},
        )


async def _as_list(coro: Awaitable[Sequence[Any]]) -> list[Any]:
    return list(await coro)


#: The process-wide instance. Tests clear it between cases (`tests/conftest.py`).
run_cache = RunCache()
