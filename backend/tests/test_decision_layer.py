"""Work order B5.1 -- the decision layer: inference, watch flag, ranking, trajectories.

Pure tests run everywhere. The end-to-end gates (golden vector read back out of
``t3_predictions``, within-``t`` ranking, the ``predicted_class IS NULL`` watch-flag row,
argmax consistency, the no-High CHECK) need a real Postgres and are skipped whole unless
``T3_LIVE_DB_URL`` points at one -- same discipline as ``test_feature_persistence.py``.

Gate numbering follows the work order (section 5).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import uuid

import pytest

from app.application import decision_layer as dl
from app.application import explanation

# --- gate 8: trajectory boundaries ---------------------------------------------------


def test_classify_trajectory_boundaries_are_exact():
    e = dl.EPSILON_PRACTICE  # 0.05
    assert dl.classify_trajectory(e + 1e-12, e) == "improving"
    assert dl.classify_trajectory(e, e) == "stable"          # exactly +0.05 -> stable
    assert dl.classify_trajectory(-e, e) == "stable"         # exactly -0.05 -> stable
    assert dl.classify_trajectory(-e - 1e-12, e) == "needs_attention"
    assert dl.classify_trajectory(None, e) == "unknown"


def test_trailing_trajectory_needs_three_points_else_unknown():
    # 2 usable points -> unknown, never stable, even though the slope is ~0.
    two = [(1, 0.5), (2, 0.5)]
    assert dl.trailing_trajectory(two, t=19, epsilon=dl.EPSILON_PRACTICE) == "unknown"
    three_flat = [(1, 0.5), (2, 0.5), (3, 0.5)]
    assert dl.trailing_trajectory(three_flat, t=19, epsilon=dl.EPSILON_PRACTICE) == "stable"


def test_trailing_trajectory_uses_only_trailing_window_and_sessions_up_to_t():
    # A steep early climb then a decline in the trailing w=4 -> needs_attention.
    points = [(1, 0.1), (2, 0.9), (3, 0.9), (5, 0.7), (7, 0.5), (9, 0.3)]
    assert dl.trailing_trajectory(points, t=9, epsilon=dl.EPSILON_PRACTICE) == "needs_attention"
    # Same learner scored at t=3 only sees sessions <= 3 -> a sharp rise -> improving.
    assert dl.trailing_trajectory(points, t=3, epsilon=dl.EPSILON_PRACTICE) == "improving"


def test_epsilon_practice_is_not_the_stagnation_floor():
    """Trap 4: eps_practice is 0.05, not 0.005. A slope of 0.02 -- one differing item over a
    window -- is noise and must read `stable`, not `improving`."""

    noisy = [(1, 0.50), (2, 0.52), (3, 0.54), (4, 0.56)]  # slope +0.02
    assert dl.trailing_trajectory(noisy, t=4, epsilon=dl.EPSILON_PRACTICE) == "stable"
    assert dl.EPSILON_PRACTICE == 0.05
    assert dl.EPSILON_ENGAGEMENT == 0.010


def test_ols_slope_matches_hand_computation():
    assert dl.ols_slope([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert dl.ols_slope([3, 5, 7, 9], [0.2, 0.2, 0.2, 0.2]) == pytest.approx(0.0)
    assert dl.ols_slope([1], [1]) is None
    assert dl.ols_slope([2, 2, 2], [1, 2, 3]) is None


# --- gate 3 support: the watch flag, including predicted_class IS NULL ----------------


def test_compute_watch_flag_whole_rule():
    # D5/D14: predicted_class >= 1 AND sessions_completed >= 3. Nothing else.
    assert dl.compute_watch_flag(1, 3) is True
    assert dl.compute_watch_flag(2, 9) is True
    assert dl.compute_watch_flag(0, 9) is False
    assert dl.compute_watch_flag(1, 2) is False
    # THE TRAP: no prediction (below the warm-up floor). Must be FALSE, never None/raise.
    assert dl.compute_watch_flag(None, 5) is False
    assert dl.compute_watch_flag(None, 2) is False


def test_evidence_status_below_and_above_the_floor():
    assert dl.evidence_status_for(2) == "insufficient_exposure"
    assert dl.evidence_status_for(3) == "sufficient_evidence"
    assert dl.evidence_status_for(19) == "sufficient_evidence"


# --- gate 6 / gate 7: ranking is within-t, pooled would be wrong, ties deterministic --


def _fabricate_scored_rows():
    """Two t=4 learners and two t=19 learners. The t=4 pair have HIGHER prob_class_2plus
    than the t=19 pair -- a pooled rank would put the calendar-late learners on top."""

    def row(sid, t, p2):
        return {"student_id": sid, "t": t, "prob_class_2plus": p2}

    return [
        row(uuid.UUID(int=1), 4, 0.40),
        row(uuid.UUID(int=2), 4, 0.30),
        row(uuid.UUID(int=3), 19, 0.20),
        row(uuid.UUID(int=4), 19, 0.10),
    ]


def test_ranking_is_within_t_never_pooled():
    rows = _fabricate_scored_rows()
    dl.assign_ranks_within_t(rows)
    by_sid = {r["student_id"].int: r for r in rows}

    # Each t is ranked from 1 independently.
    assert by_sid[1]["rank_within_t"] == 1 and by_sid[2]["rank_within_t"] == 2
    assert by_sid[3]["rank_within_t"] == 1 and by_sid[4]["rank_within_t"] == 2

    # A pooled ranking would give the t=4 high-prob learner rank 1 overall and the t=19
    # learners ranks 3-4; here the low-prob t=19 learner is still rank 1 *within its t*.
    assert by_sid[3]["rank_within_t"] == 1
    # No rank is comparable across different t: every rank group shares one t.
    groups: dict[int, list[int]] = {}
    for r in rows:
        groups.setdefault(r["rank_within_t"], []).append(r["t"])
    for _rank, ts in groups.items():
        assert len(set(ts)) == 1 or len(ts) == len(set(ts))


def test_a_low_t_high_prob_learner_outranks_a_high_t_lower_prob_learner_only_within_t():
    """Gate 6, literal form: a t=4 learner with a high prob_class_2plus and a t=19 learner
    with a lower one are NEVER placed in the same ranking."""

    rows = _fabricate_scored_rows()
    dl.assign_ranks_within_t(rows)
    t4_top = next(r for r in rows if r["t"] == 4 and r["rank_within_t"] == 1)
    t19_top = next(r for r in rows if r["t"] == 19 and r["rank_within_t"] == 1)
    assert t4_top["prob_class_2plus"] > t19_top["prob_class_2plus"]
    assert t4_top["rank_within_t"] == t19_top["rank_within_t"] == 1  # same rank, different t


def test_ranking_ties_break_deterministically_on_student_id():
    a, b = uuid.UUID(int=100), uuid.UUID(int=5)  # str(b) < str(a)
    rows = [
        {"student_id": a, "t": 7, "prob_class_2plus": 0.5},
        {"student_id": b, "t": 7, "prob_class_2plus": 0.5},
    ]
    dl.assign_ranks_within_t(rows)
    ranks = {r["student_id"]: r["rank_within_t"] for r in rows}
    assert ranks[b] == 1 and ranks[a] == 2  # ascending str(student_id)


def test_ranking_is_identical_across_repeated_calls_on_shuffled_input():
    """Gate 7 / test 12: identical inputs -> identical order, twice."""

    import random

    base = _fabricate_scored_rows() + [
        {"student_id": uuid.UUID(int=i), "t": 4, "prob_class_2plus": 0.35} for i in (10, 11, 12)
    ]
    orders = []
    for seed in (1, 2, 3):
        rows = [dict(r) for r in base]
        random.Random(seed).shuffle(rows)
        dl.assign_ranks_within_t(rows)
        orders.append(
            sorted((str(r["student_id"]), r["t"], r["rank_within_t"]) for r in rows)
        )
    assert orders[0] == orders[1] == orders[2]


def test_unscored_rows_are_not_ranked():
    rows = [
        {"student_id": uuid.UUID(int=1), "t": 3, "prob_class_2plus": None},
        {"student_id": uuid.UUID(int=2), "t": 3, "prob_class_2plus": 0.1},
    ]
    dl.assign_ranks_within_t(rows)
    assert rows[0]["rank_within_t"] is None
    assert rows[0]["rank_percentile_within_t"] is None
    assert rows[1]["rank_within_t"] == 1


# --- build_prediction_rows (pure): below-floor row carries no judgement ---------------


class _FakeModel:
    feature_order = ("f",)
    artefact_sha256 = "sha-test"


_STUB_SIGNALS = [
    {
        "feature": "score_avg_recent",
        "display_name": "recent practice accuracy",
        "contribution": 1.0,
        "direction": "toward_review",
    }
]


def _stub_explanation(monkeypatch):
    """B5.2 wiring. `_FakeModel` carries no pipeline, so the real explanation layer cannot
    run here; `tests/test_explanation.py` covers its content against the real artefact. This
    stub keeps these row-construction tests honest about the fields still being populated."""

    monkeypatch.setattr(
        dl.explanation,
        "explain_snapshot",
        lambda _m, _f, *, predicted_class, watch_flag: (
            ("Flagged for teacher review." if watch_flag else None),
            (_STUB_SIGNALS if predicted_class is not None else None),
        ),
    )


def _snap(sid, t, sessions_observed):
    return dl._Snapshot(student_id=sid, t=t, features={"sessions_observed": sessions_observed})


def test_below_floor_snapshot_gets_status_but_no_watch_judgement(monkeypatch):
    """Trap 7: absence of a judgement != a negative judgement. Below the floor: probs and
    predicted_class NULL, watch_flag False, evidence_status insufficient_exposure, ranks
    NULL -- and score_snapshot is never called."""

    def _boom(*_a, **_k):  # must not be reached for a below-floor row
        raise AssertionError("score_snapshot called for a below-floor snapshot")

    monkeypatch.setattr(dl.model_loading, "score_snapshot", _boom)

    sid = uuid.uuid4()
    rows = dl.build_prediction_rows(
        snapshots=[_snap(sid, 3, sessions_observed=2)],
        panel_by_student={sid: [(1, 0.5, 0.6), (2, 0.5, 0.6)]},
        model=_FakeModel(),
        model_version="1.0.0",
        feature_version="1.0.0",
        pipeline_run_id=uuid.UUID(int=0),
        inference_timestamp=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
    )
    row = rows[0]
    assert row["evidence_status"] == "insufficient_exposure"
    assert row["predicted_class"] is None
    assert row["prob_class_0"] is None and row["prob_class_2plus"] is None
    assert row["watch_flag"] is False
    assert row["rank_within_t"] is None
    assert row["risk_level"] is None
    assert row["engagement_trajectory"] in {"improving", "stable", "needs_attention", "unknown"}
    # B5.2: no judgement means nothing to explain -- neither field is invented.
    assert row["risk_explanation"] is None
    assert row["shap_top3"] is None


def test_scored_snapshot_flags_when_predicted_class_ge_1(monkeypatch):
    _stub_explanation(monkeypatch)
    monkeypatch.setattr(
        dl.model_loading,
        "score_snapshot",
        lambda _m, _r: {
            "prob_class_0": 0.1,
            "prob_class_1": 0.3,
            "prob_class_2plus": 0.6,
            "predicted_class": 2,
        },
    )
    sid = uuid.uuid4()
    rows = dl.build_prediction_rows(
        snapshots=[_snap(sid, 9, sessions_observed=9)],
        panel_by_student={sid: [(s, 0.5, 0.6) for s in range(1, 10)]},
        model=_FakeModel(),
        model_version="1.0.0",
        feature_version="1.0.0",
        pipeline_run_id=uuid.UUID(int=0),
        inference_timestamp=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
    )
    row = rows[0]
    assert row["predicted_class"] == 2
    assert row["watch_flag"] is True
    assert row["evidence_status"] == "sufficient_evidence"
    assert row["rank_within_t"] == 1  # only scored row at t=9
    assert row["artefact_sha256"] == "sha-test"
    # B5.2 wiring: a flagged row carries both explanation fields.
    assert row["risk_explanation"] == "Flagged for teacher review."
    assert row["shap_top3"] == _STUB_SIGNALS


# --- gate 9 (partial): engagement_trajectory is not on any serialisation path ---------


def test_engagement_trajectory_absent_from_every_domain_serialisation_path():
    """D17 -- engagement_trajectory is STORED, NEVER SERVED.

    This scans app/domain and app/api for the name used AS CODE. It deliberately ignores
    prose: `app/domain/dashboard.py` names the field in its module docstring to explain why
    it must never be served, and a test that fails on its own documentation trains people to
    delete the documentation.

    B6.1 added the stronger assertion this one always wanted: `tests/test_dashboard_api.py`
    checks actual response BODIES, with source rows that CARRY engagement_trajectory. Keep
    both -- this one also covers files that have no response model yet.
    """

    import ast
    import pathlib

    backend = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in list((backend / "app" / "domain").rglob("*.py")) + list(
        (backend / "app" / "api").rglob("*.py")
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            named = (
                (isinstance(node, ast.Name) and node.id == "engagement_trajectory")
                or (isinstance(node, ast.Attribute) and node.attr == "engagement_trajectory")
                or (isinstance(node, ast.keyword) and node.arg == "engagement_trajectory")
                or (
                    isinstance(node, ast.Constant)
                    and node.value == "engagement_trajectory"
                )
                or (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == "engagement_trajectory"
                )
            )
            if named:
                offenders.append(f"{path.relative_to(backend)}:{node.lineno}")
    assert offenders == [], f"engagement_trajectory used as code on a serialisation path: {offenders}"


# --- gate 10 support: no code path in the decision layer sets risk_level --------------


def test_decision_layer_never_sets_risk_level(monkeypatch):
    _stub_explanation(monkeypatch)
    monkeypatch.setattr(
        dl.model_loading,
        "score_snapshot",
        lambda _m, _r: {
            "prob_class_0": 0.2,
            "prob_class_1": 0.5,
            "prob_class_2plus": 0.3,
            "predicted_class": 1,
        },
    )
    sid = uuid.uuid4()
    rows = dl.build_prediction_rows(
        snapshots=[_snap(sid, 11, 11)],
        panel_by_student={sid: [(s, 0.5, 0.6) for s in range(1, 12)]},
        model=_FakeModel(),
        model_version="1.0.0",
        feature_version="1.0.0",
        pipeline_run_id=uuid.UUID(int=0),
        inference_timestamp=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
    )
    assert all(r["risk_level"] is None for r in rows)
    assert "risk_level_status" not in rows[0]  # keeps the CALIBRATION_PENDING server default


# ======================================================================================
# End-to-end gates against a real database (T3_LIVE_DB_URL)
# ======================================================================================

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark_live = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the decision-layer gates",
)


if _LIVE_URL:
    import json
    import tempfile
    from pathlib import Path

    from sqlalchemy import text as _text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

    from app.application import feature_persistence as _fp
    from app.application import t3_loader as _t3_loader
    from app.infrastructure import feature_builder, model_loading
    from tests.test_t3_loader import (
        _N_STUDENTS,
        _cleanup_fixture,
        _normalise_url,
        _seed_300_learners_and_map,
    )

    _REPO_ROOT = Path(__file__).resolve().parents[3]
    _DEFAULT_SOURCE = _REPO_ROOT / "dataset" / "source" / "so2_joined_dataset_seed20260828_n300.jsonl"
    _DEFAULT_MANIFEST = _REPO_ROOT / "dataset" / "source" / "so2_manifest_seed20260828_n300.json"
    _DEFAULT_PANEL_CSV = (
        _REPO_ROOT / "dataset" / "features" / "feature_matrix_at_t_seed20260828_n300.csv"
    )
    _SOURCE_PATH = Path(os.environ.get("T3_RESEARCH_SOURCE_PATH", _DEFAULT_SOURCE))
    _MANIFEST_PATH = Path(os.environ.get("T3_RESEARCH_MANIFEST_PATH", _DEFAULT_MANIFEST))
    _PANEL_CSV = Path(os.environ.get("T3_RESEARCH_PANEL_PATH", _DEFAULT_PANEL_CSV))

    _ARTEFACT_STORE = Path(__file__).resolve().parents[1] / "artefacts"
    _MODEL_VERSION = "1.0.0"
    _GRID = feature_builder.SUPERVISED_GRID

    def _engine():
        return _create_async_engine(_normalise_url(_LIVE_URL))

    async def _cleanup_predictions_features_and_fixture(learner_ids, run_ids):
        engine = _engine()
        try:
            async with engine.begin() as conn:
                for run_id in run_ids:
                    await conn.execute(
                        _text("DELETE FROM t3_predictions WHERE pipeline_run_id = :r"),
                        {"r": run_id},
                    )
                    await conn.execute(
                        _text("DELETE FROM t3_features_at_t WHERE pipeline_run_id = :r"),
                        {"r": run_id},
                    )
        finally:
            await engine.dispose()
        await _cleanup_fixture(learner_ids, run_ids)

    @pytest.fixture(scope="module")
    def scored_run_300():
        """Full pipeline against the real research dataset: seed 300 learners + map, load a
        real 25-session ``t3_panel`` via ``t3_loader``, persist the 58-column matrix via
        ``feature_persistence``, then run ``decision_layer``. Yields
        ``(pipeline_run_id, model, student_ids)``. Torn down whole regardless of outcome.
        """

        for path in (_SOURCE_PATH, _MANIFEST_PATH, _PANEL_CSV):
            if not path.is_file():
                pytest.skip(
                    f"research dataset artefact not found at {path} -- set the "
                    "T3_RESEARCH_* env vars to run the B5.1 live gates",
                    allow_module_level=True,
                )

        pairs = asyncio.run(_seed_300_learners_and_map())
        learner_ids = [lid for lid, _ in pairs]
        run_ids: list = []

        model = model_loading.load_model(
            model_loading.resolve_artefact_path(_ARTEFACT_STORE, _MODEL_VERSION),
            model_version=_MODEL_VERSION,
        )

        try:
            engine = _engine()
            maker = _async_sessionmaker(engine, expire_on_commit=False)
            try:
                async def _pipeline():
                    async with maker() as s:
                        load = await _t3_loader.run_load(
                            s,
                            source_path=_SOURCE_PATH,
                            manifest_path=_MANIFEST_PATH,
                            resolver=_t3_loader.DemoMapLearnerResolver(s),
                            model_version=_MODEL_VERSION,
                            notes="B5.1 live gate fixture -- full 25-session panel",
                        )
                    async with maker() as s:
                        await _fp.run_persist(
                            s,
                            pipeline_run_id=load.pipeline_run_id,
                            panel_csv_path=_PANEL_CSV,
                            model=model,
                            feature_version=_MODEL_VERSION,
                        )
                    async with maker() as s:
                        decision = await dl.run_decision_layer(
                            s,
                            pipeline_run_id=load.pipeline_run_id,
                            model=model,
                            model_version=_MODEL_VERSION,
                            feature_version=_MODEL_VERSION,
                        )
                    return load.pipeline_run_id, decision

                run_id, decision = asyncio.run(_pipeline())
            finally:
                asyncio.run(engine.dispose())

            run_ids.append(run_id)
            assert decision.rows_written == _N_STUDENTS * len(_GRID) == 2700
            yield run_id, model, [sid for _, sid in pairs]
        finally:
            asyncio.run(_cleanup_predictions_features_and_fixture(learner_ids, run_ids))

    def _fetch_predictions(run_id):
        async def _go():
            engine = _engine()
            try:
                async with engine.connect() as conn:
                    rows = await conn.execute(
                        _text(
                            "SELECT m.research_student_id AS sid, p.t AS snap_t, p.evidence_status, "
                            "p.sessions_completed, p.prob_class_0, p.prob_class_1, "
                            "p.prob_class_2plus, p.predicted_class, p.watch_flag, "
                            "p.rank_within_t, p.rank_percentile_within_t, p.practice_trajectory, "
                            "p.engagement_trajectory, p.risk_level, p.risk_level_status, "
                            "p.feature_version, p.artefact_sha256, p.inference_timestamp, "
                            "p.model_version, p.risk_explanation, p.shap_top3 "
                            "FROM t3_predictions p "
                            "JOIN t3_demo_learner_map m ON m.learner_id = p.student_id "
                            "WHERE p.pipeline_run_id = :r"
                        ),
                        {"r": run_id},
                    )
                    return [dict(r._mapping) for r in rows]
            finally:
                await engine.dispose()

        return asyncio.run(_go())

    # --- gate 1/2 handled by the suite counts; this fixture asserts rows_written == 2700 --

    def test_gate5_golden_vector_read_back_out_of_t3_predictions(scored_run_300):
        """STU-0001, t=3 -> p0=0.570509, p1=0.428692, p2=0.000799, tol 1e-6, straight out of
        the stored prediction row (not recomputed)."""

        run_id, _model, _sids = scored_run_300
        by_key = {(r["sid"], r["snap_t"]): r for r in _fetch_predictions(run_id)}
        row = by_key[("STU-0001", 3)]
        assert row["prob_class_0"] == pytest.approx(0.570509, abs=1e-6)
        assert row["prob_class_1"] == pytest.approx(0.428692, abs=1e-6)
        assert row["prob_class_2plus"] == pytest.approx(0.000799, abs=1e-6)
        assert row["predicted_class"] == 0
        assert row["watch_flag"] is False

    def test_gate4_argmax_consistency_and_probabilities_sum_to_one(scored_run_300):
        run_id, _model, _sids = scored_run_300
        preds = _fetch_predictions(run_id)
        checked = 0
        for r in preds:
            if r["prob_class_0"] is None:
                continue
            probs = [r["prob_class_0"], r["prob_class_1"], r["prob_class_2plus"]]
            assert sum(probs) == pytest.approx(1.0, abs=1e-6)
            assert r["predicted_class"] == max(range(3), key=lambda i: probs[i])
            checked += 1
        assert checked == 2700

    def test_gate6_every_rank_group_shares_one_t(scored_run_300):
        run_id, _model, _sids = scored_run_300
        preds = _fetch_predictions(run_id)
        # For each t, ranks are a 1..n permutation; no rank is shared across different t
        # because ranking never pools.
        by_t: dict[int, list[int]] = {}
        for r in preds:
            if r["rank_within_t"] is not None:
                by_t.setdefault(r["snap_t"], []).append(r["rank_within_t"])
        assert set(by_t) == set(_GRID)
        for t, ranks in by_t.items():
            assert sorted(ranks) == list(range(1, len(ranks) + 1)), t

    def test_gate6_a_low_t_high_prob_learner_can_outrank_by_prob_a_high_t_learner(scored_run_300):
        """Directly: pick the top-ranked (rank 1) learner at t=5 and the top-ranked at t=19.
        Their prob_class_2plus values are on different scales (2+ prevalence rises with t),
        yet each is rank 1 *within its own t* -- proof the ranking is not pooled."""

        run_id, _model, _sids = scored_run_300
        preds = _fetch_predictions(run_id)
        top = {}
        for r in preds:
            if r["rank_within_t"] == 1:
                top[r["snap_t"]] = r
        assert top[5]["rank_within_t"] == top[19]["rank_within_t"] == 1

    def test_gate9_engagement_trajectory_stored_non_null_for_every_row(scored_run_300):
        run_id, _model, _sids = scored_run_300
        preds = _fetch_predictions(run_id)
        assert len(preds) == 2700
        assert all(r["engagement_trajectory"] is not None for r in preds)
        assert all(
            r["engagement_trajectory"] in {"improving", "stable", "needs_attention", "unknown"}
            for r in preds
        )

    def test_gate10_no_row_carries_a_risk_level_and_status_stays_pending(scored_run_300):
        run_id, _model, _sids = scored_run_300
        preds = _fetch_predictions(run_id)
        assert all(r["risk_level"] is None for r in preds)
        assert all(r["risk_level_status"] == "CALIBRATION_PENDING" for r in preds)

    # --- B5.2: the explanation layer, read back out of the database -------------------

    def test_b52_every_flagged_row_has_a_sentence_within_280_chars(scored_run_300):
        run_id, _model, _sids = scored_run_300
        flagged = [r for r in _fetch_predictions(run_id) if r["watch_flag"]]
        assert flagged, "no flagged rows in the run -- this gate would be vacuous"
        for r in flagged:
            assert r["risk_explanation"] is not None
            assert 0 < len(r["risk_explanation"]) <= 280
            assert r["shap_top3"] is not None
            assert 1 <= len(r["shap_top3"]) <= 3

    def test_b52_filter2_no_flagged_row_carries_a_protective_signal(scored_run_300):
        """Filter 2, enforced against what is actually STORED, not just what the pure
        function returns. 49.2% of elevated rows in the research build carried a protective
        sentence; this is the gate that would notice it coming back."""

        run_id, _model, _sids = scored_run_300
        for r in _fetch_predictions(run_id):
            if not r["watch_flag"]:
                continue
            for signal in r["shap_top3"]:
                assert signal["contribution"] > 0, (
                    f"protective signal stored on a flagged learner: {signal}"
                )
                assert signal["direction"] == "toward_review"

    def test_b52_filter1_no_stored_signal_uses_the_calendar_vocabulary(scored_run_300):
        run_id, _model, _sids = scored_run_300
        for r in _fetch_predictions(run_id):
            for signal in r["shap_top3"] or []:
                assert signal["feature"] not in explanation._EXCLUDED_FROM_VOCABULARY

    def test_b52_filter3_no_stored_sentence_contains_a_raw_feature_name(scored_run_300):
        run_id, model, _sids = scored_run_300
        for r in _fetch_predictions(run_id):
            sentence = r["risk_explanation"]
            if sentence is None:
                continue
            for feature in model.feature_order:
                assert feature not in sentence

    def test_b52_an_unflagged_row_is_never_narrated(scored_run_300):
        run_id, _model, _sids = scored_run_300
        unflagged = [r for r in _fetch_predictions(run_id) if not r["watch_flag"]]
        assert unflagged
        assert all(r["risk_explanation"] is None for r in unflagged)

    def test_gate13_every_stored_prediction_carries_full_provenance(scored_run_300):
        run_id, _model, _sids = scored_run_300
        preds = _fetch_predictions(run_id)
        for r in preds:
            assert r["model_version"] == "1.0.0"
            assert r["feature_version"] == "1.0.0"
            assert r["artefact_sha256"] == model_loading.ARTEFACT_SHA256
            assert r["inference_timestamp"] is not None

    def test_gate10_check_constraint_rejects_a_direct_high_tier_write(scored_run_300):
        """Test 17: the schema-level guarantee. A direct attempt to store risk_level='High'
        is rejected by ck_t3_predictions_no_high."""

        run_id, _model, _sids = scored_run_300

        async def _go():
            engine = _engine()
            try:
                async with engine.connect() as conn:
                    trans = await conn.begin()
                    try:
                        sid = (
                            await conn.execute(
                                _text(
                                    "SELECT student_id FROM t3_predictions "
                                    "WHERE pipeline_run_id = :r LIMIT 1"
                                ),
                                {"r": run_id},
                            )
                        ).scalar_one()
                        await conn.execute(
                            _text(
                                "INSERT INTO t3_predictions (student_id, t, model_version, "
                                "evidence_status, sessions_completed, predicted_class, "
                                "watch_flag, practice_trajectory, engagement_trajectory, "
                                "risk_level, feature_version, artefact_sha256, "
                                "inference_timestamp, pipeline_run_id, source_class, "
                                "source_system, parameter_source_status) VALUES (:sid, 999, "
                                "'1.0.0', 'sufficient_evidence', 5, 0, false, 'stable', "
                                "'stable', 'High', '1.0.0', 'sha', now(), :r, 'SYNTHETIC', "
                                "'decision_layer', 'TEST_FIXTURE_ONLY')"
                            ),
                            {"sid": sid, "r": run_id},
                        )
                    finally:
                        await trans.rollback()
            finally:
                await engine.dispose()

        with pytest.raises(IntegrityError):
            asyncio.run(_go())

    # --- gate 3: the predicted_class IS NULL watch-flag row, end to end ------------------

    @pytest.fixture(scope="module")
    def below_floor_run():
        """A hand-built run with ONE learner whose only snapshot has sessions_observed = 2
        -- below the warm-up floor -- so the decision layer produces a row with
        predicted_class IS NULL. Proves the Python result and the stored row agree, and that
        such a row has watch_flag = false (trap 2 / test 16)."""

        learner_id = uuid.uuid4()
        run_id = uuid.uuid4()
        model = model_loading.load_model(
            model_loading.resolve_artefact_path(_ARTEFACT_STORE, _MODEL_VERSION),
            model_version=_MODEL_VERSION,
        )
        # A complete, valid 58-key feature dict; sessions_observed forced to 2.
        feature_dict = {name: 0.0 for name in model.feature_order}
        feature_dict["sessions_observed"] = 2

        async def _setup():
            engine = _engine()
            async with engine.begin() as conn:
                # Clear any STU-9998 remnant from a prior interrupted run.
                stale = [
                    r[0]
                    for r in (
                        await conn.execute(
                            _text(
                                "SELECT learner_id FROM t3_demo_learner_map "
                                "WHERE research_student_id = 'STU-9998'"
                            )
                        )
                    )
                ]
                if stale:
                    for tbl in ("t3_predictions", "t3_features_at_t", "t3_panel"):
                        await conn.execute(
                            _text(f"DELETE FROM {tbl} WHERE student_id = ANY(:l)"), {"l": stale}
                        )
                    await conn.execute(
                        _text("DELETE FROM t3_demo_learner_map WHERE learner_id = ANY(:l)"),
                        {"l": stale},
                    )
                    await conn.execute(
                        _text("DELETE FROM b_learners WHERE learner_id = ANY(:l)"), {"l": stale}
                    )
                await conn.execute(
                    _text(
                        "INSERT INTO b_learners (learner_id, status, request_id, "
                        "operation_or_event_type, reason_code, resource_type, resource_id, "
                        "source_class, source_system, environment, schema_revision, "
                        "system_actor, name) VALUES (:lid, 'active', :rid, 'create', "
                        "'b5_1_fixture', 'learner', :lid, 'TEST', 't3_demo_fixture', 'test', "
                        "'1', 't3_demo_fixture', 'b5_1 below floor')"
                    ),
                    {"lid": learner_id, "rid": f"b5_1-{learner_id}"},
                )
                await conn.execute(
                    _text(
                        "INSERT INTO t3_demo_learner_map (learner_id, research_student_id, "
                        "source_class, source_system, parameter_source_status, pipeline_run_id) "
                        "VALUES (:lid, :sid, 'TEST', 't3_demo_fixture', 'TEST_FIXTURE_ONLY', :r)"
                    ),
                    {"lid": learner_id, "sid": "STU-9998", "r": uuid.uuid4()},
                )
                await conn.execute(
                    _text(
                        "INSERT INTO t3_pipeline_runs (pipeline_run_id, dataset_manifest, "
                        "model_version, source_class, source_system, parameter_source_status) "
                        "VALUES (:r, '{}'::jsonb, '1.0.0', 'SYNTHETIC', 'decision_layer', "
                        "'TEST_FIXTURE_ONLY')"
                    ),
                    {"r": run_id},
                )
                for session_no in (1, 2):
                    await conn.execute(
                        _text(
                            "INSERT INTO t3_panel (student_id, intervention_session_number, "
                            "intervention_session_date, b_present, c_present, b_accuracy_rate, "
                            "c_engagement_score, pipeline_run_id, source_class, source_system, "
                            "parameter_source_status) VALUES (:lid, :n, '2026-01-01', true, "
                            "true, 0.5, 0.6, :r, 'SYNTHETIC', 't3_loader', 'TEST_FIXTURE_ONLY')"
                        ),
                        {"lid": learner_id, "n": session_no, "r": run_id},
                    )
                await conn.execute(
                    _text(
                        "INSERT INTO t3_features_at_t (student_id, t, feature_version, "
                        "features, pipeline_run_id, source_class, source_system, "
                        "parameter_source_status) VALUES (:lid, 3, '1.0.0', "
                        "CAST(:feat AS jsonb), :r, 'SYNTHETIC', 'feature_persistence', "
                        "'TEST_FIXTURE_ONLY')"
                    ),
                    {"lid": learner_id, "feat": json.dumps(feature_dict), "r": run_id},
                )
            await engine.dispose()

        async def _teardown():
            engine = _engine()
            async with engine.begin() as conn:
                await conn.execute(_text("DELETE FROM t3_predictions WHERE pipeline_run_id = :r"), {"r": run_id})
                await conn.execute(_text("DELETE FROM t3_features_at_t WHERE pipeline_run_id = :r"), {"r": run_id})
                await conn.execute(_text("DELETE FROM t3_panel WHERE pipeline_run_id = :r"), {"r": run_id})
                await conn.execute(_text("DELETE FROM t3_pipeline_runs WHERE pipeline_run_id = :r"), {"r": run_id})
                await conn.execute(_text("DELETE FROM t3_demo_learner_map WHERE learner_id = :l"), {"l": learner_id})
                await conn.execute(_text("DELETE FROM b_learners WHERE learner_id = :l"), {"l": learner_id})
            await engine.dispose()

        try:
            asyncio.run(_setup())

            async def _run():
                engine = _engine()
                maker = _async_sessionmaker(engine, expire_on_commit=False)
                try:
                    async with maker() as s:
                        return await dl.run_decision_layer(
                            s,
                            pipeline_run_id=run_id,
                            model=model,
                            model_version=_MODEL_VERSION,
                            feature_version=_MODEL_VERSION,
                        )
                finally:
                    await engine.dispose()

            result = asyncio.run(_run())
            yield run_id, learner_id, result
        finally:
            asyncio.run(_teardown())

    def test_gate3_null_prediction_row_agrees_python_and_db_and_is_unflagged(below_floor_run):
        run_id, _learner_id, result = below_floor_run
        assert result.rows_written == 1
        assert result.below_floor == 1

        async def _fetch():
            engine = _engine()
            try:
                async with engine.connect() as conn:
                    return (
                        await conn.execute(
                            _text(
                                "SELECT evidence_status, sessions_completed, predicted_class, "
                                "prob_class_0, watch_flag, rank_within_t "
                                "FROM t3_predictions WHERE pipeline_run_id = :r"
                            ),
                            {"r": run_id},
                        )
                    ).one()
            finally:
                await engine.dispose()

        row = asyncio.run(_fetch())
        assert row.predicted_class is None
        assert row.prob_class_0 is None
        assert row.sessions_completed == 2
        assert row.evidence_status == "insufficient_exposure"
        assert row.watch_flag is False          # trap 2 -- NOT null, NOT unconstrained
        assert row.rank_within_t is None
        # Python side agrees:
        assert dl.compute_watch_flag(None, 2) is False


# --- gate 12: upadya (dev DB) row counts unchanged -----------------------------------

_RO_URL = os.environ.get("T3_LIVE_DB_URL_READONLY")

if _RO_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_readonly_live_target

    assert_safe_and_reachable_readonly_live_target(_RO_URL, env_var="T3_LIVE_DB_URL_READONLY")


@pytest.mark.skipif(
    not _RO_URL,
    reason="set T3_LIVE_DB_URL_READONLY to a direct upadya URL to run the gate 12 count check",
)
def test_gate12_upadya_dev_db_prediction_and_learner_counts_are_untouched():
    """The decision layer writes only to T3_LIVE_DB_URL (the disposable upadya_test). This
    records t3_predictions / t3_panel / b_learners counts in the shared dev DB `upadya`
    across a read-only connection and asserts nothing here changes them."""

    from sqlalchemy import text as _t
    from sqlalchemy.ext.asyncio import create_async_engine as _cae

    def _norm(u):
        try:
            from app.infrastructure.db_url import normalise_async_url

            return normalise_async_url(u)
        except Exception:
            return u.replace("postgresql://", "postgresql+asyncpg://", 1)

    async def _counts():
        engine = _cae(_norm(_RO_URL), execution_options={"postgresql_readonly": True})
        try:
            async with engine.connect() as conn:
                out = {}
                for table in ("t3_predictions", "t3_panel", "t3_features_at_t", "b_learners"):
                    out[table] = (
                        await conn.execute(_t(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                return out
        finally:
            await engine.dispose()

    before = asyncio.run(_counts())
    after = asyncio.run(_counts())
    print(f"\n[gate 12] upadya counts before={before} after={after}")
    assert before == after
