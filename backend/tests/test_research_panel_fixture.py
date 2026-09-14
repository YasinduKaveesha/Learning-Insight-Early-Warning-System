"""Guards on the committed `research_panel_min.csv` fixture.

It is a checked-in data file -- a deliberate, narrow exception to the root .gitignore's data
policy (`*.csv`, `dataset/`) so the D18 golden vector runs from a clean clone. Its contents are
therefore a rule 3-F1 surface (`population` / `dd_subtype` must never enter this repo) and must
be guarded by a test, not by reviewer memory.
"""

from __future__ import annotations

import pandas as pd

from app.infrastructure import feature_builder
from tests.conftest import MIN_RESEARCH_PANEL_PATH

EXPECTED_ROW_COUNT = 108
EXPECTED_COLUMN_COUNT = 21  # student_id, t, 19 base features
EXPECTED_LEARNERS = frozenset(
    {
        "STU-0001",
        "STU-0004",
        "STU-0005",
        "STU-0008",
        "STU-0010",
        "STU-0012",
        "STU-0014",
        "STU-0015",
        "STU-0016",
        "STU-0023",
        # Added for D20: the only two hint_intensity-affected learners in the golden test
        # split -- STU-0167 (null at t=3, t=5) and STU-0237 (null at t=3). Without them the
        # suite was green while the D20 bug was live.
        "STU-0167",
        "STU-0237",
    }
)

# feature_builder.FORBIDDEN_COLUMNS governs what must never reach predict_proba, where
# student_id/t are rightly forbidden. This fixture is a different context: student_id and t
# are its required key columns (spec: "student_id, t, and the 19 base features"), so they are
# excluded here. Everything else in FORBIDDEN_COLUMNS, plus the engineered/lag/delta/rollmean
# groups the fixture must not carry (the builder derives those; the fixture supplies raw
# inputs only), stays forbidden.
FORBIDDEN_IN_FIXTURE = (feature_builder.FORBIDDEN_COLUMNS - {"student_id", "t"}) | {
    "risk_level_status",
    "trajectory_indicators_status",
    *feature_builder.MISSINGNESS_INDICATORS,
    *feature_builder.LAG1_COLUMNS,
    *feature_builder.DELTA1_COLUMNS,
    *feature_builder.ROLLMEAN_COLUMNS,
    *feature_builder.INTERACTIONS,
}


def test_research_panel_min_shape() -> None:
    raw = pd.read_csv(MIN_RESEARCH_PANEL_PATH)
    assert raw.shape == (EXPECTED_ROW_COUNT, EXPECTED_COLUMN_COUNT)


def test_research_panel_min_learners_and_grid() -> None:
    raw = pd.read_csv(MIN_RESEARCH_PANEL_PATH)
    assert set(raw["student_id"].unique()) == EXPECTED_LEARNERS
    assert set(raw["t"].unique()) == set(feature_builder.SUPERVISED_GRID)
    assert len(raw) == len(EXPECTED_LEARNERS) * len(feature_builder.SUPERVISED_GRID)


def test_research_panel_min_columns_are_exactly_key_plus_base_features() -> None:
    raw = pd.read_csv(MIN_RESEARCH_PANEL_PATH)
    expected_columns = ("student_id", "t") + feature_builder.BASE_FEATURES
    assert tuple(raw.columns) == expected_columns


def test_research_panel_min_contains_no_forbidden_columns() -> None:
    raw = pd.read_csv(MIN_RESEARCH_PANEL_PATH)
    present_forbidden = FORBIDDEN_IN_FIXTURE.intersection(raw.columns)
    assert present_forbidden == set(), f"forbidden columns present in fixture: {sorted(present_forbidden)}"

    # Named explicitly, not just via the sets above -- these are the two audit labels rule
    # 3-F1 exists to keep out of every model, endpoint and, per this test, every repo file.
    assert "population" not in raw.columns
    assert "dd_subtype" not in raw.columns
