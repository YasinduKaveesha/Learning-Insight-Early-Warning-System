"""The decision layer -- model output -> ``t3_predictions`` (work order B5.1).

Everything between the model's raw probabilities and what the API will serve:
evidence status, the watch flag, within-``t`` ranking, both trajectories, and -- since B5.2 --
the explanation layer, which is delegated wholesale to :mod:`app.application.explanation`.
NOT here (named owners, so nobody re-litigates mid-build):

* skill progress, ``docs`` section 6.5 (still open).
* the eleven read endpoints (B6); recommendations (B7).
* ``risk_level`` -- stays NULL, ``risk_level_status`` stays at its ``CALIBRATION_PENDING``
  default. No validated tier exists; the High tier was rejected across eight label
  parameterisations (``ck_t3_predictions_no_high`` is the schema-level guarantee).

Input, per decision D21: the 58-column feature *values* are read from ``t3_features_at_t``
(persisted by :mod:`app.application.feature_persistence` for this ``pipeline_run_id``), and
scored with the pinned artefact via :func:`app.infrastructure.model_loading.score_snapshot`.
The trailing-window trajectories are computed from ``t3_panel`` -- the raw per-session
Component B / C measures (``b_accuracy_rate``, ``c_engagement_score``), which are the panel's
job, not the feature matrix's.

Rules enforced here (backend_plan.md sections 6.1-6.3, README D5/D6/D11/D12/D14/D16/D17,
dev_docs/ML_BACKEND_HANDOVER_SPEC.md sections 8/9/22):

1. **Watch flag = ``predicted_class >= 1 AND sessions_completed >= 3``. That is the whole
   rule** (D5, D14). No probability threshold, no top-k% cut, no session gate beyond the
   warm-up floor. :func:`compute_watch_flag` mirrors the load-bearing
   ``COALESCE(predicted_class, -1)`` of ``ck_t3_predictions_watch_flag`` -- a null
   ``predicted_class`` (a learner below the warm-up floor) is FALSE, never NULL/unconstrained.
2. **A learner below the warm-up floor (< 3 completed sessions, D6) gets an
   ``evidence_status`` and NO watch judgement** -- ``predicted_class`` / the probabilities /
   the ranks are all NULL, ``watch_flag`` is ``false``. Absence of a judgement and a negative
   judgement are different things (trap 7). Never a default of "no concern".
3. **Ranking is on ``prob_class_2plus``, WITHIN each ``t``, never pooled** (trap 1, D-handover
   section 9). 2+ prevalence rises 0.000 -> 0.144 across ``t`` and ``t`` is the strongest
   single feature; a pooled rank sorts by the calendar. Persisted keyed ``(student_id, t)``,
   never as a learner attribute -- rank correlation decays to ~0 within six sessions and is
   negative across the study. A previous snapshot's flag is never carried forward.
   **Tiebreak: ascending ``str(student_id)``** -- deterministic, and tested (gate 7 / test 12).
4. **``practice_trajectory`` ships; ``engagement_trajectory`` is STORED and NEVER SERVED**
   (D17). Both are computed identically -- OLS slope over the trailing ``w = 4`` sessions --
   but with different floors: ``EPSILON_PRACTICE = 0.05`` (NOT 0.005 -- ``b_accuracy_rate`` is
   a ratio over 2-4 items, one differing item moves the slope 0.08-0.17, and it takes only 88
   distinct values across 2,700 rows; 0.005 is an order of magnitude below what the instrument
   resolves) and ``EPSILON_ENGAGEMENT = 0.010``. **The two are never averaged** (rule 3-F9).
   ``< 3 sessions`` -> ``unknown``, never ``stable``.
5. **No code path emits ``risk_level = 'High'``** (trap 6). This module never sets
   ``risk_level`` at all.

Transactional shape: matches :mod:`app.application.feature_persistence` exactly -- the model
contract is asserted BEFORE ``session.begin()`` (a violation aborts before a single write),
the write + read-back-count check are one transaction, and a count mismatch rolls the whole
thing back. Never a partial predictions generation.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.feature_persistence import assert_matches_model_contract
from app.application import explanation
from app.infrastructure import model_loading
from app.infrastructure.db.models import FeaturesAtT, Prediction, PipelineRun
from app.infrastructure.model_loading import LoadedModel

__all__ = [
    "SOURCE_CLASS",
    "SOURCE_SYSTEM",
    "PARAMETER_SOURCE_STATUS",
    "WARMUP_FLOOR",
    "TRAJECTORY_WINDOW",
    "EPSILON_PRACTICE",
    "EPSILON_ENGAGEMENT",
    "EVIDENCE_SUFFICIENT",
    "EVIDENCE_INSUFFICIENT_EXPOSURE",
    "PipelineRunNotFoundError",
    "FeatureMatrixEmptyError",
    "PredictionRowCountMismatchError",
    "DecisionResult",
    "ols_slope",
    "classify_trajectory",
    "trailing_trajectory",
    "compute_watch_flag",
    "evidence_status_for",
    "assign_ranks_within_t",
    "build_prediction_rows",
    "run_decision_layer",
]

SOURCE_CLASS = "SYNTHETIC"
SOURCE_SYSTEM = "decision_layer"
PARAMETER_SOURCE_STATUS = "TEST_FIXTURE_ONLY"

#: D6 -- the warm-up floor. Below this many completed sessions there is no watch judgement.
WARMUP_FLOOR = 3

#: D11 -- OLS slope over the trailing w = 4 sessions.
TRAJECTORY_WINDOW = 4

#: D11 [SENS] -- practice: half an item per window. NOT 0.005 (see module docstring).
EPSILON_PRACTICE = 0.05
#: D17 -- engagement (computed, never served).
EPSILON_ENGAGEMENT = 0.010

EVIDENCE_SUFFICIENT = "sufficient_evidence"
EVIDENCE_INSUFFICIENT_EXPOSURE = "insufficient_exposure"

_TRAJECTORY_IMPROVING = "improving"
_TRAJECTORY_STABLE = "stable"
_TRAJECTORY_NEEDS_ATTENTION = "needs_attention"
_TRAJECTORY_UNKNOWN = "unknown"

#: The 58-column feature that carries how many sessions this learner has data for. On the
#: research dataset ``sessions_observed == t`` for every one of the 2,700 rows; it is the
#: number of completed sessions the warm-up floor (D6) is checked against. Read from the
#: persisted feature row rather than counted from ``t3_panel`` so the watch judgement does
#: not depend on whether the panel happens to hold every session or only the snapshot grid.
_SESSIONS_COMPLETED_FEATURE = "sessions_observed"


class PipelineRunNotFoundError(RuntimeError):
    """The given ``pipeline_run_id`` has no row in ``t3_pipeline_runs``."""


class FeatureMatrixEmptyError(RuntimeError):
    """``t3_features_at_t`` has no rows for this ``pipeline_run_id`` / ``feature_version``.

    The decision layer scores what feature persistence wrote; nothing to score is an abort,
    never a silent empty predictions generation.
    """


class PredictionRowCountMismatchError(RuntimeError):
    """The row count read back from ``t3_predictions`` does not match the number of
    prediction rows built. Hard failure -- aborts and rolls back, never a partial write."""

    def __init__(self, pipeline_run_id: uuid.UUID, expected: int, actual: int) -> None:
        self.pipeline_run_id = pipeline_run_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"t3_predictions row count for pipeline_run_id={pipeline_run_id} is {actual}, "
            f"expected {expected}; aborting and rolling back the write."
        )


@dataclass(frozen=True)
class DecisionResult:
    pipeline_run_id: uuid.UUID
    model_version: str
    feature_version: str
    rows_written: int
    watch_flagged: int
    below_floor: int


# --- pure decision functions -----------------------------------------------------------


def ols_slope(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Ordinary-least-squares slope of ``ys`` on ``xs``. ``None`` if it is not defined
    (fewer than two points, or every ``x`` identical). Pure; no numpy dependency."""

    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n
    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    if sxx == 0.0:
        return None
    sxy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return sxy / sxx


