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
        # `division` is in mastery but NEVER in opportunities: the D46 "not practised yet"
        # case -- its 0.15 is the model's starting prior, not a measurement.
        self.b_mastery = {"counting": 0.83, "division": 0.15}
        for key, value in kwargs.items():
            setattr(self, key, value)


class _PredRow:
    def __init__(self, student_id, t, watch_flag, trajectory):
        self.student_id = student_id
        self.t = t
        self.watch_flag = watch_flag
        self.practice_trajectory = trajectory
        # B6.5: the participation histogram buckets learners by this. It equals `t` on every
        # real row (the decision layer writes them together and a live test pins it), so the
        # double mirrors that rather than inventing an independent value.
        self.sessions_completed = t


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

    class _ClassroomRow:
        def __init__(self, classroom_id, name, grade="GRADE_3"):
            self.classroom_id = classroom_id
            self.name = name
            self.grade = grade

    async def _classrooms(_session, teacher_profile_id):
        # B6.5: `class_report` and `student_detail` now need the class name (and, for the
        # student screen, the id to link back with).
        return [_ClassroomRow(CLASSROOM, "Grade 3 Maths")] if teacher_profile_id == TEACHER else []

    async def _classroom_for_learner(_session, teacher_profile_id, learner_id):
        if teacher_profile_id != TEACHER:
            return None
        return _ClassroomRow(CLASSROOM, "Grade 3 Maths")

    da = dashboard_service.data_access
    async def _handled(_session, _run):
        # No suggestion has been handled unless a test says otherwise (decision B).
        return {}

    monkeypatch.setattr(da, "handled_suggestions_for_run", _handled)
    monkeypatch.setattr(da, "classrooms_for_teacher", _classrooms)
    monkeypatch.setattr(da, "classroom_for_learner", _classroom_for_learner)
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


def test_the_sessions_route_never_serves_a_mastery_value(client):
    """D42 opened ONE door -- `mastery_level` on the skills route. Session history stays
    closed: the reader now selects `b_mastery`, and this proves it does not leak through."""

    body = client.get(SESSIONS).text
    for banned in ("b_mastery", "mastery", "p_l", "skill_estimate", "0.83"):
        assert banned not in body


def test_a_never_practised_skill_serves_no_level_and_says_so(client):
    """D46. `division` has a stored mastery of 0.15 and no opportunity in any session, so it is
    the model's starting prior, not a measurement. Serving the level would draw the shortest bar
    on the screen for a skill nobody has practised."""

    skills = {s["skill"]: s for s in client.get(SKILLS).json()["skills"]}
    assert skills["division"]["never_practised"] is True
    assert skills["division"]["mastery_level"] is None
    # A practised skill is unaffected, and is never labelled untested.
    assert skills["counting"]["never_practised"] is False
    assert skills["counting"]["mastery_level"] == 0.83


def test_practice_in_any_earlier_session_counts_not_just_the_latest_window(client, monkeypatch):
    """The rule is LIFETIME practice. A skill practised early and not since is still practised --
    the failure mode of the `opportunities_w4 = 0` shortcut, which the ML team measured at 45 of
    116 demo division bars."""

    rows = [_PanelRow(1), _PanelRow(2)]
    rows[0].b_opportunities_w4 = {"division": 5}
    rows[1].b_opportunities_w4 = {"counting": 8}
    for row in rows:
        row.b_mastery = {"counting": 0.6, "division": 0.42}

    async def _history(_session, _run, _student):
        return rows

    monkeypatch.setattr(dashboard_service.data_access, "session_history_for_student", _history)
    skills = {s["skill"]: s for s in client.get(SKILLS).json()["skills"]}
    assert skills["division"]["never_practised"] is False
    assert skills["division"]["mastery_level"] == 0.42


def test_ever_practised_ignores_zero_and_non_numeric_counts():
    class _Row:
        def __init__(self, opportunities):
            self.b_opportunities_w4 = opportunities

    assert dashboard_service._ever_practised(
        [_Row({"a": 0, "b": None, "c": "3", "d": True, "e": 1}), _Row(None)]
    ) == {"e"}


