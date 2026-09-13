"""Session history, skill progress and class reports (work order B6.2).

The three tests worth reading are the ones guarding rules a passing suite would not
otherwise notice, because each failure mode produces a plausible-looking number rather than
an exception:

* `test_a_technical_fault_is_never_rendered_as_disengagement` -- a broken telemetry session
  and a disengaged child both produce a low engagement score.
* `test_b_and_c_are_separate_field_groups` -- a merged accuracy is still a float.
* `test_a_skill_with_too_few_observations_has_no_slope` -- `0.0` and "cannot tell yet" are
  both renderable as a flat bar.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.application import dashboard_service
from app.domain.dashboard import DISCLOSURE
from app.domain.principal import Principal
from tests.test_dashboard_api import (
    CLASSROOM,
    LEARNER,
    OTHER_LEARNER,
    TEACHER,
    _Learner,
    _set_env,
    assert_no_forbidden_fields,
)


class _PanelRow:
    """A `session_history_for_student` row. Defaults are a clean, complete session; each
    test overrides only the columns it is about."""

    def __init__(self, n, **kwargs):
        self.student_id = LEARNER
        self.intervention_session_number = n
        self.intervention_session_date = dt.date(2026, 3, n)
        self.b_present = True
        self.c_present = True
        self.b_accuracy_rate = 0.5
        self.b_total_questions = 10
        self.b_correct_responses = 5
        self.b_hint_requests = 2
        self.b_median_item_response_time_sec = 12.0
        self.b_mastery_slope_w4 = {"counting": 0.2, "place_value": 0.0, "fractions": -0.3}
        self.b_opportunities_w4 = {"counting": 8, "place_value": 2, "fractions": 6}
        # Component C values are deliberately DIFFERENT from the B ones above, so a test
        # that finds a B number under a C key (or vice versa) fails loudly.
        self.c_accuracy_rate = 0.9
        self.c_task_completion_rate = 0.8
        self.c_median_game_task_latency_sec = 3.0
        self.c_engagement_score = 0.7
        self.c_engagement_components = {"completion": 0.4, "activity": 0.3}
        self.c_frustration_index = 0.6
        self.c_frustration_components = {"error_run": 0.5, "inactivity_burden": 0.1}
        self.c_learner_state = "engaged"
        self.c_current_difficulty_level = 3
        self.c_difficulty_trend = "stable"
        self.c_telemetry_quality_status = "ok"
        self.c_session_technical_issue_flag = False
        self.c_inactive_time_sec = 0.0
        # Mastery must never be served in any form; carried here so a test can prove it.
        self.b_mastery = {"counting": 0.83}
        for key, value in kwargs.items():
            setattr(self, key, value)


class _PredRow:
    def __init__(self, student_id, t, watch_flag, trajectory):
        self.student_id = student_id
        self.t = t
        self.watch_flag = watch_flag
        self.practice_trajectory = trajectory


@pytest.fixture
def client(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    class _Run:
        pipeline_run_id = uuid.UUID(int=7)

    state = {"panel": [_PanelRow(1), _PanelRow(2), _PanelRow(3)]}

    async def _active_run(_session, *, active_model_version):
        return _Run()

    async def _history(_session, _run, student_id):
        return state["panel"]

    async def _roster(_session, classroom_id):
        return [_Learner(LEARNER, "Amara"), _Learner(OTHER_LEARNER, "Bo")]

    async def _predictions(_session, _run, student_id=None):
        return [
            _PredRow(LEARNER, 3, True, "needs_attention"),
            _PredRow(OTHER_LEARNER, 3, False, "improving"),
            _PredRow(LEARNER, 9, True, "needs_attention"),
            _PredRow(OTHER_LEARNER, 9, True, "needs_attention"),
        ]

    async def _owns(_session, teacher_profile_id, classroom_id):
        return teacher_profile_id == TEACHER and classroom_id == CLASSROOM

    async def _visible(_session, teacher_profile_id, learner_id):
        return teacher_profile_id == TEACHER and learner_id in {LEARNER, OTHER_LEARNER}

    async def _real_learners(_session, *, learner_ids=None):
        return [_Learner(LEARNER, "Amara")]

    da = dashboard_service.data_access
    monkeypatch.setattr(da, "active_pipeline_run", _active_run)
    monkeypatch.setattr(da, "session_history_for_student", _history)
    monkeypatch.setattr(da, "classroom_roster", _roster)
    monkeypatch.setattr(da, "predictions_for_run", _predictions)
    monkeypatch.setattr(da, "teacher_owns_classroom", _owns)
    monkeypatch.setattr(da, "learner_visible_to_teacher", _visible)
    monkeypatch.setattr(da, "real_learners", _real_learners)

    app = create_app()

    async def _principal():
        return Principal(teacher_profile_id=TEACHER, resolution="demo")

    async def _session():
        yield None

    app.dependency_overrides[dependencies.current_principal] = _principal
    app.dependency_overrides[dependencies.db_session] = _session
    with TestClient(app) as test_client:
        test_client.state = state
        yield test_client


SESSIONS = f"/api/v1/t3/students/{LEARNER}/sessions"
SKILLS = f"/api/v1/t3/students/{LEARNER}/skills"
REPORTS = f"/api/v1/t3/classes/{CLASSROOM}/reports"
ALL_ROUTES = (SESSIONS, SKILLS, REPORTS)


# --- rule 1: B and C are never merged ---------------------------------------------------


def test_b_and_c_are_separate_field_groups(client):
    """The test contract lists a merged B/C accuracy or timing value as a hard failure.
    A merged number is still a float, so this asserts on the SHAPE: two nested objects, each
    keeping its own value."""

    record = client.get(SESSIONS).json()["sessions"][0]
    assert record["practice"]["accuracy_rate"] == 0.5
    assert record["games"]["accuracy_rate"] == 0.9
    assert record["practice"]["median_item_response_time_sec"] == 12.0
    assert record["games"]["median_task_latency_sec"] == 3.0
    # No blended field may exist at the top level of a session record.
    for merged in ("accuracy_rate", "accuracy", "response_time_sec", "median_latency"):
        assert merged not in record


def test_a_session_missing_one_component_returns_null_for_it_not_a_zero(client):
    """`b_present = false` means "no practice happened", not "practice scored zero"."""

    client.state["panel"] = [_PanelRow(1, b_present=False)]
    record = client.get(SESSIONS).json()["sessions"][0]
    assert record["practice"] is None
    assert record["practice_present"] is False
    assert record["games"] is not None


# --- rule 2: a technical fault is never disengagement ------------------------------------


def test_a_technical_fault_is_never_rendered_as_disengagement(client):
    """The failure this guards is silent: a broken telemetry session and a disengaged child
    both produce a low engagement score, and only the guard columns tell them apart."""

    client.state["panel"] = [
        _PanelRow(1, c_session_technical_issue_flag=True, c_engagement_score=0.05)
    ]
    games = client.get(SESSIONS).json()["sessions"][0]["games"]
    assert games["data_quality"] == "technical_issue"
    assert games["engagement_score"] is None
    assert games["frustration_index"] is None
    assert games["engagement_components"] is None


def test_degraded_telemetry_also_suppresses_the_engagement_figures(client):
    client.state["panel"] = [
        _PanelRow(1, c_telemetry_quality_status="partial", c_engagement_score=0.05)
    ]
    games = client.get(SESSIONS).json()["sessions"][0]["games"]
    assert games["data_quality"] == "incomplete_telemetry"
    assert games["engagement_score"] is None


def test_a_clean_session_still_reports_its_engagement(client):
    """The suppression must not be so eager that it hides good data."""

    games = client.get(SESSIONS).json()["sessions"][0]["games"]
    assert games["data_quality"] == "ok"
    assert games["engagement_score"] == 0.7
    assert games["frustration_components"]["error_run"] == 0.5


def test_the_technical_issue_flag_wins_over_an_ok_status(client):
    """Migration 0005 added the flag precisely because the status string alone could not
    separate a fault from disengagement -- so the flag is checked first and independently."""

    client.state["panel"] = [
        _PanelRow(1, c_session_technical_issue_flag=True, c_telemetry_quality_status="ok")
    ]
    assert (
        client.get(SESSIONS).json()["sessions"][0]["games"]["data_quality"]
        == "technical_issue"
    )


# --- rule 3: no mastery value, and no fabricated slope ----------------------------------


def test_no_mastery_value_is_ever_served(client):
    """`b_skill_certification_results` values are TEST_FIXTURE_ONLY and documented as never
    exposed through a public DTO; live BKT uses identical parameters for all seven skills."""

    for route in (SESSIONS, SKILLS):
        body = client.get(route).text
        for banned in ("b_mastery", "p_l", "skill_estimate", "mastery_value", "0.83"):
            assert banned not in body


def test_a_skill_with_too_few_observations_has_no_slope(client):
    """`place_value` has 2 observations. Fewer than four means `unknown`, never `stable` --
    "we cannot tell yet" and "flat" are different claims about a child."""

    skills = {s["skill"]: s for s in client.get(SKILLS).json()["skills"]}
    assert skills["place_value"]["direction"] == "unknown"
    assert skills["place_value"]["practice_count"] == 2


def test_skills_with_enough_observations_report_a_direction(client):
    skills = {s["skill"]: s for s in client.get(SKILLS).json()["skills"]}
    assert skills["counting"]["direction"] == "improving"
    assert skills["fractions"]["direction"] == "needs_attention"
    assert skills["counting"]["practice_count"] == 8


def test_skill_progress_uses_the_decision_layers_epsilon(client):
    """One epsilon, not two. A skill chip and a trajectory chip must not be able to disagree
    on screen because someone tuned one constant and missed the other."""

    from app.application.decision_layer import EPSILON_PRACTICE

    assert dashboard_service._skill_direction(EPSILON_PRACTICE, 10) == "stable"
    assert dashboard_service._skill_direction(EPSILON_PRACTICE + 0.001, 10) == "improving"
    assert dashboard_service._skill_direction(-EPSILON_PRACTICE - 0.001, 10) == "needs_attention"


# --- reports ----------------------------------------------------------------------------


def test_the_early_warning_curve_is_computed_per_t_never_pooled(client):
    """One point per `t`. A single pooled flag rate is dominated by whichever `t` the class
    is clustered at and tells a teacher nothing."""

    curve = client.get(REPORTS).json()["early_warning_curve"]
    assert [p["t"] for p in curve] == [3, 9]
    at_3 = next(p for p in curve if p["t"] == 3)
    at_9 = next(p for p in curve if p["t"] == 9)
    assert at_3["watch_flagged"] == 1 and at_3["flag_rate"] == 0.5
    assert at_9["watch_flagged"] == 2 and at_9["flag_rate"] == 1.0


def test_the_trajectory_trend_is_also_per_t(client):
    trend = client.get(REPORTS).json()["practice_trajectory_trend"]
    at_3 = next(p for p in trend if p["t"] == 3)
    assert at_3["improving"] == 1 and at_3["needs_attention"] == 1


def test_reports_only_count_learners_on_this_teachers_roster(client, monkeypatch):
    """A prediction for a learner outside the roster must not reach the curve."""

    async def _one_learner_roster(_session, classroom_id):
        return [_Learner(LEARNER, "Amara")]

    monkeypatch.setattr(
        dashboard_service.data_access, "classroom_roster", _one_learner_roster
    )
    curve = client.get(REPORTS).json()["early_warning_curve"]
    assert all(p["learners_with_prediction"] == 1 for p in curve)


# --- the shared guarantees --------------------------------------------------------------


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_no_route_serialises_a_forbidden_field(client, route):
    assert_no_forbidden_fields(client.get(route).json())


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_every_response_carries_the_disclosure(client, route):
    assert client.get(route).json()["disclosure"] == DISCLOSURE


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_engagement_trajectory_is_never_served(client, route):
    assert "engagement_trajectory" not in client.get(route).text


def test_a_learner_or_class_the_teacher_cannot_see_is_403(client):
    stranger = uuid.uuid4()
    assert client.get(f"/api/v1/t3/students/{stranger}/sessions").status_code == 403
    assert client.get(f"/api/v1/t3/students/{stranger}/skills").status_code == 403
    assert client.get(f"/api/v1/t3/classes/{stranger}/reports").status_code == 403


def test_every_b62_route_requires_a_principal(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    with TestClient(create_app()) as bare:
        for route in ALL_ROUTES:
            assert bare.get(route).status_code in (401, 403), route