def classify_trajectory(slope: float | None, epsilon: float) -> str:
    """``slope > +epsilon`` -> improving; ``slope < -epsilon`` -> needs_attention;
    ``|slope| <= epsilon`` -> stable; ``slope is None`` -> unknown.

    The boundary is exact and tested (gate 8): a slope of *exactly* ``+epsilon`` is
    ``stable`` (not improving); *exactly* ``-epsilon`` is ``stable`` (not needs_attention).
    """

    if slope is None:
        return _TRAJECTORY_UNKNOWN
    if slope > epsilon:
        return _TRAJECTORY_IMPROVING
    if slope < -epsilon:
        return _TRAJECTORY_NEEDS_ATTENTION
    return _TRAJECTORY_STABLE


def trailing_trajectory(
    points: Sequence[tuple[int, float | None]],
    *,
    t: int,
    window: int = TRAJECTORY_WINDOW,
    epsilon: float,
) -> str:
    """Trajectory from ``(session_number, value)`` pairs for one learner.

    Keeps sessions ``<= t`` with a non-null value, takes the trailing ``window`` of them by
    session number, and classifies the OLS slope. **Fewer than 3 usable points -> unknown**
    (D11 / backend_plan.md section 6.3), never ``stable`` -- "we don't know yet" is a
    first-class answer, and ``stable`` is a claim in a system whose target is flatness.

    ``session_number`` is the x-axis (not a 0..w index) so a gap between sessions is
    reflected in the slope rather than silently compressed.
    """

    usable = sorted(
        ((s, v) for s, v in points if s <= t and v is not None),
        key=lambda pair: pair[0],
    )
    usable = usable[-window:]
    if len(usable) < 3:
        return _TRAJECTORY_UNKNOWN
    xs = [float(s) for s, _ in usable]
    ys = [float(v) for _, v in usable]
    return classify_trajectory(ols_slope(xs, ys), epsilon)


