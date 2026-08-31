"""Tests 4-9 from backend_plan.md section 9 / handover section 18.

Test 8 (lag boundary) is called out in both source documents as the highest-value test:
lags/deltas/rolling means must never cross a student_id boundary, because that is the one
construction error that *improves* held-out metrics and nothing downstream catches it.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from app.domain.errors import FeatureContractViolation
from app.infrastructure import feature_builder, model_loading


def test_feature_order_matches_model_feature_names_in(loaded_model, feature_matrix) -> None:
    """Test 4 -- constructed frame equals feature_names_in_ element-wise.

    `feature_row_for` returns a dict keyed exactly by the order it is given; passing
    `loaded_model.feature_order` must therefore reproduce that order verbatim, and the set of
    names this module knows how to build must exactly equal the model's feature set.
    """

    assert set(feature_builder.ALL_FEATURE_COLUMNS) == set(loaded_model.feature_order)

    row = feature_builder.feature_row_for(
        feature_matrix, loaded_model.feature_order, student_id="STU-0001", t=3
    )
    assert tuple(row.keys()) == loaded_model.feature_order


def test_no_forbidden_columns_reach_the_model(loaded_model, feature_matrix) -> None:
    """Test 5 -- the section 5.7 exclusion set intersected with input columns is empty."""

    row = feature_builder.feature_row_for(
        feature_matrix, loaded_model.feature_order, student_id="STU-0001", t=3
    )
    assert feature_builder.FORBIDDEN_COLUMNS.isdisjoint(row.keys())
    assert feature_builder.FORBIDDEN_COLUMNS.isdisjoint(loaded_model.feature_order)


def test_no_audit_labels_in_input(research_panel, feature_matrix, loaded_model) -> None:
    """Test 6 -- population, dd_subtype absent from input and from any output this module
    produces. There is no database write in this work order, so "stored output" here means
    the feature matrix and the scored dict."""

    for frame in (research_panel, feature_matrix):
        assert "population" not in frame.columns
        assert "dd_subtype" not in frame.columns

    row = feature_builder.feature_row_for(
        feature_matrix, loaded_model.feature_order, student_id="STU-0001", t=3
    )
    assert "population" not in row
    assert "dd_subtype" not in row


def test_no_future_window_fields(research_panel, feature_matrix, loaded_model) -> None:
    """Test 7 -- no future_* columns reach the model."""

    for frame in (research_panel, feature_matrix):
        assert not any(col.startswith("future_") for col in frame.columns)

    assert not any(name.startswith("future_") for name in loaded_model.feature_order)


def test_lag_boundary_first_snapshot_is_null(feature_matrix) -> None:
    """Test 8a -- every learner's first snapshot has all lag/delta/rollmean features null and
    is_first_snapshot == 1."""

    first_rows = feature_matrix.loc[feature_matrix["t"] == feature_builder.SUPERVISED_GRID[0]]
    assert len(first_rows) > 0

    assert (first_rows["is_first_snapshot"] == 1).all()
    for column in (
        feature_builder.LAG1_COLUMNS + feature_builder.DELTA1_COLUMNS + feature_builder.ROLLMEAN_COLUMNS
    ):
        assert first_rows[column].isna().all(), f"{column} was not null at every first snapshot"


def test_lag_boundary_never_crosses_a_learner(feature_matrix) -> None:
    """Test 8b -- for later snapshots, each _lag1 equals THAT SAME LEARNER's prior row with
    t_prev < t. This is the one error nothing downstream detects (backend_plan.md section 5.2
    rule 2) -- checked directly against an independently-sorted per-student walk, not by
    trusting groupby.shift again."""

    checked_any_later_snapshot = False

    for student_id, group in feature_matrix.groupby("student_id", sort=False):
        rows = group.sort_values("t").reset_index(drop=True)
        for i in range(1, len(rows)):
            checked_any_later_snapshot = True
            current, previous = rows.iloc[i], rows.iloc[i - 1]
            assert previous["t"] < current["t"]
            assert current["is_first_snapshot"] == 0
            for base in feature_builder.LAG_BASES:
                expected = previous[base]
                actual = current[f"{base}_lag1"]
                if pd.isna(expected):
                    assert pd.isna(actual), (
                        f"{student_id} t={current['t']}: {base}_lag1 should be null "
                        f"(prior row null) but was {actual}"
                    )
                else:
                    assert actual == pytest.approx(expected), (
                        f"{student_id} t={current['t']}: {base}_lag1={actual} does not match "
                        f"the same learner's prior row (t={previous['t']}) value {expected}"
                    )

    assert checked_any_later_snapshot


def test_rollmean_prior_excludes_current_t() -> None:
    """Test 8c -- rollmean_prior is the expanding mean of strictly prior snapshots.

    A small synthetic panel makes the exact expected numbers easy to hand-verify, rather than
    trusting the same machinery under test to check itself against the full dataset.
    """

    panel = pd.DataFrame(
        {
            "student_id": ["STU-X"] * 3,
            "t": [3, 5, 7],
            **{base: [0.0, 0.0, 0.0] for base in feature_builder.BASE_FEATURES if base != "score_trend_slope"},
            "score_trend_slope": [1.0, 3.0, 5.0],
        }
    )
    matrix = feature_builder.build_feature_matrix(panel)

    assert pd.isna(matrix.loc[0, "score_trend_slope_rollmean_prior"])
    assert matrix.loc[1, "score_trend_slope_rollmean_prior"] == pytest.approx(1.0)
    assert matrix.loc[2, "score_trend_slope_rollmean_prior"] == pytest.approx((1.0 + 3.0) / 2)


def test_missingness_indicators_precede_imputation_and_nulls_never_become_zero(
    feature_matrix,
) -> None:
    """Test 9 -- nulls reach the imputer, indicators are computed from the raw (pre-impute)
    value, and no null slope-type feature is silently coerced to 0.0 anywhere in this module."""

    null_rt_accuracy = feature_matrix.loc[feature_matrix["rt_accuracy_tradeoff"].isna()]
    assert len(null_rt_accuracy) > 0
    assert (null_rt_accuracy["zero_accuracy_window"] == 1).all()

    present_rt_accuracy = feature_matrix.loc[feature_matrix["rt_accuracy_tradeoff"].notna()]
    assert len(present_rt_accuracy) > 0
    assert (present_rt_accuracy["zero_accuracy_window"] == 0).all()

    # A first-snapshot slope-type feature must be NaN, never 0.0 -- "zero means flat", a claim
    # this module must never manufacture.
    first_rows = feature_matrix.loc[feature_matrix["t"] == feature_builder.SUPERVISED_GRID[0]]
    for column in feature_builder.LAG1_COLUMNS + feature_builder.DELTA1_COLUMNS + feature_builder.ROLLMEAN_COLUMNS:
        assert not (first_rows[column] == 0.0).any()
        assert first_rows[column].isna().all()


def test_score_snapshot_raises_typed_error_on_missing_column(loaded_model) -> None:
    """A feature-contract violation lists the offending names rather than silently dropping
    or defaulting a column -- backend_plan.md section 5.2 and section 8 "Errors"."""

    incomplete_row = {name: 0.0 for name in loaded_model.feature_order if name != "sessions_observed"}
    with pytest.raises(FeatureContractViolation) as excinfo:
        model_loading.score_snapshot(loaded_model, incomplete_row)
    assert "sessions_observed" in excinfo.value.missing


def test_score_snapshot_raises_typed_error_on_extra_column(loaded_model) -> None:
    extra_row = {name: 0.0 for name in loaded_model.feature_order}
    extra_row["population"] = "TD"
    with pytest.raises(FeatureContractViolation) as excinfo:
        model_loading.score_snapshot(loaded_model, extra_row)
    assert "population" in excinfo.value.extra


def test_score_snapshot_handles_null_inputs_via_the_pipelines_imputer(
    loaded_model, feature_matrix
) -> None:
    """Nulls flow through to the model's internal SimpleImputer rather than being pre-imputed
    or defaulted by this module -- backend_plan.md section 5.8."""

    first_row = feature_matrix.loc[feature_matrix["t"] == feature_builder.SUPERVISED_GRID[0]].iloc[0]
    row = {name: first_row[name] for name in loaded_model.feature_order}
    assert any(
        value is None or (isinstance(value, float) and math.isnan(value)) for value in row.values()
    ), "expected at least one null in a first-snapshot row to exercise the imputer"

    result = model_loading.score_snapshot(loaded_model, row)
    probs = (result["prob_class_0"], result["prob_class_1"], result["prob_class_2plus"])
    assert all(0.0 <= p <= 1.0 for p in probs)
