"""`GET /classes/{id}/students/overview` -- a whole class's student screens in one request.

The endpoint exists for speed, so the danger is that it quietly serves a learner DIFFERENTLY from
the single-learner endpoints the student screen used to call. The central test therefore asks both
for the same learner and requires identical answers. The rest pin the ownership rule, the Getting
Started case, and that the class is read in one batched history query which later single reads reuse.
"""

from __future__ import annotations

import types
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.application import dashboard_service, recommendation_service
from app.domain.principal import Principal
from app.domain.recommendations import RecommendationListResponse
from tests.test_dashboard_api import CLASSROOM, LEARNER, OTHER_LEARNER, TEACHER, _set_env
from tests.test_sessions_api import _PanelRow

NEWCOMER = uuid.UUID("eeeeeeee-7777-4777-8777-eeeeeeeeeeee")
OVERVIEW = f"/api/v1/t3/classes/{CLASSROOM}/students/overview"


def _prediction(student_id, t, *, watch_flag, rank, trajectory, explanation):
    return types.SimpleNamespace(
        student_id=student_id,
        t=t,
        evidence_status="sufficient_evidence",
        sessions_completed=t,
        watch_flag=watch_flag,
        rank_within_t=rank,
        rank_percentile_within_t=None,
        practice_trajectory=trajectory,
        risk_explanation=explanation,
        shap_top3=[{"display_name": "Recent practice accuracy", "direction": "toward_review", "feature": "x"}],
        risk_level=None,
        risk_level_status="CALIBRATION_PENDING",
        model_version="1.0.0",
        inference_timestamp=None,
        pipeline_run_id=uuid.UUID(int=7),
    )


