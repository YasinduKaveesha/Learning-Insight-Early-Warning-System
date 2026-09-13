"""The teacher-dashboard read endpoints (work order B6.1).

The tests that matter most here are the never-serialised ones. B5.1's gate 9 could only
assert that `engagement_trajectory` was absent from the *source files* under `app/domain` and
`app/api`, because no response models existed yet. They exist now, so this suite asserts it
against actual response BODIES -- which is the assertion the plan has always asked for and
the one that will still be true after someone adds a field in six months.

Auth is stubbed via FastAPI dependency overrides rather than by minting real JWTs: this suite
is about what the endpoints RETURN. `tests/test_auth.py` and `tests/test_principal_
resolution.py` own token verification and identity resolution respectively, and
`test_every_route_requires_a_principal` below proves the dependency is actually wired on
every route rather than assumed.
"""

from __future__ import annotations

import datetime as _dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.application import dashboard_service
from app.domain.dashboard import DISCLOSURE
from app.domain.principal import Principal

# Every field the plan forbids on the wire (backend_plan.md section 8, "Fields that must
# never be serialised"). Asserted against whole response bodies, recursively.
FORBIDDEN_FIELDS = (
    "prob_class_0",
    "prob_class_1",
    "prob_class_2plus",
    "predicted_class",
    "engagement_trajectory",
    "population",
    "dd_subtype",
    "risk_score",
    "cluster",
    "pca",
    "feature",
)

