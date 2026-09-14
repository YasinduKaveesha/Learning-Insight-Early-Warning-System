"""The Component 3 loader -- docs/04 section 7 steps 1-3 only (work order B4).

Steps 4-5 (features -> ``t3_features_at_t``, predictions -> ``t3_predictions``) are later
work orders and are NOT done here.

    1. Allocate a ``pipeline_run_id``; write the ``t3_pipeline_runs`` row with a real
       ``dataset_manifest`` (the ``so2_manifest_*.json``) and ``model_version``.
    2. Resolve every ``student_id`` to an existing ``b_learners.learner_id``. **The loader
       does not create learners** -- they belong to the live application. A ``student_id``
       with no matching learner is an error: report how many and abort, never skip silently.
    3. Load the panel -> ``t3_panel``.

Provenance on every written row (work order B4):

    source_class            = 'SYNTHETIC'   -- the research dataset, not real activity;
                                               this is the switch that makes the transition
                                               to real data visible.
    source_system           = 't3_loader'
    parameter_source_status = 'TEST_FIXTURE_ONLY'
    pipeline_run_id         = this run's id

Re-runnable by construction: each call allocates a fresh ``pipeline_run_id``, and
``t3_panel``'s primary key carries ``pipeline_run_id`` -- so a second run writes a new
generation beside the first rather than colliding with or silently mixing into it.

Before writing a single panel row the loader asserts ``population`` and ``dd_subtype`` are
absent from every mapped record; if either is present it aborts the entire load (docs/04
section 7 step 4 states this for features -- it applies here too). It does not drop the
column and continue.

This module reads its data ONLY through :mod:`app.infrastructure.bc_adapter`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import re

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import bc_adapter
from app.infrastructure.db.models import Panel, PipelineRun

__all__ = [
    "SOURCE_CLASS",
    "SOURCE_SYSTEM",
    "PARAMETER_SOURCE_STATUS",
    "LearnerResolutionError",
    "AuditLabelLeakError",
    "PanelRowCountMismatchError",
    "LoadResult",
    "LearnerResolver",
    "DictLearnerResolver",
    "SqlLearnerResolver",
    "DemoMapLearnerResolver",
    "assert_no_audit_labels",
    "partition_by_resolution",
    "run_load",
]

SOURCE_CLASS = "SYNTHETIC"
SOURCE_SYSTEM = "t3_loader"
PARAMETER_SOURCE_STATUS = "TEST_FIXTURE_ONLY"

_FORBIDDEN_KEYS = frozenset({"population", "dd_subtype"})


class LearnerResolutionError(RuntimeError):
    """One or more ``student_id`` values do not match any ``b_learners.learner_id``.

    The loader aborts -- it never creates learners and never skips a session silently.
    """

    def __init__(self, unresolved: Sequence[str]) -> None:
        self.unresolved = list(unresolved)
        preview = ", ".join(self.unresolved[:10])
        more = "" if len(self.unresolved) <= 10 else f" (+{len(self.unresolved) - 10} more)"
        super().__init__(
            f"{len(self.unresolved)} student_id value(s) resolve to no b_learners row: "
            f"[{preview}{more}]. The loader does not create learners; aborting the load."
        )


class AuditLabelLeakError(RuntimeError):
    """A mapped record carried ``population`` or ``dd_subtype``. Abort the whole load."""


class PanelRowCountMismatchError(RuntimeError):
    """The row count read back from ``t3_panel`` for this ``pipeline_run_id`` does not match
    the expected number of resolvable records.

    B0.1's mutation testing proved dropping a row from the loader still leaves the test suite
    green -- there was no automated assertion on row count. This is that assertion: a hard
    failure, not a log line, and it aborts (rolls back) the whole load rather than leaving a
    partial generation behind.
    """

    def __init__(self, pipeline_run_id: uuid.UUID, expected: int, actual: int) -> None:
        self.pipeline_run_id = pipeline_run_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"t3_panel row count for pipeline_run_id={pipeline_run_id} is {actual}, "
            f"expected {expected}; aborting and rolling back the load."
        )


@dataclass(frozen=True)
class LoadResult:
    pipeline_run_id: uuid.UUID
    records_read: int
    panel_rows_written: int
    unresolved_student_ids: tuple[str, ...] = ()


class LearnerResolver(Protocol):
    """Maps research ``student_id`` strings to live ``b_learners.learner_id`` UUIDs.

    Resolution is a lookup, never a create. An id with no match is simply absent from the
    returned mapping -- :func:`partition_by_resolution` turns that into the abort.
    """

    async def resolve(self, student_ids: set[str]) -> dict[str, uuid.UUID]: ...


class DictLearnerResolver:
    """A fixed mapping -- for tests and for a caller that already holds the correspondence."""

    def __init__(self, mapping: dict[str, uuid.UUID]) -> None:
        self._mapping = dict(mapping)

    async def resolve(self, student_ids: set[str]) -> dict[str, uuid.UUID]:
        return {sid: self._mapping[sid] for sid in student_ids if sid in self._mapping}


class SqlLearnerResolver:
    """Resolve against a column of the live ``b_learners`` table.

    The research ``student_id`` ("STU-0001") is an opaque external identifier; the live app
    owns no column named for it, so the matching column is configurable (default ``name``).
    ``b_learners`` is not in Component 3's metadata beyond a one-column shadow, so this reads
    it with a parameterised ``text()`` query rather than the ORM. Wiring the real
    correspondence is a live-integration concern (backend_plan.md section 11) -- this
    resolver is the seam for it.
    """

    _IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

    def __init__(self, session: AsyncSession, *, match_column: str = "name") -> None:
        if not self._IDENT.match(match_column):
            raise ValueError(f"match_column {match_column!r} is not a bare SQL identifier")
        self._session = session
        self._match_column = match_column

    async def resolve(self, student_ids: set[str]) -> dict[str, uuid.UUID]:
        if not student_ids:
            return {}
        rows = await self._session.execute(
            text(
                f"SELECT {self._match_column} AS k, learner_id "  # noqa: S608 - validated ident
                "FROM b_learners WHERE "
                f"{self._match_column} = ANY(:ids)"
            ),
            {"ids": list(student_ids)},
        )
        return {str(key): value for key, value in rows.all()}


class DemoMapLearnerResolver:
    """Resolve via the demo bridge table ``t3_demo_learner_map`` (work order B4.1).

    ``SqlLearnerResolver`` matches ``student_id`` against ``b_learners.name`` -- live names
    are empty/unrelated, so it aborts every load for now. This resolver reads the explicit
    demo bridge instead: ``research_student_id -> learner_id``, both directions unique by
    construction (the table's PK and UNIQUE constraint). It is additive -- ``SqlLearnerResolver``
    is untouched and still the one live-integration work will eventually replace or repoint.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, student_ids: set[str]) -> dict[str, uuid.UUID]:
        if not student_ids:
            return {}
        rows = await self._session.execute(
            text(
                "SELECT research_student_id AS k, learner_id "
                "FROM t3_demo_learner_map WHERE research_student_id = ANY(:ids)"
            ),
            {"ids": list(student_ids)},
        )
        return {str(key): value for key, value in rows.all()}


