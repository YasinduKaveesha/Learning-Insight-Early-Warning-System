"""The Component 3 loader -- work order B4.

The loader touches the database, so this module needs SQLAlchemy and is skipped whole in the
pinned `c3-ews` env (no SQLAlchemy / asyncpg). The pure orchestration helpers
(`assert_no_audit_labels`, `partition_by_resolution`, `LearnerResolutionError`) are tested
here without a database; the end-to-end gates (3, 4, 8) require one and skip cleanly unless
`T3_LIVE_DB_URL` points at a direct (5432) Postgres.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")

from app.application import t3_loader  # noqa: E402


def _rec(student_id: str, n: int = 1) -> dict:
    return {"student_id": student_id, "intervention_session_number": n,
            "b_present": True, "c_present": True}


# --- pure helpers --------------------------------------------------------------------

def test_provenance_constants_are_the_work_order_values():
    assert t3_loader.SOURCE_CLASS == "SYNTHETIC"
    assert t3_loader.SOURCE_SYSTEM == "t3_loader"
    assert t3_loader.PARAMETER_SOURCE_STATUS == "TEST_FIXTURE_ONLY"


def test_assert_no_audit_labels_passes_on_clean_records():
    t3_loader.assert_no_audit_labels([_rec("STU-0001"), _rec("STU-0002")])


@pytest.mark.parametrize("bad", ["population", "dd_subtype"])
def test_assert_no_audit_labels_aborts_on_a_leaked_column(bad):
    with pytest.raises(t3_loader.AuditLabelLeakError):
        t3_loader.assert_no_audit_labels([{**_rec("STU-0001"), bad: "x"}])


def test_partition_by_resolution_splits_and_reports_unresolved():
    u = uuid.uuid4()
    records = [_rec("STU-0001"), _rec("STU-0001", 2), _rec("STU-0002"), _rec("STU-0003")]
    resolvable, unresolved = t3_loader.partition_by_resolution(records, {"STU-0001": u})
    assert len(resolvable) == 2
    assert unresolved == ["STU-0002", "STU-0003"]  # sorted, de-duplicated


def test_learner_resolution_error_counts_and_previews():
    err = t3_loader.LearnerResolutionError([f"STU-{i:04d}" for i in range(15)])
    assert "15 student_id" in str(err)
    assert "does not create learners" in str(err)
    assert err.unresolved[0] == "STU-0000"


def test_sql_resolver_rejects_a_non_identifier_match_column():
    with pytest.raises(ValueError):
        t3_loader.SqlLearnerResolver(session=None, match_column="name; drop table b_learners")


def test_dict_resolver_only_returns_matches():
    u = uuid.uuid4()
    resolver = t3_loader.DictLearnerResolver({"STU-0001": u})
    got = asyncio.run(resolver.resolve({"STU-0001", "STU-0002"}))
    assert got == {"STU-0001": u}


# --- DemoMapLearnerResolver (work order B4.1) ----------------------------------------

class _FakeMapRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeMapSession:
    """A minimal stand-in for AsyncSession sufficient for DemoMapLearnerResolver.resolve."""

    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_params = None

    async def execute(self, query, params=None):
        self.last_query = str(query)
        self.last_params = params
        return _FakeMapRows(self._rows)


def test_demo_map_resolver_queries_the_bridge_table_and_returns_matches():
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    session = _FakeMapSession([("STU-0001", u1), ("STU-0002", u2)])
    resolver = t3_loader.DemoMapLearnerResolver(session)
    got = asyncio.run(resolver.resolve({"STU-0001", "STU-0002", "STU-9999"}))
    assert got == {"STU-0001": u1, "STU-0002": u2}
    assert "t3_demo_learner_map" in session.last_query
    assert "research_student_id" in session.last_query


def test_demo_map_resolver_short_circuits_on_empty_input():
    session = _FakeMapSession([])
    resolver = t3_loader.DemoMapLearnerResolver(session)
    got = asyncio.run(resolver.resolve(set()))
    assert got == {}
    assert session.last_query is None  # never touched the database


# --- the hard row-count assertion (work order B4.1, core deliverable gate) -----------
#
# Uses a fake AsyncSession so this runs without a database (contributing to the always-run
# suite, not just the live gates) while still exercising `run_load`'s real code path: the
# `session.begin()` transaction, the two inserts, and the read-back count comparison.

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
        return False  # never swallow the exception


class _FakeLoaderSession:
    """Stands in for AsyncSession across a full `run_load` call.

    `scalar_override` controls what the read-back row-count query returns; set it to
    something other than the number of resolvable records to simulate the exact bug B0.1's
    mutation testing found nothing was checking (a row silently dropped from the insert).
    """

    def __init__(self, scalar_override: int | None):
        self._scalar_override = scalar_override
        self.committed = False
        self.rolled_back = False
        self.executed = []

    def begin(self):
        return _FakeTxn(self)

    async def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        return None

    async def scalar(self, *args, **kwargs):
        return self._scalar_override


def _patch_bc_adapter(monkeypatch, records):
    monkeypatch.setattr(t3_loader.bc_adapter, "read_manifest", lambda path: {"dataset": "x"})
    monkeypatch.setattr(t3_loader.bc_adapter, "load_panel_records", lambda path: records)


def test_run_load_raises_on_row_count_mismatch_and_rolls_back(monkeypatch):
    u = uuid.uuid4()
    records = [_rec("STU-0001", 1), _rec("STU-0001", 2)]
    _patch_bc_adapter(monkeypatch, records)
    session = _FakeLoaderSession(scalar_override=1)  # wrong: 2 records resolve, DB says 1

    with pytest.raises(t3_loader.PanelRowCountMismatchError) as excinfo:
        asyncio.run(
            t3_loader.run_load(
                session,
                source_path="unused",
                manifest_path="unused",
                resolver=t3_loader.DictLearnerResolver({"STU-0001": u}),
                model_version="1.0.0",
            )
        )
    assert excinfo.value.expected == 2
    assert excinfo.value.actual == 1
    assert session.rolled_back is True
    assert session.committed is False


def test_run_load_succeeds_when_the_readback_count_matches(monkeypatch):
    u = uuid.uuid4()
    records = [_rec("STU-0001", 1), _rec("STU-0001", 2)]
    _patch_bc_adapter(monkeypatch, records)
    session = _FakeLoaderSession(scalar_override=2)  # correct

    result = asyncio.run(
        t3_loader.run_load(
            session,
            source_path="unused",
            manifest_path="unused",
            resolver=t3_loader.DictLearnerResolver({"STU-0001": u}),
            model_version="1.0.0",
        )
    )
    assert result.panel_rows_written == 2
    assert session.committed is True
    assert session.rolled_back is False


# --- end-to-end (gates 3, 4, 8): needs a database ------------------------------------

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)

pytestmark_live = pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the loader end-to-end",
)


@pytestmark_live
def test_loader_end_to_end_is_a_db_gate_documented_in_the_report():
    # Gates 3 (7,500 panel rows), 4 (no b_present/c_present-false row) and 8 (re-run makes a
    # second pipeline_run_id, first generation intact) are demonstrated against the local
    # Docker DB in the work-order report, not here.
    pytest.skip("covered by the manual gate demonstrations in the B4 report")


# --- the 300-row demo fixture and the row-count gate against a real database (B4.1) --------
#
# Seeds 300 `b_learners` rows and their 300 `t3_demo_learner_map` rows, runs a full load
# through `DemoMapLearnerResolver`, and reads the resulting `t3_panel` row count back with a
# fresh direct query -- not the in-memory `LoadResult` -- so this is a real assertion on what
# the database holds, not on what the loader believes it wrote. Cleans up by
# `pipeline_run_id` plus the fixture learners/map rows it created.

if _LIVE_URL:
    import json
    import uuid as _uuid

    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

    def _normalise_url(url: str) -> str:
        try:
            from app.infrastructure.db_url import normalise_async_url

            return normalise_async_url(url)
        except Exception:
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)

    _N_STUDENTS = 300
    _N_SESSIONS = 25  # -> 7,500 panel rows, matching the real dataset's scale.

    def _seed_sql(learner_id, name):
        return _text(
            "INSERT INTO b_learners (learner_id, status, request_id, "
            "operation_or_event_type, reason_code, resource_type, resource_id, "
            "source_class, source_system, environment, schema_revision, system_actor, name) "
            "VALUES (:lid, 'active', :rid, 'create', 'b4_1_fixture', 'learner', :lid, "
            "'TEST', 't3_demo_fixture', 'test', '1', 't3_demo_fixture', :name)"
        ).bindparams(lid=learner_id, rid=f"b4_1-{learner_id}", name=name)

    async def _seed_300_learners_and_map() -> list[tuple]:
        # A fresh engine per `asyncio.run` call -- asyncpg connections are bound to the event
        # loop that created them, so an engine reused across separate `asyncio.run` calls
        # (each of which opens a NEW loop) fails at teardown with "Event loop is closed".
        engine = _create_async_engine(_normalise_url(_LIVE_URL))
        try:
            pairs = []
            async with engine.begin() as conn:
                for i in range(1, _N_STUDENTS + 1):
                    lid = _uuid.uuid4()
                    sid = f"STU-{i:04d}"
                    pairs.append((lid, sid))
                    await conn.execute(_seed_sql(lid, f"b4_1 fixture {sid}"))
                    await conn.execute(
                        _text(
                            "INSERT INTO t3_demo_learner_map "
                            "(learner_id, research_student_id, source_class, source_system, "
                            "parameter_source_status, pipeline_run_id) "
                            "VALUES (:lid, :sid, 'TEST', 't3_demo_fixture', "
                            "'TEST_FIXTURE_ONLY', :run)"
                        ),
                        {"lid": lid, "sid": sid, "run": _uuid.uuid4()},
                    )
            return pairs
        finally:
            await engine.dispose()

    async def _cleanup_fixture(learner_ids, pipeline_run_ids) -> None:
        engine = _create_async_engine(_normalise_url(_LIVE_URL))
        try:
            async with engine.begin() as conn:
                for run_id in pipeline_run_ids:
                    await conn.execute(
                        _text("DELETE FROM t3_panel WHERE pipeline_run_id = :run"),
                        {"run": run_id},
                    )
                    await conn.execute(
                        _text("DELETE FROM t3_pipeline_runs WHERE pipeline_run_id = :run"),
                        {"run": run_id},
                    )
                await conn.execute(
                    _text("DELETE FROM t3_demo_learner_map WHERE learner_id = ANY(:ids)"),
                    {"ids": learner_ids},
                )
                await conn.execute(
                    _text("DELETE FROM b_learners WHERE learner_id = ANY(:ids)"),
                    {"ids": learner_ids},
                )
        finally:
            await engine.dispose()

    def _write_synthetic_source(tmp_path, student_ids):
        source_path = tmp_path / "so2_joined_fixture.jsonl"
        manifest_path = tmp_path / "so2_manifest_fixture.json"
        manifest_path.write_text(
            json.dumps({"dataset": "b4_1_demo_fixture", "n_students": len(student_ids)}),
            encoding="utf-8",
        )
        with source_path.open("w", encoding="utf-8") as handle:
            for sid in student_ids:
                for session_no in range(1, _N_SESSIONS + 1):
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

    @pytest.fixture(scope="module")
    def demo_learner_map_300():
        pairs = asyncio.run(_seed_300_learners_and_map())
        pipeline_run_ids: list = []
        try:
            yield pairs, pipeline_run_ids
        finally:
            asyncio.run(_cleanup_fixture([lid for lid, _ in pairs], pipeline_run_ids))

    def test_loader_end_to_end_row_count_matches_the_database(
        demo_learner_map_300, tmp_path
    ):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        pairs, pipeline_run_ids = demo_learner_map_300
        student_ids = [sid for _, sid in pairs]
        source_path, manifest_path = _write_synthetic_source(tmp_path, student_ids)

        async def go():
            # One engine, one event loop, for both the load and the direct read-back --
            # avoids reusing an asyncpg connection pool across separate `asyncio.run` loops.
            engine = _create_async_engine(_normalise_url(_LIVE_URL))
            try:
                maker = async_sessionmaker(engine, expire_on_commit=False)
                async with maker() as session:
                    result = await t3_loader.run_load(
                        session,
                        source_path=source_path,
                        manifest_path=manifest_path,
                        resolver=t3_loader.DemoMapLearnerResolver(session),
                        model_version="1.0.0",
                        notes="B4.1 300-row fixture end-to-end gate",
                    )
                async with engine.connect() as conn:
                    db_count = (
                        await conn.execute(
                            _text(
                                "SELECT count(*) FROM t3_panel WHERE pipeline_run_id = :run"
                            ),
                            {"run": result.pipeline_run_id},
                        )
                    ).scalar_one()
                return result, db_count
            finally:
                await engine.dispose()

        result, db_count = asyncio.run(go())
        pipeline_run_ids.append(result.pipeline_run_id)

        expected = _N_STUDENTS * _N_SESSIONS
        assert result.panel_rows_written == expected
        assert db_count == expected  # queried directly from the database, not a variable
        assert not result.unresolved_student_ids
