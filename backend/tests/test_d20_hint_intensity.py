"""Decision D20 regression coverage -- `hint_intensity` reproduces the training encoding.

`docs/06` section 238 defines `hint_intensity` as "null by definition" where the hint rate is
zero, with `hint_avoidance == 1.0` carrying that case. The notebook that produced the training
matrix wrote `0.0` on those rows instead, and `nb05_primary_logreg_armA.joblib` was fitted on
that encoding, so serving must reproduce it (D20; plan/backend_plan.md section 5.2).

The encoding is CONDITIONAL and ASSERTED, never a blanket `fillna(0.0)`: a null `hint_intensity`
on a row where `hint_avoidance != 1.0` is a genuinely missing value and must fail loudly rather
than be silently encoded as "used no hints". These tests fail if that conditional is ever
"simplified" back into an unconditional fill.

Runs off the committed 108-row fixture -- no env var, clean-clone safe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.infrastructure import feature_builder
from tests.conftest import MIN_RESEARCH_PANEL_PATH

# The three rows the D20 fix must zero-fill: STU-0167 is affected at t=3 and t=5, STU-0237 at
# t=3. These are the only hint_intensity-null rows in the committed fixture and they match the
# three rows that failed the 810-row golden check before the fix.
D20_AFFECTED_ROWS = (("STU-0167", 3), ("STU-0167", 5), ("STU-0237", 3))


def test_known_affected_rows_encode_as_structural_zero() -> None:
    matrix = feature_builder.build_feature_matrix(
        feature_builder.load_research_panel(MIN_RESEARCH_PANEL_PATH)
    )

    for student_id, t in D20_AFFECTED_ROWS:
        row = matrix.loc[(matrix["student_id"] == student_id) & (matrix["t"] == t)]
        assert len(row) == 1, f"expected exactly one row for {student_id} t={t}"
        assert row["hint_intensity"].iloc[0] == 0.0
        assert row["hint_avoidance"].iloc[0] == 1.0


def test_biconditional_holds_and_nothing_else_was_altered() -> None:
    raw = pd.read_csv(MIN_RESEARCH_PANEL_PATH)
    matrix = feature_builder.build_feature_matrix(
        feature_builder.load_research_panel(MIN_RESEARCH_PANEL_PATH)
    )

    raw_keyed = raw.set_index(["student_id", "t"])
    built_keyed = matrix.set_index(["student_id", "t"])

    # Every row with hint_avoidance == 1.0 ends up with hint_intensity == 0.0 ...
    avoids = built_keyed.loc[built_keyed["hint_avoidance"] == 1.0, "hint_intensity"]
    assert (avoids == 0.0).all()

    # ... and the ONLY rows whose hint_intensity changed from the raw CSV are the three known
    # affected rows. A blanket fillna(0.0) that touched any other null would fail here.
    changed = [
        key
        for key in raw_keyed.index
        if not _same(raw_keyed.loc[key, "hint_intensity"], built_keyed.loc[key, "hint_intensity"])
    ]
    assert sorted(changed) == sorted(D20_AFFECTED_ROWS)
    assert len(changed) == 3


def _same(a: object, b: object) -> bool:
    a_nan = a is None or (isinstance(a, float) and np.isnan(a))
    b_nan = b is None or (isinstance(b, float) and np.isnan(b))
    if a_nan or b_nan:
        return a_nan and b_nan
    return a == b


def test_raise_names_offending_key_when_avoidance_not_one() -> None:
    panel = feature_builder.load_research_panel(MIN_RESEARCH_PANEL_PATH)
    panel.loc[0, "hint_intensity"] = np.nan
    panel.loc[0, "hint_avoidance"] = 0.5
    offending = (panel.loc[0, "student_id"], int(panel.loc[0, "t"]))

    with pytest.raises(ValueError) as excinfo:
        feature_builder._apply_d20_hint_intensity_encoding(panel)

    message = str(excinfo.value)
    assert str(offending[0]) in message
    assert str(offending[1]) in message


def test_blanket_fillna_guard_zero_avoidance_must_raise() -> None:
    """The load-bearing test: a null hint_intensity with hint_avoidance == 0.0 is genuinely
    missing, not a structural zero. If someone later collapses the conditional into
    `fillna(0.0)`, this row would be silently filled and this test fails."""

    panel = feature_builder.load_research_panel(MIN_RESEARCH_PANEL_PATH)
    panel.loc[0, "hint_intensity"] = np.nan
    panel.loc[0, "hint_avoidance"] = 0.0

    with pytest.raises(ValueError):
        feature_builder._apply_d20_hint_intensity_encoding(panel)
