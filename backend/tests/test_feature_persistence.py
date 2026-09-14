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
from app.infrastructure import feature_builder, model_loading  # noqa: E402

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


if _LIVE_URL:
    import json
    import tempfile
    from pathlib import Path

    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

    from app.application import t3_loader as _t3_loader
    from tests.test_t3_loader import (
        _N_STUDENTS,
        _cleanup_fixture,
        _normalise_url,
        _seed_300_learners_and_map,
    )

    # The full 300-student research panel is required for gate 1's 2,700-row count (300 x 9
    # supervised-grid snapshots). It lives outside the repo (dataset/ is gitignored) -- see
    # tests/conftest.py's T3_RESEARCH_PANEL_PATH convention. Fall back to the path this was
    # developed against (a sibling of the LIEWS git root) so these tests actually run here
    # rather than skip, while still honouring the env var when set for other machines/CI.
    _DEFAULT_PANEL_PATH = (
        Path(__file__).resolve().parents[3]
        / "dataset"
        / "features"
        / "feature_matrix_at_t_seed20260828_n300.csv"
    )
    _PANEL_PATH = Path(os.environ.get("T3_RESEARCH_PANEL_PATH", _DEFAULT_PANEL_PATH))

    _ARTEFACT_STORE = Path(__file__).resolve().parents[1] / "artefacts"
    _MODEL_VERSION = "1.0.0"
    _GRID = feature_builder.SUPERVISED_GRID

    def _write_grid_only_source(tmp_path, student_ids):
        """Same shape as test_t3_loader's `_write_synthetic_source`, restricted to the
        9 supervised-grid sessions per learner (2,700 records instead of 7,500) -- panel
        content is irrelevant here (feature values come from the CSV per B4.2), only the
        (student_id, t) scope it establishes matters, so there is no reason to pay for the
        full 25-session write."""

        source_path = tmp_path / "b42a_source.jsonl"
        manifest_path = tmp_path / "b42a_manifest.json"
        manifest_path.write_text(
            json.dumps({"dataset": "b4_2a_fixture", "n_students": len(student_ids)}),
            encoding="utf-8",
        )
        with source_path.open("w", encoding="utf-8") as handle:
            for sid in student_ids:
                for session_no in _GRID:
                    raw = {
                        "mapping": {
                            "student_id": sid,
                            "intervention_session_number": session_no,
                            "intervention_session_date": "2026-01-01",
                            "intervention_session_id": f"{sid}-I-{session_no:03d}",
                            "b_session_id": f"{sid}-B-{session_no:03d}",
                            "c_session_id": f"{sid}-C-{session_no:03d}",
                            "b_present": True,
                            "c_present": True,
                        },
                        "b_to_3": {
                            "accuracy_rate": 0.5,
                            "total_questions": 10,
                            "correct_responses": 5,
                            "hint_requests": 1,
                        },
                        "c_to_3": {
                            "accuracy_rate": 0.5,
                            "task_completion_rate": 0.8,
                            "engagement_score": 0.6,
                        },
                    }
                    handle.write(json.dumps(raw) + "\n")
        return source_path, manifest_path

    async def _cleanup_features_and_fixture(learner_ids, pipeline_run_ids):
        engine = _create_async_engine(_normalise_url(_LIVE_URL))
        try:
            async with engine.begin() as conn:
                for run_id in pipeline_run_ids:
                    await conn.execute(
                        _text("DELETE FROM t3_features_at_t WHERE pipeline_run_id = :run"),
                        {"run": run_id},
                    )
        finally:
            await engine.dispose()
        await _cleanup_fixture(learner_ids, pipeline_run_ids)

    @pytest.fixture(scope="module")
    def persisted_features_300():
        """Seeds 300 b_learners + t3_demo_learner_map rows, loads a grid-only t3_panel via
        t3_loader, persists the 58-column matrix via feature_persistence against the real
        research CSV, and yields (pipeline_run_id, model, student_ids) for the gate tests
        below. Torn down (t3_features_at_t, t3_panel, t3_pipeline_runs, the map, the
        learners) by pipeline_run_id / learner_id regardless of test outcome.
        """

        if not _PANEL_PATH.is_file():
            pytest.skip(
                f"full research panel not found at {_PANEL_PATH} -- set "
                "T3_RESEARCH_PANEL_PATH to run the B4.2a live gates",
                allow_module_level=True,
            )

        pairs = asyncio.run(_seed_300_learners_and_map())
        learner_ids = [lid for lid, _ in pairs]
        student_ids = [sid for _, sid in pairs]
        pipeline_run_ids: list = []

        model = model_loading.load_model(
            model_loading.resolve_artefact_path(_ARTEFACT_STORE, _MODEL_VERSION),
            model_version=_MODEL_VERSION,
        )

        try:
            with tempfile.TemporaryDirectory() as td:
                tmp_dir = Path(td)
                source_path, manifest_path = _write_grid_only_source(tmp_dir, student_ids)

                engine = _create_async_engine(_normalise_url(_LIVE_URL))
                maker = _async_sessionmaker(engine, expire_on_commit=False)
                try:
                    async def _load_and_persist():
                        async with maker() as session:
                            load_result = await _t3_loader.run_load(
                                session,
                                source_path=source_path,
                                manifest_path=manifest_path,
                                resolver=_t3_loader.DemoMapLearnerResolver(session),
                                model_version=_MODEL_VERSION,
                                notes="B4.2a live gate fixture -- grid-only t3_panel scope",
                            )
                        async with maker() as session:
                            persist_result = await feature_persistence.run_persist(
                                session,
                                pipeline_run_id=load_result.pipeline_run_id,
                                panel_csv_path=_PANEL_PATH,
                                model=model,
                                feature_version=_MODEL_VERSION,
                            )
                        return load_result, persist_result

                    load_result, persist_result = asyncio.run(_load_and_persist())
                finally:
                    asyncio.run(engine.dispose())

            pipeline_run_ids.append(load_result.pipeline_run_id)
            # Deliberately no assertion on `persist_result.rows_written` here -- that would
            # pre-empt gate 1 below with a fixture-setup error instead of a clean test
            # failure. Row count is exactly what test_live_row_count_is_2700_for_one_pipeline_run
            # exists to check, read fresh from the database.

            yield load_result.pipeline_run_id, model, student_ids
        finally:
            asyncio.run(_cleanup_features_and_fixture(learner_ids, pipeline_run_ids))

    def _fetch_all_features(pipeline_run_id):
        """(research_student_id, t) -> features dict for every row of this run, read fresh
        from the database via t3_demo_learner_map -- independent of whatever mapping
        `feature_persistence` used internally to write the rows."""

        async def _go():
            engine = _create_async_engine(_normalise_url(_LIVE_URL))
            try:
                async with engine.connect() as conn:
                    rows = await conn.execute(
                        _text(
                            "SELECT m.research_student_id AS sid, f.t AS snapshot_t, f.features "
                            "FROM t3_features_at_t f "
                            "JOIN t3_demo_learner_map m ON m.learner_id = f.student_id "
                            "WHERE f.pipeline_run_id = :run"
                        ),
                        {"run": pipeline_run_id},
                    )
                    # `Row.t` collides with SQLAlchemy's own reserved attribute (hence the
                    # `AS snapshot_t` above) -- use `._mapping` throughout to avoid any
                    # further name collisions with column names this table happens to reuse.
                    return {
                        (row._mapping["sid"], row._mapping["snapshot_t"]): row._mapping["features"]
                        for row in rows
                    }
            finally:
                await engine.dispose()

        return asyncio.run(_go())

    def _row_count(pipeline_run_id):
        async def _go():
            engine = _create_async_engine(_normalise_url(_LIVE_URL))
            try:
                async with engine.connect() as conn:
                    return (
                        await conn.execute(
                            _text(
                                "SELECT count(*) FROM t3_features_at_t "
                                "WHERE pipeline_run_id = :run"
                            ),
                            {"run": pipeline_run_id},
                        )
                    ).scalar_one()
            finally:
                await engine.dispose()

        return asyncio.run(_go())

    # --- gate 1: row count -----------------------------------------------------------

    def test_live_row_count_is_2700_for_one_pipeline_run(persisted_features_300):
        pipeline_run_id, _model, _student_ids = persisted_features_300
        count = _row_count(pipeline_run_id)
        assert count == _N_STUDENTS * len(_GRID) == 2700

    # --- gate 2: golden vector read back out of the database -------------------------

    def test_live_golden_vector_stu_0001_t3_from_the_database(persisted_features_300):
        """STU-0001 at t=3, read out of t3_features_at_t and re-scored with the artefact,
        must reproduce p0=0.570509, p1=0.428692, p2=0.000799 to 1e-6 -- proof that what is
        PERSISTED is what the model was validated on, not just what was built in memory."""

        pipeline_run_id, model, _student_ids = persisted_features_300
        features = _fetch_all_features(pipeline_run_id)[("STU-0001", 3)]
        result = model_loading.score_snapshot(model, features)
        assert result["prob_class_0"] == pytest.approx(0.570509, abs=1e-6)
        assert result["prob_class_1"] == pytest.approx(0.428692, abs=1e-6)
        assert result["prob_class_2plus"] == pytest.approx(0.000799, abs=1e-6)

    # --- gate 3: lag boundary, DB-wide -------------------------------------------------

    def test_live_lag_boundary_holds_across_the_whole_database(persisted_features_300):
        pipeline_run_id, _model, _student_ids = persisted_features_300
        by_key = _fetch_all_features(pipeline_run_id)

        by_student: dict[str, list[int]] = {}
        for sid, t in by_key:
            by_student.setdefault(sid, []).append(t)

        checked_first = 0
        checked_later = 0
        for sid, ts in by_student.items():
            ts.sort()
            first_features = by_key[(sid, ts[0])]
            checked_first += 1
            assert first_features["is_first_snapshot"] == 1
            for column in feature_builder.LAG1_COLUMNS + feature_builder.DELTA1_COLUMNS + feature_builder.ROLLMEAN_COLUMNS:
                assert first_features[column] is None, f"{sid} t={ts[0]}: {column} not null"

            for i in range(1, len(ts)):
                checked_later += 1
                current = by_key[(sid, ts[i])]
                previous = by_key[(sid, ts[i - 1])]
                assert current["is_first_snapshot"] == 0
                for base in feature_builder.LAG_BASES:
                    expected = previous[base]
                    actual = current[f"{base}_lag1"]
                    if expected is None:
                        assert actual is None, f"{sid} t={ts[i]}: {base}_lag1 should be null"
                    else:
                        assert actual == pytest.approx(expected), (
                            f"{sid} t={ts[i]}: {base}_lag1={actual} != prior row {expected}"
                        )

        assert checked_first == _N_STUDENTS
        assert checked_later == _N_STUDENTS * (len(_GRID) - 1)

    # --- gate 4: identity -- a row's features must belong to the learner it is filed
    # under, not merely be internally self-consistent ---------------------------------

    def test_live_stored_features_belong_to_the_mapped_learner(persisted_features_300):
        """Anchors on `score_avg_recent` at each learner's LAST supervised-grid snapshot
        (t=19).

        Why this value: it is a trailing-window average over that specific research
        student's own session history, so for 300 distinct real students it is, in
        practice, a per-student fingerprint -- rebuilding it from the CSV under the
        `t3_demo_learner_map`-resolved `research_student_id` and comparing it against what
        is actually stored under that same `learner_id` in `t3_features_at_t` catches an
        identity mix-up that B4.2 found nothing else catches: swapping one learner's WHOLE
        session history onto another leaves every _within-learner_ check (lag continuity,
        is_first_snapshot, row count) internally self-consistent, because the swapped-in
        history is still a complete, correctly-ordered trajectory -- just the wrong
        child's. Only a value tied to the specific student's own trajectory, checked
        against the specific `research_student_id` the mapping says that row should hold,
        exposes the swap.
        """

        pipeline_run_id, _model, student_ids = persisted_features_300
        stored = _fetch_all_features(pipeline_run_id)

        research_panel = feature_builder.load_research_panel(_PANEL_PATH)
        matrix = feature_builder.build_feature_matrix(research_panel)

        checked = 0
        for sid in student_ids:
            expected_row = feature_builder.feature_row_for(
                matrix, feature_builder.ALL_FEATURE_COLUMNS, student_id=sid, t=_GRID[-1]
            )
            expected_value = expected_row["score_avg_recent"]
            actual_value = stored[(sid, _GRID[-1])]["score_avg_recent"]
            checked += 1
            if expected_value is None:
                assert actual_value is None, f"{sid}: expected null score_avg_recent"
            else:
                assert actual_value == pytest.approx(expected_value, abs=1e-9), (
                    f"{sid}: stored score_avg_recent={actual_value} does not match this "
                    f"student's own recomputed value {expected_value} -- possible identity "
                    "mix-up between learners"
                )

        assert checked == _N_STUDENTS
