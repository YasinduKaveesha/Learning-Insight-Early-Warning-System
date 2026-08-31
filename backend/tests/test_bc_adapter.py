"""The B/C adapter -- work order B4, gates 5, 6 and 7 (adapter half).

Pure Python: the adapter imports only the standard library, so this runs in the pinned
`c3-ews` env. The mapping unit tests use an inline synthetic record and always run; the
whole-dataset tests skip cleanly when the out-of-repo research dataset is absent (a clean
clone never has `dataset/` -- see conftest).
"""

from __future__ import annotations

import datetime as dt
import inspect
from pathlib import Path

import pytest

from app.infrastructure import bc_adapter

# dataset/ sits above the git root and is untracked.
_DATASET_DIR = Path(__file__).resolve().parents[3] / "dataset" / "source"
_SOURCE = _DATASET_DIR / "so2_joined_dataset_seed20260828_n300.jsonl"
_MANIFEST = _DATASET_DIR / "so2_manifest_seed20260828_n300.json"

_dataset = pytest.mark.skipif(
    not _SOURCE.exists(),
    reason=f"research dataset not present at {_SOURCE} (out-of-repo, see conftest)",
)


# --- an inline record: B and C accuracy differ, all slopes censored -------------------

def _raw(**overrides):
    raw = {
        "student_id": "STU-0001",
        "intervention_session_id": "STU-0001-I-001",
        "intervention_session_number": 1,
        "mapping": {
            "student_id": "STU-0001",
            "intervention_session_id": "STU-0001-I-001",
            "intervention_session_number": 1,
            "intervention_session_date": "2026-01-05",
            "b_session_id": "STU-0001-B-001",
            "c_session_id": "STU-0001-C-001",
            "b_present": True,
            "c_present": True,
        },
        "b_to_3": {
            "mastery_counting": 0.17,
            "mastery_number_sense": 0.22,
            "mastery_place_value": 0.15,
            "mastery_addition": 0.15,
            "mastery_subtraction": 0.15,
            "mastery_multiplication": 0.15,
            "mastery_division": 0.15,
            "total_questions": 2,
            "correct_responses": 1,
            "accuracy_rate": 0.5,
            "hint_requests": 0,
            "b_median_item_response_time_sec": 0.786,
            "b_item_response_time_std_sec": 0.329,
            "mastery_certified": {s: False for s in bc_adapter.SKILLS},
            "error_class_dist": {"correct": 0.5, "off_by_one": 0.5},
            "mastery_slope_w4": {s: None for s in bc_adapter.SKILLS},
            "opportunities_w4": {"counting": 1, "number_sense": 1},
        },
        "c_to_3": {
            "accuracy_rate": 1.0,
            "task_completion_rate": 1.0,
            "c_median_game_task_latency_sec": 11.7145,
            "difficulty_floor_hits": 0,
            "engagement_score": 0.7398,
            "engagement_components": {"completion_component": 1.0},
            "frustration_index": 0.142,
            "frustration_components": {"error_run_component": 0.4},
            "learner_state": "engaged",
            "state_reason": "high_engagement_low_friction",
            "telemetry_quality_status": "complete",
            "current_difficulty_level": 2,
            "difficulty_trend": "increasing",
            "session_technical_issue_flag": False,
            "inactive_time_sec": 5.074,
        },
    }
    raw["mapping"].update(overrides.pop("mapping", {}))
    raw.update(overrides)
    return raw


def test_output_keys_are_a_subset_of_panel_fields():
    record = bc_adapter.map_record(_raw())
    assert set(record).issubset(bc_adapter.PANEL_FIELDS)


def test_gate5_b_and_c_accuracy_land_in_their_own_column_with_their_own_value():
    """A session where b_to_3.accuracy_rate (0.5) and c_to_3.accuracy_rate (1.0) differ."""

    record = bc_adapter.map_record(_raw())
    assert record["b_accuracy_rate"] == 0.5
    assert record["c_accuracy_rate"] == 1.0
    assert "accuracy_rate" not in record  # never one unprefixed field