def compute_watch_flag(predicted_class: int | None, sessions_completed: int) -> bool:
    """D5 / D14, and the Python mirror of ``ck_t3_predictions_watch_flag``'s
    ``watch_flag = (COALESCE(predicted_class, -1) >= 1 AND sessions_completed >= 3)``.

    The ``COALESCE`` is load-bearing (trap 2): ``predicted_class`` is nullable -- a learner
    below the warm-up floor has no prediction. A bare ``predicted_class >= 1`` would be NULL
    for those rows, and PostgreSQL PASSES a CHECK on NULL, so the guarantee would evaporate
    exactly on the Getting Started learners. Here the ``-1`` default forces FALSE.
    """

    coalesced = predicted_class if predicted_class is not None else -1
    return coalesced >= 1 and sessions_completed >= WARMUP_FLOOR


def evidence_status_for(sessions_completed: int) -> str:
    """backend_plan.md section 6.1 / trap 7.

    ``sessions_completed < 3`` -> ``insufficient_exposure`` (no watch judgement). Otherwise
    ``sufficient_evidence``.

    The three retrospective statuses (``insufficient_future_evidence``,
    ``censored_by_observation_end``, ``administratively_missing``) are assessed against the
    ``t+1..t+5`` outcome window -- that window is out of scope for B5.1 (no ``future_*``
    fields; the explanation/outcome-window layer is B5.2). On the research dataset every
    supervised-grid row has ``sessions_observed == t >= 3``, so all rows resolve to
    ``sufficient_evidence`` here, which matches the ``warmup_floor = 3`` recorded in the
    produced training table.
    """

    if sessions_completed < WARMUP_FLOOR:
        return EVIDENCE_INSUFFICIENT_EXPOSURE
    return EVIDENCE_SUFFICIENT


def assign_ranks_within_t(rows: list[dict[str, Any]]) -> None:
    """Set ``rank_within_t`` / ``rank_percentile_within_t`` in place, per trap 1.

    Only rows that carry a ``prob_class_2plus`` (i.e. were scored -- at or above the warm-up
    floor) are ranked. Rows are grouped by ``t`` and never compared across ``t``.

    Order: ``prob_class_2plus`` descending, ties broken by ascending ``str(student_id)`` --
    deterministic, so identical inputs give identical order (gate 7 / test 12).

    ``rank_within_t`` is 1-based (1 = most elevated at that ``t``).
    ``rank_percentile_within_t = (n_at_t - rank_within_t + 1) / n_at_t`` in ``(0, 1]`` --
    1.0 for the top-ranked learner, ``1/n`` for the last. Unscored rows get NULL for both.
    """

    by_t: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        row["rank_within_t"] = None
        row["rank_percentile_within_t"] = None
        if row.get("prob_class_2plus") is None:
            continue
        by_t.setdefault(row["t"], []).append(row)

    for _t, group in by_t.items():
        group.sort(key=lambda r: (-r["prob_class_2plus"], str(r["student_id"])))
        n = len(group)
        for index, row in enumerate(group):
            rank = index + 1
            row["rank_within_t"] = rank
            row["rank_percentile_within_t"] = (n - rank + 1) / n


# --- row construction (pure) ---------------------------------------------------------


@dataclass
class _Snapshot:
    student_id: uuid.UUID
    t: int
    features: dict[str, Any]


def _sessions_completed_from_features(features: dict[str, Any], t: int) -> int:
    value = features.get(_SESSIONS_COMPLETED_FEATURE)
    if value is None:
        return 0
    return int(round(float(value)))