def assert_no_audit_labels(records: Iterable[dict[str, Any]]) -> None:
    """Raise :class:`AuditLabelLeakError` if any record carries an audit-only label.

    Called before the first panel write. Not defensive programming -- it is the last
    automated point at which a leaked column can be caught before it reaches an application
    that would happily serve it (docs/04 section 7).
    """

    for record in records:
        leaked = _FORBIDDEN_KEYS.intersection(record)
        if leaked:
            raise AuditLabelLeakError(
                f"mapped record for {record.get('student_id')!r} carries {sorted(leaked)}; "
                "aborting the entire load (docs/04 section 7 step 4)"
            )


def partition_by_resolution(
    records: Sequence[dict[str, Any]], id_map: dict[str, uuid.UUID]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Split records into (resolvable, sorted-unique-unresolved-student-ids).

    Pure -- no database. ``run_load`` aborts when the second list is non-empty.
    """

    unresolved = sorted({r["student_id"] for r in records if r["student_id"] not in id_map})
    resolvable = [r for r in records if r["student_id"] in id_map]
    return resolvable, unresolved


async def run_load(
    session: AsyncSession,
    *,
    source_path: str | Path,
    manifest_path: str | Path,
    resolver: LearnerResolver,
    model_version: str,
    notes: str | None = None,
) -> LoadResult:
    """Run docs/04 section 7 steps 1-3 in a single transaction. Returns a :class:`LoadResult`.

    Aborts (rolling back) on any unresolved ``student_id`` or any leaked audit label, before
    a panel row is written.
    """

    manifest = bc_adapter.read_manifest(manifest_path)
    records = bc_adapter.load_panel_records(source_path)
    assert_no_audit_labels(records)

    pipeline_run_id = uuid.uuid4()
    provenance = {
        "source_class": SOURCE_CLASS,
        "source_system": SOURCE_SYSTEM,
        "parameter_source_status": PARAMETER_SOURCE_STATUS,
        "pipeline_run_id": pipeline_run_id,
    }

    student_ids = {r["student_id"] for r in records}

    # `resolver.resolve` executes a query against `session` (`SqlLearnerResolver` /
    # `DemoMapLearnerResolver` both do). SQLAlchemy's AsyncSession autobegins a transaction on
    # first use, so that query must happen INSIDE the same `session.begin()` block as the
    # writes below -- calling `resolver.resolve` first and then `session.begin()` raises
    # ``InvalidRequestError: A transaction is already begun on this Session`` the moment a
    # resolver that actually touches the database (as opposed to `DictLearnerResolver`, which
    # never has) is used. Resolution still happens, and still aborts, before any panel row is
    # written -- it is simply the first statement inside the transaction rather than before it.
    async with session.begin():
        id_map = await resolver.resolve(student_ids)
        resolvable, unresolved = partition_by_resolution(records, id_map)
        if unresolved:
            raise LearnerResolutionError(unresolved)

        await session.execute(
            insert(PipelineRun).values(
                pipeline_run_id=pipeline_run_id,
                dataset_manifest=manifest,
                model_version=model_version,
                notes=notes,
                source_class=SOURCE_CLASS,
                source_system=SOURCE_SYSTEM,
                parameter_source_status=PARAMETER_SOURCE_STATUS,
            )
        )

        rows = [
            {
                **{key: value for key, value in record.items() if key != "student_id"},
                "student_id": id_map[record["student_id"]],
                **provenance,
            }
            for record in resolvable
        ]
        if rows:
            await session.execute(insert(Panel), rows)

        # Hard, asserted row-count check (work order B4.1): read the actual count back from
        # the database for this pipeline_run_id, not the length of the in-memory `rows` list
        # that was just inserted -- a mismatch here means the database's view of what was
        # written disagrees with what the loader intended, which is exactly what B0.1's
        # mutation testing found nothing was checking. A mismatch raises inside the
        # transaction block, so `session.begin()` rolls the whole load back; this must be a
        # hard failure, never a log/warning.
        actual_count = await session.scalar(
            select(func.count()).select_from(Panel).where(
                Panel.pipeline_run_id == pipeline_run_id
            )
        )
        if actual_count != len(rows):
            raise PanelRowCountMismatchError(pipeline_run_id, len(rows), actual_count or 0)

    return LoadResult(
        pipeline_run_id=pipeline_run_id,
        records_read=len(records),
        panel_rows_written=len(rows),
    )


async def _amain() -> None:  # pragma: no cover - operational entrypoint
    """``python -m app.application.t3_loader`` -- run against the direct (5432) database.

    Reads ``DATABASE_URL`` and ``T3_ACTIVE_MODEL_VERSION`` from the environment, and the
    source/manifest paths from ``T3_SOURCE_PATH`` / ``T3_MANIFEST_PATH``.

    ``T3_LEARNER_RESOLVER`` selects how a research ``student_id`` becomes a ``learner_id``:

    ``sql`` (default)
        :class:`SqlLearnerResolver`, matching ``b_learners.name``. This is the seam real
        live-integration will repoint, and it is the default because it is what the committed
        live tests exercise. Against today's data it resolves nothing.

    ``demo_map``
        :class:`DemoMapLearnerResolver`, reading the explicit ``t3_demo_learner_map`` bridge
        that ``scripts/seed_demo_tenancy.py`` populates. This is what a demo run wants.

    Either way :func:`run_load` refuses a partial load -- an unresolved ``student_id`` raises
    :class:`LearnerResolutionError` rather than silently dropping a learner. So the source
    file must contain only students present in the bridge; loading the full 300-student
    research dataset against a 120-learner demo roster is expected to abort, and that is the
    guard working, not a bug.
    """

    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.db.engine import create_direct_engine

    # The shared factory's *direct-connection* shape (work order B2.2). This is a bulk load
    # on port 5432, not an API request on the pooler, so it must not go through
    # `get_engine()`; `create_direct_engine` still refuses a pooler URL outright.
    engine, target = create_direct_engine(os.environ["DATABASE_URL"])
    print(f"t3_loader target: {target}")

    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            resolver_name = os.environ.get("T3_LEARNER_RESOLVER", "sql").strip().lower()
            if resolver_name == "demo_map":
                resolver: LearnerResolver = DemoMapLearnerResolver(session)
            elif resolver_name == "sql":
                resolver = SqlLearnerResolver(session)
            else:
                raise ValueError(
                    f"T3_LEARNER_RESOLVER={resolver_name!r} is not recognised; "
                    f"use 'sql' or 'demo_map'"
                )
            print(f"learner resolver: {resolver_name}")

            result = await run_load(
                session,
                source_path=os.environ["T3_SOURCE_PATH"],
                manifest_path=os.environ["T3_MANIFEST_PATH"],
                resolver=resolver,
                model_version=os.environ.get("T3_ACTIVE_MODEL_VERSION", "1.0.0"),
            )
    finally:
        await engine.dispose()

    print(
        f"pipeline_run_id={result.pipeline_run_id} records_read={result.records_read} "
        f"panel_rows_written={result.panel_rows_written}"
    )


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(_amain())