def test_the_skills_route_serves_mastery_only_as_mastery_level(client):
    """D42: the latest value, rounded, under its honest name -- never the raw column name,
    and None for a skill with no stored mastery."""

    body = client.get(SKILLS)
    assert "b_mastery" not in body.text
    skills = {s["skill"]: s for s in body.json()["skills"]}
    assert skills["counting"]["mastery_level"] == 0.83
    assert skills["place_value"]["mastery_level"] is None
    assert all(s["relative_level"] is None for s in skills.values())


@pytest.mark.parametrize(
    "raw, served",
    [(0.834999, 0.83), (0.0, 0.0), (1.0, 1.0), (1.2, None), (-0.1, None), ("0.5", None), (True, None), (None, None)],
)
def test_mastery_level_is_rounded_and_never_clamped(raw, served):
    assert dashboard_service._mastery_level(raw) == served


def test_a_learner_with_no_sessions_gets_an_empty_skill_list_not_an_error(client, monkeypatch):
    """A child who has not practised yet has no skills to report -- an empty list, not a
    failure. This used to 404, and because the student screen fetches the detail and the skills
    together, one 404 took the whole screen down to "couldn't load this student"."""

    async def _no_history(_session, _run, _student):
        return []

    monkeypatch.setattr(dashboard_service.data_access, "session_history_for_student", _no_history)
    response = client.get(SKILLS)
    assert response.status_code == 200
    body = response.json()
    assert body["skills"] == []
    assert body["disclosure"] == DISCLOSURE
    # And the sessions route answers the same shape of nothing.
    assert client.get(SESSIONS).json()["sessions"] == []


def test_skill_direction_is_withheld_for_every_skill(client):
    """D38. The old chip applied the accuracy-rate epsilon to a mastery slope and read 76% of
    practised skills as stable. Until it is re-specified and D16-checked, every skill -- however
    many observations it has -- serves `unknown`. `counting` has 8 observations and a clearly
    positive slope in this fixture, which is exactly the case that must NOT report a direction."""

    skills = {s["skill"]: s for s in client.get(SKILLS).json()["skills"]}
    assert skills, "the fixture must still return skills"
    assert {s["direction"] for s in skills.values()} == {"unknown"}
    # The practice count is a restatement of b_opportunities_w4 and is unaffected.
    assert skills["counting"]["practice_count"] == 8
    assert skills["place_value"]["practice_count"] == 2


def test_the_skill_chip_no_longer_applies_the_accuracy_epsilon():
    """D38: `EPSILON_PRACTICE` applies to `b_accuracy_rate` only. The function that applied it to
    a mastery slope is gone, so it cannot be quietly re-wired."""

    assert not hasattr(dashboard_service, "_skill_direction")


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


# ------------------------------------------------------------------------------------------
# B6.5 — the Reports fields the current UI renders.
# ------------------------------------------------------------------------------------------


def test_class_report_serves_the_class_name(client):
    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/reports").json()
    assert body["class_name"] == "Grade 3 Maths"


def test_participation_counts_learners_not_prediction_rows(client):
    """The histogram is per LEARNER, from each one's latest snapshot.

    Counting every prediction row instead would count a learner once per session and turn a
    class of twenty into a chart of several hundred -- a bar chart that looks like a cohort and
    is actually a session log.
    """

    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/reports").json()
    total = sum(b["student_count"] for b in body["participation"])
    assert total == body["learner_count"] or total <= body["learner_count"]
    assert total <= len(body["early_warning_curve"]) * body["learner_count"]


def test_participation_keeps_empty_bands(client):
    """A band that vanishes at zero makes the chart change shape for an invisible reason."""

    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/reports").json()
    labels = [b["bucket_label"] for b in body["participation"]]
    assert labels == [
        "Fewer than 3 sessions",
        "3-5 sessions",
        "6-10 sessions",
        "11-15 sessions",
        "16+ sessions",
    ]

