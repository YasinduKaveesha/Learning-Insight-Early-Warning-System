"""Persists the 58-column feature matrix to ``t3_features_at_t`` (work order B4.2).

CONTRACT NOTE, read before touching this file: ``t3_panel`` stores *raw* Component B/C
session measures (``b_accuracy_rate``, ``b_mastery`` jsonb, ``c_engagement_score``, ...). The
19 base features ``app.infrastructure.feature_builder`` expects
(``score_trend_slope``, ``mastery_progression_rate``, ...) are a separate research-pipeline
output (docs/06) that lives only in
``dataset/features/feature_matrix_at_t_seed20260828_n300.csv`` -- there is no code anywhere in
this backend that derives them from raw ``t3_panel`` rows, and this module does not add any.

So the division of responsibility here (confirmed with the work-order owner) is:

* ``t3_panel`` (already loaded by ``t3_loader``, work order B4/B4.1) is read ONLY to resolve
  *scope*: which ``pipeline_run_id`` is in play and which ``(learner_id, t)`` pairs already
  have a panel row on the supervised grid.
* The CSV research panel remains the authoritative source of the 58-column feature *values*,
  read through the existing, tested ``feature_builder`` module unchanged.
* ``t3_demo_learner_map`` bridges the two: it maps ``t3_panel``'s ``learner_id`` (uuid) back
  to the research ``student_id`` ("STU-0001") the CSV is keyed by.

Rules enforced here (backend_plan.md section 5.2, dev_docs/ML_BACKEND_HANDOVER_SPEC.md
section 5):

1. Column order for scoring comes from ``model.feature_names_in_``, read at load time --
   never hardcoded. Enforced by :func:`assert_matches_model_contract`.
2. The set of feature names stored must equal ``set(model.feature_names_in_)`` exactly. A
   violation raises and aborts the WHOLE write -- never a partial matrix.
3. Every stored row carries ``feature_version`` and ``pipeline_run_id``.
4. A null is never coerced to a zero on the way into ``jsonb`` -- ``_json_safe`` maps
   ``NaN`` / ``pandas.NA`` to ``None``, nothing else.
5. Row count read back from the DATABASE after the write must match the number of snapshots
   built, the same discipline as ``t3_loader.PanelRowCountMismatchError``. A mismatch aborts
   (rolls back) the whole write.

Follows ``t3_loader.py``'s self-contained-engine pattern for the CLI entry point
(``_amain``). TODO(B2.2): repoint at the shared session factory once it exists instead of
opening its own engine here.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import feature_builder
from app.infrastructure.db.models import FeaturesAtT, PipelineRun
from app.infrastructure.model_loading import LoadedModel

__all__ = [
    "SOURCE_CLASS",
    "SOURCE_SYSTEM",
    "PARAMETER_SOURCE_STATUS",
    "PipelineRunNotFoundError",
    "PanelScopeEmptyError",
    "LearnerMapResolutionError",
    "FeatureContractAbort",
    "FeatureRowCountMismatchError",
    "PersistResult",
    "assert_matches_model_contract",
    "json_safe_features",
    "resolve_panel_scope",
    "reverse_resolve_student_ids",
    "build_rows_to_write",
    "run_persist",
]

SOURCE_CLASS = "SYNTHETIC"
SOURCE_SYSTEM = "feature_persistence"
PARAMETER_SOURCE_STATUS = "TEST_FIXTURE_ONLY"


class PipelineRunNotFoundError(RuntimeError):
    """The given ``pipeline_run_id`` has no row in ``t3_pipeline_runs``."""


class PanelScopeEmptyError(RuntimeError):
    """``t3_panel`` has no rows on the supervised grid for this ``pipeline_run_id``."""


class LearnerMapResolutionError(RuntimeError):
    """One or more ``learner_id`` values in scope have no ``t3_demo_learner_map`` row.

    This module never guesses a research ``student_id`` -- an unmapped learner aborts the
    whole write rather than silently skipping a snapshot.
    """

    def __init__(self, unresolved: Sequence[uuid.UUID]) -> None:
        self.unresolved = list(unresolved)
        super().__init__(
            f"{len(self.unresolved)} learner_id(s) in t3_panel scope have no "
            f"t3_demo_learner_map row: {self.unresolved[:10]}"
            + ("" if len(self.unresolved) <= 10 else f" (+{len(self.unresolved) - 10} more)")
        )


class FeatureContractAbort(RuntimeError):
    """The set of feature names this module would store does not exactly equal
    ``model.feature_names_in_``. Raised before a single row is written."""

    def __init__(self, *, missing: frozenset[str], extra: frozenset[str]) -> None:
        self.missing = missing
        self.extra = extra
        super().__init__(
            f"feature contract violation: missing={sorted(missing)} extra={sorted(extra)}"
        )


class FeatureRowCountMismatchError(RuntimeError):
    """The row count read back from ``t3_features_at_t`` does not match the number of
    snapshots built. Hard failure -- aborts and rolls back, never a partial matrix."""

    def __init__(self, pipeline_run_id: uuid.UUID, expected: int, actual: int) -> None:
        self.pipeline_run_id = pipeline_run_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"t3_features_at_t row count for pipeline_run_id={pipeline_run_id} is {actual}, "
            f"expected {expected}; aborting and rolling back the write."
        )


@dataclass(frozen=True)
class PersistResult:
    pipeline_run_id: uuid.UUID
    feature_version: str
    rows_written: int


def assert_matches_model_contract(model: LoadedModel) -> None:
    """Rule 1/2: the columns ``feature_builder`` knows how to build must exactly equal the
    model's ``feature_names_in_``. Checked once, up front, so a drift between the two is a
    loud abort rather than a silently short (or long) stored row."""

    built = frozenset(feature_builder.ALL_FEATURE_COLUMNS)
    expected = frozenset(model.feature_order)
    missing = expected - built
    extra = built - expected
    if missing or extra:
        raise FeatureContractAbort(missing=missing, extra=extra)


def json_safe_features(record: dict[str, Any], feature_order: Sequence[str]) -> dict[str, Any]:
    """Extract exactly ``feature_order`` from ``record`` as a jsonb-safe dict.

    ``NaN`` (from a censored slope, a first-snapshot lag, ...) becomes ``None`` -- jsonb has
    no NaN literal, and rule 5 says a null is never a zero. Nothing else is coerced: an
    already-null value stays ``None``, a real number is passed through unchanged (numpy
    scalars are converted to native Python via ``.item()`` so ``json`` can serialise them).
    """

    out: dict[str, Any] = {}
    for name in feature_order:
        value = record[name]
        if value is None:
            out[name] = None
        elif isinstance(value, float) and math.isnan(value):
            out[name] = None
        elif pd.isna(value):
            out[name] = None
        elif hasattr(value, "item"):
            out[name] = value.item()
        else:
            out[name] = value
    return out


async def resolve_panel_scope(
    session: AsyncSession, *, pipeline_run_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Read ``t3_panel`` for ``pipeline_run_id``, restricted to the supervised snapshot grid.

    Raises :class:`PipelineRunNotFoundError` if the run does not exist, and
    :class:`PanelScopeEmptyError` if it exists but has no rows on the grid -- both before any
    feature row is built.
    """

    run_exists = await session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_run_id == pipeline_run_id)
    )
    if not run_exists:
        raise PipelineRunNotFoundError(
            f"pipeline_run_id={pipeline_run_id} has no t3_pipeline_runs row"
        )

    rows = await session.execute(
        text(
            "SELECT student_id, intervention_session_number FROM t3_panel "
            "WHERE pipeline_run_id = :run AND intervention_session_number = ANY(:grid)"
        ),
        {"run": pipeline_run_id, "grid": list(feature_builder.SUPERVISED_GRID)},
    )
    scope = [(row.student_id, row.intervention_session_number) for row in rows]
    if not scope:
        raise PanelScopeEmptyError(
            f"t3_panel has no rows on the supervised grid {feature_builder.SUPERVISED_GRID} "
            f"for pipeline_run_id={pipeline_run_id}"
        )
    return scope


