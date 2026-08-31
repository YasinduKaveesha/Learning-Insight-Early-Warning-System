"""Test 10 from backend_plan.md section 9 / handover section 18 -- the golden vector.

Run this first. If it does not reproduce, feature construction is wrong; fix that before
writing anything else built on top of it (backend_plan.md section 5.3 / section 10).

Three tiers, matching what is actually available on a clean clone:
  - the single golden vector (STU-0001, t=3) -- always runs, off the committed 90-row fixture.
  - a 90-row cross-check against the 10 learners in that fixture -- always runs.
  - the full 810-row check against the real research dataset -- skipped unless
    T3_RESEARCH_PANEL_PATH points at it (dataset/ is untracked and outside this repo).
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.infrastructure import feature_builder, model_loading
from tests.conftest import FULL_RESEARCH_PANEL_ENV, FULL_RESEARCH_PANEL_PATH, GOLDEN_PROBABILITIES_PATH

GOLDEN_TOLERANCE = 1e-6


def _max_abs_diff_against_golden(loaded_model, matrix, golden: pd.DataFrame) -> tuple[float, int]:
    max_abs_diff = 0.0
    checked = 0
    for _, record in golden.iterrows():
        row = feature_builder.feature_row_for(
            matrix,
            loaded_model.feature_order,
            student_id=record["student_id"],
            t=int(record["t"]),
        )
        result = model_loading.score_snapshot(loaded_model, row)

        max_abs_diff = max(
            max_abs_diff,
            abs(result["prob_class_0"] - record["prob_class_0"]),
            abs(result["prob_class_1"] - record["prob_class_1"]),
            abs(result["prob_class_2plus"] - record["prob_class_2+"]),
        )
        checked += 1
    return max_abs_diff, checked


def test_golden_vector_stu_0001_t3(loaded_model, feature_matrix) -> None:
    """STU-0001 at t=3 -> p0=0.570509, p1=0.428692, p2=0.000799, tolerance 1e-6.

    Source: notebooks/outputs/tables/57_test_predicted_probabilities.csv.
    Runs off the committed 90-row fixture -- STU-0001 is one of its 10 learners.
    """

    row = feature_builder.feature_row_for(
        feature_matrix, loaded_model.feature_order, student_id="STU-0001", t=3
    )
    result = model_loading.score_snapshot(loaded_model, row)

    assert result["prob_class_0"] == pytest.approx(0.570509, abs=GOLDEN_TOLERANCE)
    assert result["prob_class_1"] == pytest.approx(0.428692, abs=GOLDEN_TOLERANCE)
    assert result["prob_class_2plus"] == pytest.approx(0.000799, abs=GOLDEN_TOLERANCE)
    assert result["predicted_class"] == 0


def test_cross_check_against_committed_fixture(loaded_model, feature_matrix) -> None:
    """All 108 rows for the 12 learners in the committed fixture reproduce their published
    expected probabilities, to the golden-vector tolerance. Always runs on a clean clone.

    STU-0167 and STU-0237 were added for D20: they are hint_intensity-affected in the golden
    test split (null at t=3/t=5 and t=3 respectively), so this now fails on a clean clone if
    the D20 zero-fill regresses -- which the 10-learner fixture could not catch."""

    golden = pd.read_csv(GOLDEN_PROBABILITIES_PATH)
    assert "population" not in golden.columns

    fixture_learners = set(feature_matrix["student_id"].unique())
    relevant_golden = golden.loc[golden["student_id"].isin(fixture_learners)]

    max_abs_diff, checked = _max_abs_diff_against_golden(loaded_model, feature_matrix, relevant_golden)

    assert checked == len(relevant_golden) == 108
    assert max_abs_diff < GOLDEN_TOLERANCE


@pytest.mark.skipif(
    not FULL_RESEARCH_PANEL_PATH,
    reason=(
        f"full research dataset not available -- set {FULL_RESEARCH_PANEL_ENV} to "
        "dataset/features/feature_matrix_at_t_seed20260828_n300.csv for a full-coverage run"
    ),
)
def test_full_table_reproduces_golden_fixture(loaded_model, full_feature_matrix) -> None:
    """Every row of the saved test-set predictions (810 rows, all learners) reproduces from
    this backend's own feature-builder + model pipeline, to the golden-vector tolerance.

    Fixture is `57_test_predicted_probabilities.csv` with the `population` column dropped
    on ingest, per backend_plan.md section 9 test 10. Requires the full out-of-repo research
    dataset -- see T3_RESEARCH_PANEL_PATH in tests/conftest.py.
    """

    golden = pd.read_csv(GOLDEN_PROBABILITIES_PATH)
    assert "population" not in golden.columns

    max_abs_diff, checked = _max_abs_diff_against_golden(loaded_model, full_feature_matrix, golden)

    assert checked == len(golden) == 810
    assert max_abs_diff < GOLDEN_TOLERANCE
