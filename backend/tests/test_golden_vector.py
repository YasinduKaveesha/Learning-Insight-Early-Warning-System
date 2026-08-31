"""Test 10 from backend_plan.md section 9 / handover section 18 -- the golden vector.

Run this first. If it does not reproduce, feature construction is wrong; fix that before
writing anything else built on top of it (backend_plan.md section 5.3 / section 10).
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.infrastructure import feature_builder, model_loading
from tests.conftest import GOLDEN_PROBABILITIES_PATH

GOLDEN_TOLERANCE = 1e-6


def test_golden_vector_stu_0001_t3(loaded_model, feature_matrix) -> None:
    """STU-0001 at t=3 -> p0=0.570509, p1=0.428692, p2=0.000799, tolerance 1e-6.

    Source: notebooks/outputs/tables/57_test_predicted_probabilities.csv.
    """

    row = feature_builder.feature_row_for(
        feature_matrix, loaded_model.feature_order, student_id="STU-0001", t=3
    )
    result = model_loading.score_snapshot(loaded_model, row)

    assert result["prob_class_0"] == pytest.approx(0.570509, abs=GOLDEN_TOLERANCE)
    assert result["prob_class_1"] == pytest.approx(0.428692, abs=GOLDEN_TOLERANCE)
    assert result["prob_class_2plus"] == pytest.approx(0.000799, abs=GOLDEN_TOLERANCE)
    assert result["predicted_class"] == 0


def test_full_table_reproduces_golden_fixture(loaded_model, feature_matrix) -> None:
    """Every row of the saved test-set predictions reproduces from this backend's own
    feature-builder + model pipeline, to the golden-vector tolerance.

    Fixture is `57_test_predicted_probabilities.csv` with the `population` column dropped
    on ingest, per backend_plan.md section 9 test 10.
    """

    golden = pd.read_csv(GOLDEN_PROBABILITIES_PATH)
    assert "population" not in golden.columns

    max_abs_diff = 0.0
    checked = 0
    for _, record in golden.iterrows():
        row = feature_builder.feature_row_for(
            feature_matrix,
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

    assert checked == len(golden) == 810
    assert max_abs_diff < GOLDEN_TOLERANCE