async def reverse_resolve_student_ids(
    session: AsyncSession, learner_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """``t3_demo_learner_map.learner_id -> research_student_id`` for exactly ``learner_ids``.

    Raises :class:`LearnerMapResolutionError` if any id is unmapped -- this module never
    skips a learner silently, mirroring ``t3_loader.LearnerResolutionError``.
    """

    if not learner_ids:
        return {}

    rows = await session.execute(
        text(
            "SELECT learner_id, research_student_id FROM t3_demo_learner_map "
            "WHERE learner_id = ANY(:ids)"
        ),
        {"ids": list(learner_ids)},
    )
    mapping = {row.learner_id: row.research_student_id for row in rows}
    unresolved = sorted(learner_ids - mapping.keys(), key=str)
    if unresolved:
        raise LearnerMapResolutionError(unresolved)
    return mapping


def build_rows_to_write(
    *,
    scope: list[tuple[uuid.UUID, int]],
    learner_to_student: dict[uuid.UUID, str],
    feature_matrix: pd.DataFrame,
    feature_order: Sequence[str],
    feature_version: str,
    pipeline_run_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Turn panel scope + the CSV-built matrix into ``t3_features_at_t`` insert dicts.

    Pure -- no database. One row per ``(learner_id, t)`` in ``scope``; every value is looked
    up from ``feature_matrix`` by the reverse-resolved research ``student_id``, never the
    other way round, so an unmapped or out-of-matrix snapshot raises rather than being
    silently dropped.
    """

    rows: list[dict[str, Any]] = []
    for learner_id, t in scope:
        student_id = learner_to_student[learner_id]
        record = feature_builder.feature_row_for(
            feature_matrix, tuple(feature_order), student_id=student_id, t=t
        )
        rows.append(
            {
                "student_id": learner_id,
                "t": t,
                "feature_version": feature_version,
                "features": json_safe_features(record, feature_order),
                "pipeline_run_id": pipeline_run_id,
                "source_class": SOURCE_CLASS,
                "source_system": SOURCE_SYSTEM,
                "parameter_source_status": PARAMETER_SOURCE_STATUS,
            }
        )
    return rows


async def run_persist(
    session: AsyncSession,
    *,
    pipeline_run_id: uuid.UUID,
    panel_csv_path: str | Path,
    model: LoadedModel,
    feature_version: str,
) -> PersistResult:
    """Read ``t3_panel`` scope for ``pipeline_run_id``, build the 58-column matrix from the
    CSV research panel via the existing ``feature_builder``, and write ``t3_features_at_t``.

    Single transaction: any failure (contract violation, unresolved learner, row-count
    mismatch) rolls back the whole write. Never a partial matrix.
    """

    assert_matches_model_contract(model)

    research_panel = feature_builder.load_research_panel(panel_csv_path)
    feature_matrix = feature_builder.build_feature_matrix(research_panel)

    async with session.begin():
        scope = await resolve_panel_scope(session, pipeline_run_id=pipeline_run_id)
        learner_to_student = await reverse_resolve_student_ids(
            session, {learner_id for learner_id, _ in scope}
        )

        rows = build_rows_to_write(
            scope=scope,
            learner_to_student=learner_to_student,
            feature_matrix=feature_matrix,
            feature_order=model.feature_order,
            feature_version=feature_version,
            pipeline_run_id=pipeline_run_id,
        )

        if rows:
            await session.execute(insert(FeaturesAtT), rows)

        actual_count = await session.scalar(
            select(func.count())
            .select_from(FeaturesAtT)
            .where(
                FeaturesAtT.pipeline_run_id == pipeline_run_id,
                FeaturesAtT.feature_version == feature_version,
            )
        )
        if actual_count != len(rows):
            raise FeatureRowCountMismatchError(pipeline_run_id, len(rows), actual_count or 0)

    return PersistResult(
        pipeline_run_id=pipeline_run_id,
        feature_version=feature_version,
        rows_written=len(rows),
    )


async def _amain() -> None:  # pragma: no cover - operational entrypoint
    """``python -m app.application.feature_persistence`` -- run against the direct (5432)
    database. Reads ``DATABASE_URL``, ``T3_PIPELINE_RUN_ID``, ``T3_PANEL_CSV_PATH``,
    ``T3_ACTIVE_MODEL_VERSION`` and ``T3_ARTEFACT_STORE_PATH`` from the environment.
    """

    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.infrastructure import model_loading
    from app.infrastructure.db_url import normalise_async_url, redact_url
    from app.infrastructure.migration_guard import assert_direct_connection

    url = normalise_async_url(os.environ["DATABASE_URL"])
    assert_direct_connection(url)
    print(f"feature_persistence target: {redact_url(url)}")

    model_version = os.environ.get("T3_ACTIVE_MODEL_VERSION", "1.0.0")
    artefact_store = Path(os.environ["T3_ARTEFACT_STORE_PATH"])
    artefact_path = model_loading.resolve_artefact_path(artefact_store, model_version)
    model = model_loading.load_model(artefact_path, model_version=model_version)

    engine = create_async_engine(url, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            result = await run_persist(
                session,
                pipeline_run_id=uuid.UUID(os.environ["T3_PIPELINE_RUN_ID"]),
                panel_csv_path=os.environ["T3_PANEL_CSV_PATH"],
                model=model,
                feature_version=model_version,
            )
    finally:
        await engine.dispose()

    print(
        f"pipeline_run_id={result.pipeline_run_id} feature_version={result.feature_version} "
        f"rows_written={result.rows_written}"
    )


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(_amain())