def build_prediction_rows(
    *,
    snapshots: Sequence[_Snapshot],
    panel_by_student: dict[uuid.UUID, list[tuple[int, float | None, float | None]]],
    model: LoadedModel,
    model_version: str,
    feature_version: str,
    pipeline_run_id: uuid.UUID,
    inference_timestamp: dt.datetime,
) -> list[dict[str, Any]]:
    """Turn scored snapshots + panel history into ``t3_predictions`` insert dicts. Pure --
    no database.

    ``panel_by_student`` maps ``student_id`` to ``(intervention_session_number,
    b_accuracy_rate, c_engagement_score)`` triples covering every session the panel holds
    for that learner (not only the snapshot grid) -- the trailing-window trajectories need
    the between-snapshot sessions.
    """

    rows: list[dict[str, Any]] = []
    for snap in snapshots:
        sessions_completed = _sessions_completed_from_features(snap.features, snap.t)
        evidence = evidence_status_for(sessions_completed)

        if sessions_completed >= WARMUP_FLOOR:
            scored = model_loading.score_snapshot(model, snap.features)
            prob_0 = scored["prob_class_0"]
            prob_1 = scored["prob_class_1"]
            prob_2plus = scored["prob_class_2plus"]
            predicted_class: int | None = scored["predicted_class"]
        else:
            # Below the warm-up floor: an evidence_status and NO watch judgement (trap 7).
            prob_0 = prob_1 = prob_2plus = None
            predicted_class = None

        watch_flag = compute_watch_flag(predicted_class, sessions_completed)

        # B5.2 -- the explanation layer. Precomputed here at write time because an
        # explanation is stable for a fixed (model, snapshot) pair. Below the warm-up floor
        # `predicted_class` is None and both stay NULL: no judgement, so nothing to explain.
        risk_explanation, shap_top3 = explanation.explain_snapshot(
            model,
            snap.features,
            predicted_class=predicted_class,
            watch_flag=watch_flag,
        )

        panel_points = panel_by_student.get(snap.student_id, [])
        practice_points = [(s, b_acc) for s, b_acc, _c_eng in panel_points]
        engagement_points = [(s, c_eng) for s, _b_acc, c_eng in panel_points]

        practice_trajectory = trailing_trajectory(
            practice_points, t=snap.t, epsilon=EPSILON_PRACTICE
        )
        engagement_trajectory = trailing_trajectory(
            engagement_points, t=snap.t, epsilon=EPSILON_ENGAGEMENT
        )

        rows.append(
            {
                "student_id": snap.student_id,
                "t": snap.t,
                "model_version": model_version,
                "evidence_status": evidence,
                "sessions_completed": sessions_completed,
                "prob_class_0": prob_0,
                "prob_class_1": prob_1,
                "prob_class_2plus": prob_2plus,
                "predicted_class": predicted_class,
                "watch_flag": watch_flag,
                "rank_within_t": None,  # filled by assign_ranks_within_t
                "rank_percentile_within_t": None,
                "practice_trajectory": practice_trajectory,
                "engagement_trajectory": engagement_trajectory,
                "risk_explanation": risk_explanation,
                "shap_top3": shap_top3,
                # No validated tier exists. risk_level stays NULL; risk_level_status keeps
                # its CALIBRATION_PENDING server default (not set here).
                "risk_level": None,
                "feature_version": feature_version,
                "artefact_sha256": model.artefact_sha256,
                "inference_timestamp": inference_timestamp,
                "pipeline_run_id": pipeline_run_id,
                "source_class": SOURCE_CLASS,
                "source_system": SOURCE_SYSTEM,
                "parameter_source_status": PARAMETER_SOURCE_STATUS,
            }
        )

    assign_ranks_within_t(rows)
    return rows


# --- database orchestration ---------------------------------------------------------


async def _load_snapshots(
    session: AsyncSession, *, pipeline_run_id: uuid.UUID, feature_version: str
) -> list[_Snapshot]:
    run_exists = await session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_run_id == pipeline_run_id)
    )
    if not run_exists:
        raise PipelineRunNotFoundError(
            f"pipeline_run_id={pipeline_run_id} has no t3_pipeline_runs row"
        )

    result = await session.execute(
        select(
            FeaturesAtT.student_id,
            FeaturesAtT.t.label("snapshot_t"),
            FeaturesAtT.features,
        ).where(
            FeaturesAtT.pipeline_run_id == pipeline_run_id,
            FeaturesAtT.feature_version == feature_version,
        )
    )
    snapshots = [
        _Snapshot(
            student_id=row._mapping["student_id"],
            t=row._mapping["snapshot_t"],
            features=row._mapping["features"],
        )
        for row in result
    ]
    if not snapshots:
        raise FeatureMatrixEmptyError(
            f"t3_features_at_t has no rows for pipeline_run_id={pipeline_run_id} "
            f"feature_version={feature_version!r}"
        )
    return snapshots