def test_no_unprefixed_collision_prone_key():
    record = bc_adapter.map_record(_raw())
    for key in record:
        if any(tok in key for tok in ("accuracy", "response_time", "latency", "duration")):
            assert key.startswith(("b_", "c_")), key


def test_gate6_censored_slope_stays_none_not_zero():
    record = bc_adapter.map_record(_raw())
    assert record["b_mastery_slope_w4"] == {s: None for s in bc_adapter.SKILLS}
    assert all(v is None for v in record["b_mastery_slope_w4"].values())


def test_b_mastery_is_jsonb_keyed_by_the_seven_skill_names():
    record = bc_adapter.map_record(_raw())
    assert set(record["b_mastery"]) == set(bc_adapter.SKILLS)
    assert record["b_mastery"]["number_sense"] == 0.22


def test_session_number_is_taken_verbatim_not_derived():
    record = bc_adapter.map_record(_raw(mapping={"intervention_session_number": 17}))
    assert record["intervention_session_number"] == 17


def test_source_ids_and_c_guards_are_mapped():
    record = bc_adapter.map_record(_raw())
    assert record["intervention_session_id"] == "STU-0001-I-001"
    assert record["b_session_id"] == "STU-0001-B-001"
    assert record["c_session_id"] == "STU-0001-C-001"
    assert record["c_session_technical_issue_flag"] is False
    assert record["c_inactive_time_sec"] == 5.074


def test_date_is_a_date():
    record = bc_adapter.map_record(_raw())
    assert record["intervention_session_date"] == dt.date(2026, 1, 5)


# --- gate 7: the adapter must not know dataset/audit/ exists -------------------------

def test_gate7_adapter_source_never_references_the_audit_directory():
    """Grep the adapter's *code* (docstrings stripped) for any reference to the audit path
    or to a derived session ordinal (D9)."""

    import ast

    tree = ast.parse(inspect.getsource(bc_adapter))
    # Drop the module docstring node, then every remaining string literal / comment-free
    # code line is fair game.
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    code = "\n".join(ast.unparse(node) for node in body)
    for needle in ("audit", "ROW_NUMBER", "row_number", "ORDER BY", "created_at"):
        assert needle not in code, f"adapter code references {needle!r}"


def test_gate7_mapped_record_has_no_population_or_dd_subtype_key():
    record = bc_adapter.map_record(_raw())
    assert "population" not in record and "dd_subtype" not in record


# --- whole-dataset checks (skip cleanly when the dataset is out of repo) -------------

@pytest.fixture(scope="module")
def all_records():
    if not _SOURCE.exists():
        pytest.skip(f"research dataset not present at {_SOURCE}")
    return bc_adapter.load_panel_records(_SOURCE)


@_dataset
def test_dataset_yields_7500_records_all_present(all_records):
    assert len(all_records) == 7500
    assert all(r["b_present"] and r["c_present"] for r in all_records)


@_dataset
def test_dataset_no_record_carries_an_audit_label(all_records):
    for r in all_records:
        assert "population" not in r and "dd_subtype" not in r


@_dataset
def test_dataset_has_a_session_with_differing_b_and_c_accuracy(all_records):
    assert any(
        r["b_accuracy_rate"] is not None
        and r["c_accuracy_rate"] is not None
        and r["b_accuracy_rate"] != r["c_accuracy_rate"]
        for r in all_records
    )


@_dataset
def test_dataset_has_censored_slopes_preserved_as_none(all_records):
    assert any(
        r["b_mastery_slope_w4"] is not None
        and any(v is None for v in r["b_mastery_slope_w4"].values())
        for r in all_records
    )


@_dataset
def test_manifest_reads_and_matches_the_dataset():
    manifest = bc_adapter.read_manifest(_MANIFEST)
    assert manifest["n_rows"] == 7500
    assert manifest["global_seed"] == 20260828