TEACHER = uuid.UUID("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
CLASSROOM = uuid.UUID("bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")
LEARNER = uuid.UUID("cccccccc-3333-4333-8333-cccccccccccc")
OTHER_LEARNER = uuid.UUID("dddddddd-4444-4444-8444-dddddddddddd")


def _walk(node, seen=None):
    """Yield every key in a nested JSON body, so a forbidden field cannot hide inside a
    list of learner cards or a nested signal object."""

    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def assert_no_forbidden_fields(body) -> None:
    keys = {key.lower() for key in _walk(body)}
    for forbidden in FORBIDDEN_FIELDS:
        assert forbidden not in keys, f"{forbidden!r} was serialised to a client"


class _Row:
    """A stand-in for a `predictions_for_run` row. Deliberately carries the server-only
    columns too, so that if a service ever starts copying attributes wholesale instead of
    naming them, the forbidden-field tests above will catch it."""

    def __init__(self, *, student_id, t, sessions_completed, watch_flag, rank, trajectory):
        self.student_id = student_id
        self.t = t
        self.evidence_status = (
            "sufficient_evidence" if sessions_completed >= 3 else "insufficient_exposure"
        )
        self.sessions_completed = sessions_completed
        self.watch_flag = watch_flag
        self.rank_within_t = rank
        self.practice_trajectory = trajectory
        self.risk_explanation = "Flagged for teacher review." if watch_flag else None
        # B6.3d: served on the card so a teacher can see when the learner was last scored.
        self.model_version = "1.0.0"
        self.inference_timestamp = _dt.datetime(2026, 9, 13, 19, 30, tzinfo=_dt.timezone.utc)
        self.shap_top3 = (
            [
                {
                    "feature": "score_avg_recent",
                    "display_name": "recent practice accuracy",
                    "contribution": 1.0,
                    "direction": "toward_review",
                }
            ]
            if watch_flag
            else None
        )
        # Never-served columns, present on the row on purpose.
        self.prob_class_0 = 0.1
        self.prob_class_2plus = 0.6
        self.predicted_class = 2
        self.engagement_trajectory = "needs_attention"


class _Learner:
    def __init__(self, learner_id, name):
        self.learner_id = learner_id
        self.name = name


class _Classroom:
    def __init__(self, classroom_id, name, grade="GRADE_3"):
        self.classroom_id = classroom_id
        self.name = name
        # B6.3d: `classrooms_for_teacher` has always selected grade; the service now serves it.
        self.grade = grade


ARTEFACT_STORE_PATH = __import__("pathlib").Path(__file__).resolve().parents[1] / "artefacts"


def _set_env(monkeypatch) -> None:
    """The same minimal settings environment `tests/test_health.py` uses. `get_settings` is
    lru_cached, so the cache must be cleared after the env is set or a previously-built
    Settings leaks between tests."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PORT", "8100")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/placeholder")
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://example.supabase.co/auth/v1")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setenv(
        "SUPABASE_JWKS_URL", "https://example.supabase.co/auth/v1/.well-known/jwks.json"
    )
    monkeypatch.setenv("SUPABASE_JWKS_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("T3_MODEL_ARTEFACT_PATH", str(ARTEFACT_STORE_PATH))
    monkeypatch.setenv("T3_ACTIVE_MODEL_VERSION", "1.0.0")

    from app.infrastructure.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch):
    # `app.main` calls `get_settings()` at import time (its fail-fast boundary), so the
    # environment must be in place BEFORE the import, not merely before `create_app()`.
    _set_env(monkeypatch)
    from app.main import create_app

    class _Run:
        pipeline_run_id = uuid.UUID(int=7)

    async def _active_run(_session, *, active_model_version):
        return _Run()

    async def _classrooms(_session, teacher_profile_id):
        return [_Classroom(CLASSROOM, "Grade 3 Maths")] if teacher_profile_id == TEACHER else []


    async def _roster(_session, classroom_id):
        return [_Learner(LEARNER, "Amara"), _Learner(OTHER_LEARNER, "Bo")]

    async def _predictions(_session, _run, student_id=None):
        rows = [
            _Row(
                student_id=LEARNER, t=9, sessions_completed=9,
                watch_flag=True, rank=1, trajectory="needs_attention",
            ),
            # An older snapshot for the same learner -- invariant 1 must discard it.
            _Row(
                student_id=LEARNER, t=4, sessions_completed=4,
                watch_flag=False, rank=None, trajectory="improving",
            ),
            _Row(
                student_id=OTHER_LEARNER, t=2, sessions_completed=2,
                watch_flag=False, rank=None, trajectory="unknown",
            ),
        ]
        if student_id is not None:
            rows = [r for r in rows if r.student_id == student_id]
        return rows

    async def _owns(_session, teacher_profile_id, classroom_id):
        return teacher_profile_id == TEACHER and classroom_id == CLASSROOM

    async def _visible(_session, teacher_profile_id, learner_id):
        return teacher_profile_id == TEACHER and learner_id in {LEARNER, OTHER_LEARNER}

    async def _real_learners(_session, *, learner_ids=None):
        everyone = [_Learner(LEARNER, "Amara"), _Learner(OTHER_LEARNER, "Bo")]
        if learner_ids is None:
            return everyone
        return [l for l in everyone if l.learner_id in set(learner_ids)]

    class _PanelRow:
        """A `panel_rows_for_run` row. Two sessions for LEARNER, and a NULL accuracy on the
        second so the sparkline's null-preservation is exercised rather than assumed."""

        def __init__(self, student_id, number, date, accuracy, engagement):
            self.student_id = student_id
            self.intervention_session_number = number
            self.intervention_session_date = date
            self.b_accuracy_rate = accuracy
            self.c_engagement_score = engagement

    async def _panel_rows(_session, _run, student_id=None):
        rows = [
            _PanelRow(LEARNER, 1, _dt.date(2026, 1, 5), 0.4, 0.7),
            _PanelRow(LEARNER, 2, _dt.date(2026, 1, 12), None, 0.8),
        ]
        if student_id is not None:
            rows = [r for r in rows if r.student_id == student_id]
        return rows

    async def _pending_counts(_session, classroom_ids):
        return {CLASSROOM: 3} if CLASSROOM in set(classroom_ids) else {}

    async def _teacher_name(_session, teacher_profile_id):
        return "Teacher01" if teacher_profile_id == TEACHER else None

    class _ClassroomRow:
        def __init__(self, classroom_id, name, grade):
            self.classroom_id = classroom_id
            self.name = name
            self.grade = grade

    async def _classroom_for_learner(_session, teacher_profile_id, learner_id):
        if teacher_profile_id != TEACHER:
            return None
        return _ClassroomRow(CLASSROOM, "Grade 3 Maths", "GRADE_3")

    async def _class_keys(_session, classroom_ids):
        # Only CLASSROOM has ever had a key minted. A classroom without one is ABSENT from
        # the mapping, which is what lets the endpoint serve null rather than "".
        return {CLASSROOM: "7K4P92"} if CLASSROOM in classroom_ids else {}

    da = dashboard_service.data_access
    monkeypatch.setattr(da, "class_keys_for_classrooms", _class_keys)
    monkeypatch.setattr(da, "panel_rows_for_run", _panel_rows)
    monkeypatch.setattr(da, "pending_request_counts", _pending_counts)
    monkeypatch.setattr(da, "teacher_display_name", _teacher_name)
    monkeypatch.setattr(da, "classroom_for_learner", _classroom_for_learner)
    monkeypatch.setattr(da, "active_pipeline_run", _active_run)
    monkeypatch.setattr(da, "classrooms_for_teacher", _classrooms)
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
        yield test_client


ALL_ROUTES = (
    "/api/v1/t3/home",
    "/api/v1/t3/watch",
    f"/api/v1/t3/classes/{CLASSROOM}/cohort",
    f"/api/v1/t3/classes/{CLASSROOM}/watch",
    f"/api/v1/t3/students/{LEARNER}",
)


# --- the never-serialised guarantee -----------------------------------------------------


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_no_route_serialises_a_forbidden_field(client, route):
    response = client.get(route)
    assert response.status_code == 200, response.text
    assert_no_forbidden_fields(response.json())


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_engagement_trajectory_is_never_served_d17(client, route):
    """D17, asserted against a real response body. The source row in this suite CARRIES
    engagement_trajectory, so this fails if a service ever passes a row through wholesale."""

    body = client.get(route).text
    assert "engagement_trajectory" not in body


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_every_response_carries_the_disclosure(client, route):
    assert client.get(route).json()["disclosure"] == DISCLOSURE


def test_the_disclosure_wording_is_exact():
    assert DISCLOSURE == "Literature-informed synthetic data — not clinical evidence."


# --- the service invariants -------------------------------------------------------------


def test_only_the_latest_snapshot_per_learner_is_shown(client):
    """Invariant 1: t=9 wins over t=4 for the same learner, and the stale row is not a
    second card."""

    learners = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()["learners"]
    amara = [l for l in learners if l["student_id"] == str(LEARNER)]
    assert len(amara) == 1
    assert amara[0]["t"] == 9
    assert amara[0]["watch_flag"] is True


def test_watch_list_contains_only_flagged_learners(client):
    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/watch").json()
    assert [l["student_id"] for l in body["learners"]] == [str(LEARNER)]


def test_getting_started_and_watch_counts_are_disjoint(client):
    """Invariant 3: a below-floor learner is counted as getting-started and never as a
    watch. 'No concern' and 'not enough evidence yet' must stay different states."""

    stats = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()["stats"]
    assert stats["learner_count"] == 2
    assert stats["watch_count"] == 1
    assert stats["getting_started_count"] == 1


def test_home_summary_aggregates_across_classes(client):
    body = client.get("/api/v1/t3/home").json()
    assert body["class_count"] == 1
    assert body["watch_count"] == 1
    assert body["active_students"] == 2
    assert body["classes"][0]["name"] == "Grade 3 Maths"


def test_student_detail_exposes_display_names_but_not_feature_keys(client):
    """Filter 3: `shap_top3` stores the raw feature key; only the display name crosses the
    wire."""

    body = client.get(f"/api/v1/t3/students/{LEARNER}").json()
    assert body["signals"] == [
        {"display_name": "recent practice accuracy", "direction": "toward_review"}
    ]
    assert "score_avg_recent" not in client.get(f"/api/v1/t3/students/{LEARNER}").text


def test_watch_list_orders_within_t_never_pooled():
    """Invariant 2, tested on the sort directly so it does not depend on fixture data: a
    t=19 rank-1 must not outrank a t=3 rank-1 by rank alone -- they are not comparable."""

    from app.domain.dashboard import LearnerCard

    def _card(student, t, rank):
        return LearnerCard(
            student_id=student, display_name="x", classroom_id=CLASSROOM, t=t,
            evidence_status="sufficient_evidence", sessions_completed=t,
            watch_flag=True, rank_within_t=rank, practice_trajectory="needs_attention",
        )

    early = _card(uuid.UUID(int=1), 3, 1)
    late = _card(uuid.UUID(int=2), 19, 1)
    ordered = dashboard_service._sort_watch_list([early, late])
    assert [c.t for c in ordered] == [19, 3]


# --- authorization ----------------------------------------------------------------------


def test_a_classroom_the_teacher_does_not_own_is_403(client):
    """The fail-closed guard. A classroom owned by someone else and one that does not exist
    are the same answer, so the response cannot be used to probe for existence."""

    stranger = uuid.uuid4()
    for route in (
        f"/api/v1/t3/classes/{stranger}/cohort",
        f"/api/v1/t3/classes/{stranger}/watch",
    ):
        assert client.get(route).status_code == 403


def test_a_learner_the_teacher_cannot_see_is_403(client):
    assert client.get(f"/api/v1/t3/students/{uuid.uuid4()}").status_code == 403


def test_every_route_requires_a_principal(monkeypatch):
    """Proves the dependency is wired on every route rather than assumed. With no override
    and no Authorization header, each must refuse -- never 200."""

    _set_env(monkeypatch)
    from app.main import create_app

    with TestClient(create_app()) as bare:
        for route in ALL_ROUTES:
            assert bare.get(route).status_code in (401, 403), route


def test_a_missing_pipeline_run_is_503_not_an_empty_dashboard(client, monkeypatch):
    """An empty dashboard reads to a teacher as 'nobody needs attention'. A server-state
    failure must never be able to produce that."""

    from app.application.data_access import ActivePipelineRunError

    async def _boom(_session, *, active_model_version):
        raise ActivePipelineRunError("no run")

    monkeypatch.setattr(dashboard_service.data_access, "active_pipeline_run", _boom)
    response = client.get("/api/v1/t3/home")
    assert response.status_code == 503
    assert response.json()["detail"]["stage"] == "pipeline_run"


# ------------------------------------------------------------------------------------------
# B6.3d — the fields the dashboard frontend needs, and the two judgements inside them.
# ------------------------------------------------------------------------------------------


def test_home_serves_teacher_name_grade_and_pending_requests(client):
    body = client.get("/api/v1/t3/home").json()
    assert body["teacher_name"] == "Teacher01"
    card = body["classes"][0]
    assert card["grade"] == "GRADE_3"
    assert card["pending_request_count"] == 3


def test_cohort_serves_class_name_grade_and_pending_requests(client):
    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()
    assert body["class_name"] == "Grade 3 Maths"
    assert body["grade"] == "GRADE_3"
    assert body["pending_request_count"] == 3


def test_cohort_serves_the_permanent_class_key(client):
    """B7. D1 makes the key permanent, so the cohort response carries it rather than the
    client fetching it separately -- and the frontend has no key endpoint to call."""

    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()
    assert body["class_key"] == "7K4P92"


def test_cohort_serves_a_null_class_key_when_none_was_ever_minted(monkeypatch, client):
    """Never `""`. Every classroom that exists today was created through the student app's
    API, which writes no `t3_classroom_keys` row, so "no key yet" is the ORDINARY state --
    and six blank characters is something a teacher would try to read aloud."""

    async def _no_keys(_session, _classroom_ids):
        return {}

    monkeypatch.setattr(dashboard_service.data_access, "class_keys_for_classrooms", _no_keys)
    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()
    assert body["class_key"] is None


def test_watch_list_carries_the_population_it_was_drawn_from(client):
    """`total_students` is the denominator, not the list length.

    Without it a teacher sees a bare count, and `frontend_plan.md` section 1 records why that
    is wrong: "71 of 83" reads as escalation when it is saturation -- a weaker signal, not a
    stronger one.
    """

    body = client.get("/api/v1/t3/watch").json()
    assert body["total_students"] == 2
    assert len(body["learners"]) == 1  # only the flagged learner is listed

    scoped = client.get(f"/api/v1/t3/classes/{CLASSROOM}/watch").json()
    assert scoped["total_students"] == 2


def test_student_detail_serves_the_class_name(client):
    body = client.get(f"/api/v1/t3/students/{LEARNER}").json()
    assert body["class_name"] == "Grade 3 Maths"


def test_learner_card_carries_its_classroom_and_provenance(client):
    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()
    card = next(c for c in body["learners"] if c["student_id"] == str(LEARNER))
    assert card["classroom_id"] == str(CLASSROOM)
    assert card["model_version"] == "1.0.0"
    assert card["inference_timestamp"].startswith("2026-09-13T19:30")
    assert card["explanation"] == "Flagged for teacher review."


def test_sparklines_preserve_nulls_and_are_not_zero_filled(client):
    """A session where Component B recorded nothing is an ABSENCE.

    Zero-filling it would draw a 0% accuracy point -- inventing a bad session out of a missing
    one, on a chart a teacher reads as progress. The fixture's second session has a null
    accuracy for exactly this assertion.
    """

    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()
    card = next(c for c in body["learners"] if c["student_id"] == str(LEARNER))

    assert card["accuracy_sparkline"] == [0.4, None]
    assert 0 not in card["accuracy_sparkline"]
    assert card["engagement_sparkline"] == [0.7, 0.8]
    assert card["last_active_date"] == "2026-01-12"


def test_a_learner_with_no_prediction_gets_null_provenance(client, monkeypatch):
    """A rostered learner absent from the run has never been scored.

    `model_version` must be null -- NOT the active run's version. Stamping an unscored learner
    with a model that never saw them would be a fabricated provenance claim, and a quiet one:
    it would look entirely normal on screen.
    """

    # Must collide with no other constant in this module -- an id that happens to equal
    # OTHER_LEARNER would silently test the scored path instead.
    unscored = uuid.UUID("eeeeeeee-5555-4555-8555-eeeeeeeeeeee")

    async def _roster_with_unscored(_session, _classroom_id):
        return [_Learner(LEARNER, "Amara"), _Learner(unscored, "Unscored")]

    monkeypatch.setattr(
        dashboard_service.data_access, "classroom_roster", _roster_with_unscored
    )

    body = client.get(f"/api/v1/t3/classes/{CLASSROOM}/cohort").json()
    card = next(c for c in body["learners"] if c["student_id"] == str(unscored))

    assert card["model_version"] is None
    assert card["inference_timestamp"] is None
    assert card["t"] == 0
    assert card["evidence_status"] == "insufficient_exposure"
    assert card["watch_flag"] is False
    assert card["classroom_id"] == str(CLASSROOM)


def test_student_detail_serves_the_classroom_id_for_the_back_link(client):
    """`StudentDetail.tsx` links back to `/classes/{snapshot.classId}`.

    Lives here rather than in `test_sessions_api.py` because only this module's prediction
    double carries everything `/students/{id}` reads.
    """

    body = client.get(f"/api/v1/t3/students/{LEARNER}").json()
    assert body["classroom_id"] == str(CLASSROOM)
    assert body["class_name"] == "Grade 3 Maths"
