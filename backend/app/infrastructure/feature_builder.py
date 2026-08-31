"""Builds the 58-column model feature matrix from the research dataset panel (decision D15).

Source: `dataset/features/feature_matrix_at_t_seed20260828_n300.csv`, one row per
(student_id, t) for every session t = 1..25. The model was trained on the supervised
snapshot grid only (t in {3,5,7,...,19}); lag/delta/rollmean features read strictly earlier
*snapshots*, not strictly earlier sessions, so the panel is filtered to that grid before any
of those groups is computed -- see dev_docs/ML_BACKEND_HANDOVER_SPEC.md section 5.3 and
notebooks/outputs/tables/24_engineered_feature_matrix.csv, which is keyed the same way.

Rules enforced here (backend_plan.md section 5.2):
  1. Column order for scoring comes from `model.feature_names_in_`, never hardcoded here --
     this module only computes the named columns; `model_loading.score_snapshot` does the
     ordering and raises on any mismatch.
  2. Lags/deltas/rollmeans never cross a student_id boundary -- enforced by `groupby`.
  3. Rolling means exclude the current t -- `shift(1)` before `expanding().mean()`.
  4. Missingness indicators are computed from the raw (pre-imputation) values.
  5. A null stays null through delta/rollmean -- no null is ever coerced to 0.0.
  6. Component B response time and Component C game latency are never merged into one column.
  7. Raw values only -- no log1p, no quantile transform.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SUPERVISED_GRID: tuple[int, ...] = (3, 5, 7, 9, 11, 13, 15, 17, 19)

BASE_FEATURES: tuple[str, ...] = (
    "score_trend_slope",
    "score_avg_recent",
    "mastery_progression_rate",
    "number_sense_mastery",
    "weakest_skill_persistence",
    "rt_change_ratio",
    "rt_variability",
    "rt_accuracy_tradeoff",
    "game_latency_change_ratio",
    "error_recurrence_rate",
    "hint_avoidance",
    "hint_intensity",
    "engagement_decline_rate",
    "frustration_mean",
    "frustration_slope",
    "difficulty_floor_hits",
    "stagnant_skill_count",
    "sessions_observed",
    "slope_censored_count",
)

# The ten bases that get lag1 / delta1 / rollmean_prior siblings -- handover section 5.3-5.5.
LAG_BASES: tuple[str, ...] = (
    "score_trend_slope",
    "score_avg_recent",
    "mastery_progression_rate",
    "number_sense_mastery",
    "weakest_skill_persistence",
    "rt_accuracy_tradeoff",
    "error_recurrence_rate",
    "engagement_decline_rate",
    "frustration_mean",
    "stagnant_skill_count",
)

MISSINGNESS_INDICATORS: tuple[str, ...] = (
    "frustration_mean_missing",
    "rt_variability_missing",
    "zero_accuracy_window",
    "difficulty_floor_hits_missing",
    "c_telemetry_missing",
    "is_first_snapshot",
)

INTERACTIONS: tuple[str, ...] = (
    "engagement_x_frustration",
    "hint_intensity_x_accuracy",
    "stagnant_x_t",
)

LAG1_COLUMNS = tuple(f"{base}_lag1" for base in LAG_BASES)
DELTA1_COLUMNS = tuple(f"{base}_delta1" for base in LAG_BASES)
ROLLMEAN_COLUMNS = tuple(f"{base}_rollmean_prior" for base in LAG_BASES)

ENGINEERED_COLUMNS = MISSINGNESS_INDICATORS + LAG1_COLUMNS + DELTA1_COLUMNS + ROLLMEAN_COLUMNS + INTERACTIONS
ALL_FEATURE_COLUMNS = BASE_FEATURES + ENGINEERED_COLUMNS  # 19 + 6 + 10 + 10 + 10 + 3 = 58

# handover section 5.7 -- must never reach predict_proba.
FORBIDDEN_COLUMNS = frozenset(
    {
        "student_id",
        "t",
        "split",
        "population",
        "dd_subtype",
        "future_stagnant_count",
        "future_stagnant_skills",
        "future_frustration_mean",
        "future_engagement_decline_rate",
        "risk_level",
        "evidence_status",
        "trajectory_indicators",
    }
)

_KEY_COLUMNS = ("student_id", "t")
_RAW_SOURCE_COLUMNS = _KEY_COLUMNS + BASE_FEATURES


def load_research_panel(path: str | Path) -> pd.DataFrame:
    """Load the research feature-at-t panel and restrict it to the supervised snapshot grid.

    Returns one row per (student_id, t), sorted by (student_id, t) ascending -- the ordering
    `build_feature_matrix` depends on for lag/delta/rollmean construction.
    """

    raw = pd.read_csv(path)
    missing = set(_RAW_SOURCE_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"research panel is missing expected columns: {sorted(missing)}")

    panel = raw.loc[raw["t"].isin(SUPERVISED_GRID), list(_RAW_SOURCE_COLUMNS)].copy()
    return panel.sort_values(list(_KEY_COLUMNS)).reset_index(drop=True)


def build_feature_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    """Build the 58-column engineered feature matrix, keyed by (student_id, t).

    `panel` must already be restricted to the supervised snapshot grid, one row per
    (student_id, t), sorted by (student_id, t) -- see `load_research_panel`.
    """

    df = panel.copy()

    # Missingness indicators (5.2) -- computed on the raw values, before any imputation.
    df["frustration_mean_missing"] = df["frustration_mean"].isna().astype(int)
    df["rt_variability_missing"] = df["rt_variability"].isna().astype(int)
    df["zero_accuracy_window"] = df["rt_accuracy_tradeoff"].isna().astype(int)
    df["difficulty_floor_hits_missing"] = df["difficulty_floor_hits"].isna().astype(int)
    df["c_telemetry_missing"] = (
        df["engagement_decline_rate"].isna() | df["frustration_slope"].isna()
    ).astype(int)
    df["is_first_snapshot"] = (df["t"] == SUPERVISED_GRID[0]).astype(int)

    # Lag / delta / rollmean (5.3-5.5) -- grouped by student_id so nothing crosses a learner
    # boundary; rollmean uses shift(1) before expanding() so the current t is excluded.
    grouped = df.groupby("student_id", sort=False)
    for base in LAG_BASES:
        lag = grouped[base].shift(1)
        df[f"{base}_lag1"] = lag
        df[f"{base}_delta1"] = df[base] - lag
        df[f"{base}_rollmean_prior"] = grouped[base].transform(
            lambda s: s.shift(1).expanding().mean()
        )

    # Interactions (5.6) -- same-row fields only, no cross-component or cross-t merge.
    df["engagement_x_frustration"] = df["engagement_decline_rate"] * df["frustration_mean"]
    df["hint_intensity_x_accuracy"] = df["hint_intensity"] * df["score_avg_recent"]
    df["stagnant_x_t"] = df["stagnant_skill_count"] * df["sessions_observed"]

    return df


def feature_row_for(
    matrix: pd.DataFrame, feature_order: tuple[str, ...], *, student_id: str, t: int
) -> dict[str, object]:
    """Extract one (student_id, t) row from `matrix` as a feature dict, keyed exactly by
    `feature_order` (typically `model.feature_names_in_`)."""

    row = matrix.loc[(matrix["student_id"] == student_id) & (matrix["t"] == t)]
    if row.empty:
        raise KeyError(f"no snapshot for student_id={student_id!r} t={t}")

    record = row.iloc[0].to_dict()
    missing = [name for name in feature_order if name not in record]
    if missing:
        raise KeyError(f"feature matrix is missing columns required by the model: {missing}")

    return {name: record[name] for name in feature_order}