async def _load_panel_history(
    session: AsyncSession, *, pipeline_run_id: uuid.UUID
) -> dict[uuid.UUID, list[tuple[int, float | None, float | None]]]:
    """``student_id -> [(intervention_session_number, b_accuracy_rate, c_engagement_score)]``
    for every panel row of this run -- the raw per-session measures the trajectories slope."""

    result = await session.execute(
        text(
            "SELECT student_id, intervention_session_number, b_accuracy_rate, "
            "c_engagement_score FROM t3_panel WHERE pipeline_run_id = :run"
        ),
        {"run": pipeline_run_id},
    )
    history: dict[uuid.UUID, list[tuple[int, float | None, float | None]]] = {}
    for row in result:
        history.setdefault(row.student_id, []).append(
            (
                row.intervention_session_number,
                row.b_accuracy_rate,
                row.c_engagement_score,
            )
        )
    return history


async def run_decision_layer(
    session: AsyncSession,
    *,
    pipeline_run_id: uuid.UUID,
    model: LoadedModel,
    model_version: str,
    feature_version: str,
    inference_timestamp: dt.datetime | None = None,
) -> DecisionResult:
    """Score the persisted 58-column matrix for ``pipeline_run_id`` and write
    ``t3_predictions`` -- evidence status, watch flag, within-``t`` rank, both trajectories,
    full provenance.

    Single transaction: any failure (contract violation, empty matrix, row-count mismatch)
    rolls the whole write back. Never a partial predictions generation. The model contract
    is checked BEFORE the transaction opens, so a mismatch aborts before any write.
    """

    assert_matches_model_contract(model)
    inference_timestamp = inference_timestamp or dt.datetime.now(dt.timezone.utc)

    async with session.begin():
        snapshots = await _load_snapshots(
            session, pipeline_run_id=pipeline_run_id, feature_version=feature_version
        )
        panel_by_student = await _load_panel_history(
            session, pipeline_run_id=pipeline_run_id
        )

        rows = build_prediction_rows(
            snapshots=snapshots,
            panel_by_student=panel_by_student,
            model=model,
            model_version=model_version,
            feature_version=feature_version,
            pipeline_run_id=pipeline_run_id,
            inference_timestamp=inference_timestamp,
        )

        if rows:
            await session.execute(insert(Prediction), rows)

        actual_count = await session.scalar(
            select(func.count())
            .select_from(Prediction)
            .where(
                Prediction.pipeline_run_id == pipeline_run_id,
                Prediction.model_version == model_version,
            )
        )
        if actual_count != len(rows):
            raise PredictionRowCountMismatchError(
                pipeline_run_id, len(rows), actual_count or 0
            )

    return DecisionResult(
        pipeline_run_id=pipeline_run_id,
        model_version=model_version,
        feature_version=feature_version,
        rows_written=len(rows),
        watch_flagged=sum(1 for r in rows if r["watch_flag"]),
        below_floor=sum(1 for r in rows if r["predicted_class"] is None),
    )


async def _amain() -> None:  # pragma: no cover - operational entrypoint
    """``python -m app.application.decision_layer`` -- run against the direct (5432) database.

    Reads ``DATABASE_URL``, ``T3_PIPELINE_RUN_ID``, ``T3_ACTIVE_MODEL_VERSION`` and
    ``T3_ARTEFACT_STORE_PATH`` from the environment. Same direct-connection shape as
    ``feature_persistence`` / ``t3_loader`` -- deliberately not the API (pooler) engine.
    """

    import os
    from pathlib import Path

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.db.engine import create_direct_engine

    engine, target = create_direct_engine(os.environ["DATABASE_URL"])
    print(f"decision_layer target: {target}")

    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        model_version = os.environ.get("T3_ACTIVE_MODEL_VERSION", "1.0.0")
        artefact_store = Path(os.environ["T3_ARTEFACT_STORE_PATH"])
        artefact_path = model_loading.resolve_artefact_path(artefact_store, model_version)
        model = model_loading.load_model(artefact_path, model_version=model_version)

        async with maker() as session:
            result = await run_decision_layer(
                session,
                pipeline_run_id=uuid.UUID(os.environ["T3_PIPELINE_RUN_ID"]),
                model=model,
                model_version=model_version,
                feature_version=model_version,
            )
    finally:
        await engine.dispose()

    print(
        f"pipeline_run_id={result.pipeline_run_id} rows_written={result.rows_written} "
        f"watch_flagged={result.watch_flagged} below_floor={result.below_floor}"
    )


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(_amain())