@pytest.fixture
def client(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    names = {LEARNER: "Amara", OTHER_LEARNER: "Bo", NEWCOMER: "Newcomer"}
    histories = {
        LEARNER: [_PanelRow(1), _PanelRow(2), _PanelRow(3)],
        OTHER_LEARNER: [
            _PanelRow(1, student_id=OTHER_LEARNER, b_opportunities_w4={"counting": 0}),
        ],
        NEWCOMER: [],
    }
    calls = {"batched": [], "single": []}

    async def _active_run(_session, *, active_model_version):
        return types.SimpleNamespace(pipeline_run_id=uuid.UUID(int=7))

    async def _owns(_session, teacher_profile_id, classroom_id):
        return teacher_profile_id == TEACHER and classroom_id == CLASSROOM

    async def _visible(_session, teacher_profile_id, learner_id):
        return teacher_profile_id == TEACHER and learner_id in names

    async def _roster(_session, classroom_id):
        return [types.SimpleNamespace(learner_id=sid, name=name) for sid, name in names.items()]

    async def _classrooms(_session, teacher_profile_id):
        row = types.SimpleNamespace(classroom_id=CLASSROOM, name="Grade 3 Maths", grade="GRADE_3")
        return [row] if teacher_profile_id == TEACHER else []

    async def _classroom_for_learner(_session, teacher_profile_id, learner_id):
        return types.SimpleNamespace(classroom_id=CLASSROOM, name="Grade 3 Maths")

    async def _real_learners(_session, *, learner_ids=None):
        return [types.SimpleNamespace(learner_id=i, name=names[i]) for i in (learner_ids or [])]

    async def _predictions(_session, _run, student_id=None, student_ids=None, with_explanation=True):
        rows = [
            _prediction(LEARNER, 3, watch_flag=True, rank=2, trajectory="stable", explanation="Older."),
            _prediction(LEARNER, 9, watch_flag=True, rank=1, trajectory="needs_attention", explanation="Latest."),
            _prediction(OTHER_LEARNER, 9, watch_flag=False, rank=4, trajectory="improving", explanation=None),
        ]
        return [r for r in rows if student_id is None or r.student_id == student_id]

    async def _history_one(_session, _run, student_id):
        calls["single"].append(student_id)
        return histories.get(student_id, [])

    async def _history_many(_session, _run, student_ids):
        calls["batched"].append(list(student_ids))
        return [row for sid in student_ids for row in histories.get(sid, [])]

    async def _active_for_students(_session, _run, student_ids, latest_sessions):
        return {
            sid: RecommendationListResponse(student_id=sid, recommendations=[])
            for sid in student_ids
        }

    da = dashboard_service.data_access
    monkeypatch.setattr(da, "active_pipeline_run", _active_run)
    monkeypatch.setattr(da, "teacher_owns_classroom", _owns)
    monkeypatch.setattr(da, "learner_visible_to_teacher", _visible)
    monkeypatch.setattr(da, "classroom_roster", _roster)
    monkeypatch.setattr(da, "classrooms_for_teacher", _classrooms)
    monkeypatch.setattr(da, "classroom_for_learner", _classroom_for_learner)
    monkeypatch.setattr(da, "real_learners", _real_learners)
    monkeypatch.setattr(da, "predictions_for_run", _predictions)
    monkeypatch.setattr(da, "session_history_for_student", _history_one)
    monkeypatch.setattr(da, "session_history_for_students", _history_many)
    monkeypatch.setattr(recommendation_service, "active_for_students", _active_for_students)

    app = create_app()

    async def _principal():
        return Principal(teacher_profile_id=TEACHER, resolution="demo")

    async def _session():
        yield None

    app.dependency_overrides[dependencies.current_principal] = _principal
    app.dependency_overrides[dependencies.db_session] = _session
    with TestClient(app) as test_client:
        test_client.calls = calls
        yield test_client


def _by_student(body):
    return {s["detail"]["student_id"]: s for s in body["students"]}


def test_every_learner_matches_the_single_learner_endpoints_exactly(client) -> None:
    """The reason this endpoint is safe to use: it is the same data, built the same way."""

    overview = client.get(OVERVIEW)
    assert overview.status_code == 200, overview.text
    students = _by_student(overview.json())
    assert set(students) == {str(LEARNER), str(OTHER_LEARNER), str(NEWCOMER)}

    for sid in (LEARNER, OTHER_LEARNER, NEWCOMER):
        detail = client.get(f"/api/v1/t3/students/{sid}").json()
        skills = client.get(f"/api/v1/t3/students/{sid}/skills").json()
        assert students[str(sid)]["detail"] == detail, sid
        assert students[str(sid)]["skills"] == skills, sid


def test_the_latest_snapshot_is_served_not_an_older_one(client) -> None:
    amara = _by_student(client.get(OVERVIEW).json())[str(LEARNER)]["detail"]
    assert amara["t"] == 9
    assert amara["explanation"] == "Latest."
    assert amara["signals"] == [{"display_name": "Recent practice accuracy", "direction": "toward_review"}]


def test_a_learner_not_in_the_run_is_getting_started_not_no_concern(client) -> None:
    newcomer = _by_student(client.get(OVERVIEW).json())[str(NEWCOMER)]
    assert newcomer["detail"]["evidence_status"] == "insufficient_exposure"
    assert newcomer["detail"]["watch_flag"] is False
    assert newcomer["skills"]["skills"] == []


def test_a_class_the_teacher_does_not_own_is_forbidden(client) -> None:
    other = uuid.UUID("99999999-9999-4999-8999-999999999999")
    response = client.get(f"/api/v1/t3/classes/{other}/students/overview")
    assert response.status_code == 403
    assert "students" not in response.text


def test_the_class_is_read_in_one_history_query_that_single_reads_then_reuse(client) -> None:
    client.get(OVERVIEW)
    assert len(client.calls["batched"]) == 1
    assert set(client.calls["batched"][0]) == {LEARNER, OTHER_LEARNER, NEWCOMER}

    # Opening one learner afterwards touches no history reader at all.
    client.get(f"/api/v1/t3/students/{LEARNER}/skills")
    assert client.calls["single"] == []


def test_the_response_carries_the_disclosure_and_no_raw_feature_key(client) -> None:
    body = client.get(OVERVIEW).json()
    assert body["disclosure"]
    assert '"feature"' not in client.get(OVERVIEW).text
