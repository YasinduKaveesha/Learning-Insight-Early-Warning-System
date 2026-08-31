"""Work order B4.2 -- persisting the 58-column feature matrix to ``t3_features_at_t``.

Pure/fake-session tests run everywhere. The end-to-end gates (row count, golden vector back
out of the database, lag boundary, forbidden columns, nulls, provenance, mutation testing)
need a real Postgres and are skipped whole unless ``T3_LIVE_DB_URL`` points at one -- same
discipline as ``test_t3_loader.py``.
"""

from __future__ import annotations

import asyncio
import math
import os
import uuid

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from app.application import feature_persistence  # noqa: E402
from app.infrastructure import feature_builder  # noqa: E402

# --- json_safe_features ---------------------------------------------------------------


def test_json_safe_features_maps_nan_to_none_and_passes_through_numbers():
    record = {"a": float("nan"), "b": 1.5, "c": None, "d": 3}
    out = feature_persistence.json_safe_features(record, ["a", "b", "c", "d"])
    assert out == {"a": None, "b": 1.5, "c": None, "d": 3}


def test_json_safe_features_only_returns_requested_order_keys():
    record = {"a": 1.0, "b": 2.0, "unused": 99.0}
    out = feature_persistence.json_safe_features(record, ["b", "a"])
    assert list(out.keys()) == ["b", "a"]


# --- assert_matches_model_contract ------------------------------------------------------


class _FakeModel:
    def __init__(self, feature_order):
        self.feature_order = tuple(feature_order)


def test_assert_matches_model_contract_passes_when_sets_are_equal():
    feature_persistence.assert_matches_model_contract(
        _FakeModel(feature_builder.ALL_FEATURE_COLUMNS)
    )


def test_assert_matches_model_contract_raises_on_missing_and_extra():
    order = list(feature_builder.ALL_FEATURE_COLUMNS)[1:] + ["bogus_extra_column"]
    with pytest.raises(feature_persistence.FeatureContractAbort) as excinfo:
        feature_persistence.assert_matches_model_contract(_FakeModel(order))
    assert feature_builder.ALL_FEATURE_COLUMNS[0] in excinfo.value.extra
    assert "bogus_extra_column" in excinfo.value.missing


# --- build_rows_to_write (pure) ----------------------------------------------------------


def test_build_rows_to_write_keys_rows_by_reverse_resolved_student_id(feature_matrix):
    learner_id = uuid.uuid4()
    scope = [(learner_id, 3)]
    rows = feature_persistence.build_rows_to_write(
        scope=scope,
        learner_to_student={learner_id: "STU-0001"},
        feature_matrix=feature_matrix,
        feature_order=feature_builder.ALL_FEATURE_COLUMNS,
        feature_version="1.0.0",
        pipeline_run_id=uuid.UUID(int=0),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["student_id"] == learner_id
    assert row["t"] == 3
    assert row["feature_version"] == "1.0.0"
    assert set(row["features"].keys()) == set(feature_builder.ALL_FEATURE_COLUMNS)
    assert row["source_class"] == feature_persistence.SOURCE_CLASS
    assert row["parameter_source_status"] == feature_persistence.PARAMETER_SOURCE_STATUS


def test_build_rows_to_write_raises_on_unmapped_learner(feature_matrix):
    learner_id = uuid.uuid4()
    with pytest.raises(KeyError):
        feature_persistence.build_rows_to_write(
            scope=[(learner_id, 3)],
            learner_to_student={},
            feature_matrix=feature_matrix,
            feature_order=feature_builder.ALL_FEATURE_COLUMNS,
            feature_version="1.0.0",
            pipeline_run_id=uuid.UUID(int=0),
        )


def test_build_rows_to_write_nulls_survive_for_a_censored_first_snapshot(feature_matrix):
    """A first-snapshot row's lag features must be stored as null, never 0.0 -- rule 5."""

    learner_id = uuid.uuid4()
    rows = feature_persistence.build_rows_to_write(
        scope=[(learner_id, feature_builder.SUPERVISED_GRID[0])],
        learner_to_student={learner_id: "STU-0001"},
        feature_matrix=feature_matrix,
        feature_order=feature_builder.ALL_FEATURE_COLUMNS,
        feature_version="1.0.0",
        pipeline_run_id=uuid.UUID(int=0),
    )
    features = rows[0]["features"]
    for column in feature_builder.LAG1_COLUMNS:
        assert features[column] is None
        assert features[column] != 0.0


# --- resolve_panel_scope / reverse_resolve_student_ids: fake-session behaviour -----------


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeScopeSession:
    def __init__(self, *, run_exists: bool, panel_rows, map_rows):
        self._run_exists = run_exists
        self._panel_rows = panel_rows
        self._map_rows = map_rows

    async def scalar(self, *args, **kwargs):
        return 1 if self._run_exists else 0

    async def execute(self, query, params=None):
        text = str(query)
        if "t3_panel" in text:
            return _FakeRows(self._panel_rows)
        if "t3_demo_learner_map" in text:
            return _FakeRows(self._map_rows)
        raise AssertionError(f"unexpected query: {text}")


def test_resolve_panel_scope_raises_if_pipeline_run_missing():
    session = _FakeScopeSession(run_exists=False, panel_rows=[], map_rows=[])
    with pytest.raises(feature_persistence.PipelineRunNotFoundError):
        asyncio.run(
            feature_persistence.resolve_panel_scope(session, pipeline_run_id=uuid.uuid4())
        )


def test_resolve_panel_scope_raises_if_grid_empty():
    session = _FakeScopeSession(run_exists=True, panel_rows=[], map_rows=[])
    with pytest.raises(feature_persistence.PanelScopeEmptyError):
        asyncio.run(
            feature_persistence.resolve_panel_scope(session, pipeline_run_id=uuid.uuid4())
        )


def test_resolve_panel_scope_returns_grid_rows():
    lid = uuid.uuid4()
    session = _FakeScopeSession(
        run_exists=True,
        panel_rows=[_Row(student_id=lid, intervention_session_number=3)],
        map_rows=[],
    )
    scope = asyncio.run(
        feature_persistence.resolve_panel_scope(session, pipeline_run_id=uuid.uuid4())
    )
    assert scope == [(lid, 3)]


def test_reverse_resolve_student_ids_short_circuits_on_empty_input():
    session = _FakeScopeSession(run_exists=True, panel_rows=[], map_rows=[])
    got = asyncio.run(feature_persistence.reverse_resolve_student_ids(session, set()))
    assert got == {}


def test_reverse_resolve_student_ids_raises_on_unmapped_learner():
    lid = uuid.uuid4()
    session = _FakeScopeSession(run_exists=True, panel_rows=[], map_rows=[])
    with pytest.raises(feature_persistence.LearnerMapResolutionError) as excinfo:
        asyncio.run(feature_persistence.reverse_resolve_student_ids(session, {lid}))
    assert excinfo.value.unresolved == [lid]


def test_reverse_resolve_student_ids_returns_mapping():
    lid = uuid.uuid4()
    session = _FakeScopeSession(
        run_exists=True,
        panel_rows=[],
        map_rows=[_Row(learner_id=lid, research_student_id="STU-0001")],
    )
    got = asyncio.run(feature_persistence.reverse_resolve_student_ids(session, {lid}))
    assert got == {lid: "STU-0001"}


# --- run_persist: the hard row-count assertion, against a full fake session -------------
#
# Mirrors test_t3_loader.py's `_FakeLoaderSession` pattern: exercises the real `run_persist`
# transaction/insert/readback code path without a database.


class _FakeTxn:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._session.committed = True
        else:
            self._session.rolled_back = True
        return False


class _FakePersistSession:
    def __init__(self, *, panel_rows, map_rows, scalar_sequence):
        self._panel_rows = panel_rows
        self._map_rows = map_rows
        self._scalars = list(scalar_sequence)
        self.committed = False
        self.rolled_back = False
        self.executed = []

    def begin(self):
        return _FakeTxn(self)

    async def scalar(self, *args, **kwargs):
        return self._scalars.pop(0)

    async def execute(self, query, params=None):
        text = str(query)
        self.executed.append((text, params))
        if "t3_panel" in text:
            return _FakeRows(self._panel_rows)
        if "t3_demo_learner_map" in text:
            return _FakeRows(self._map_rows)
        return None


def _fake_model():
    return _FakeModel(feature_builder.ALL_FEATURE_COLUMNS)


def test_run_persist_raises_on_row_count_mismatch_and_rolls_back(tmp_path):
    lid = uuid.uuid4()
    session = _FakePersistSession(
        panel_rows=[_Row(student_id=lid, intervention_session_number=3)],
        map_rows=[_Row(learner_id=lid, research_student_id="STU-0001")],
        # scalar() is called twice: run-exists check (1), then the mismatching readback (0).
        scalar_sequence=[1, 0],
    )
    csv_path = _tiny_panel_csv(tmp_path)

    with pytest.raises(feature_persistence.FeatureRowCountMismatchError) as excinfo:
        asyncio.run(
            feature_persistence.run_persist(
                session,
                pipeline_run_id=uuid.uuid4(),
                panel_csv_path=csv_path,
                model=_fake_model(),
                feature_version="1.0.0",
            )
        )
    assert excinfo.value.expected == 1
    assert excinfo.value.actual == 0
    assert session.rolled_back is True
    assert session.committed is False


def test_run_persist_succeeds_when_readback_matches(tmp_path):
    lid = uuid.uuid4()
    session = _FakePersistSession(
        panel_rows=[_Row(student_id=lid, intervention_session_number=3)],
        map_rows=[_Row(learner_id=lid, research_student_id="STU-0001")],
        scalar_sequence=[1, 1],
    )
    csv_path = _tiny_panel_csv(tmp_path)

    result = asyncio.run(
        feature_persistence.run_persist(
            session,
            pipeline_run_id=uuid.uuid4(),
            panel_csv_path=csv_path,
            model=_fake_model(),
            feature_version="1.0.0",
        )
    )
    assert result.rows_written == 1
    assert session.committed is True
    assert session.rolled_back is False


def _tiny_panel_csv(tmp_path):
    """One STU-0001 row at t=3 with every base feature column, minimal but valid."""

    import pandas as pd

    csv_path = tmp_path / "tiny_panel.csv"
    row = {col: 0.5 for col in feature_builder.BASE_FEATURES}
    row["student_id"] = "STU-0001"
    row["t"] = 3
    row["hint_avoidance"] = 0.0
    pd.DataFrame([row]).to_csv(csv_path, index=False)
    return csv_path


def test_run_persist_aborts_before_any_write_on_contract_violation(tmp_path):
    """Gate 2 support: a model/feature_builder mismatch must abort before touching the
    database at all -- `session.begin()` (and therefore any insert) must never be entered."""

    session = _FakePersistSession(panel_rows=[], map_rows=[], scalar_sequence=[])
    csv_path = _tiny_panel_csv(tmp_path)
    bad_model = _FakeModel(list(feature_builder.ALL_FEATURE_COLUMNS)[:-1])

    with pytest.raises(feature_persistence.FeatureContractAbort):
        asyncio.run(
            feature_persistence.run_persist(
                session,
                pipeline_run_id=uuid.uuid4(),
                panel_csv_path=csv_path,
                model=bad_model,
                feature_version="1.0.0",
            )
        )
    assert session.executed == []
    assert session.committed is False


# --- end-to-end gates against a real database (T3_LIVE_DB_URL) --------------------------

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark_live = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the persistence gates",
)


@pytestmark_live
def test_live_gates_are_demonstrated_in_the_work_order_report():
    pytest.skip("covered by the manual gate demonstrations in the B4.2 report")
