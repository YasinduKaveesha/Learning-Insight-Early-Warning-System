"""Recommendation endpoints and domain rules (work order B7) -- offline.

The state machine itself is enforced by the database and is tested live in
`tests/test_recommendation_transitions_live.py`. This module pins what does not need a database:

* the never-served evidence filter (`mastery_current` in `docs/10`'s own example must not reach a
  client),
* the open action vocabulary (D7 closed the words, not the schema -- an unknown kind is valid),
* the HTTP mapping: 403 for invisible-or-nonexistent, 409 with a named reason, 401/403 with no
  principal,
* and that NO route can create a recommendation, because the trigger -> action mapping is not
  decided (`dev_docs/QUESTIONS_FOR_ML_TEAM_4.md`).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import dependencies
from app.application import recommendation_service
from app.domain.dashboard import DISCLOSURE
from app.domain.principal import Principal
from app.domain.recommendations import (
    ActionOut,
    ModifyRequest,
    RecommendationListResponse,
    RecommendationOut,
    TriggerOut,
    filter_evidence,
)
from tests.test_dashboard_api import TEACHER, LEARNER, _set_env, assert_no_forbidden_fields

RECO = uuid.UUID("eeeeeeee-5555-4555-8555-eeeeeeeeeeee")


def _reco(**overrides) -> RecommendationOut:
    fields = dict(
        recommendation_id=RECO,
        student_id=LEARNER,
        issued_at_intervention_session=5,
        expires_after_session=10,
        target_component="B",
        trigger=TriggerOut(type="stagnation", skill="subtraction", evidence={"opportunities_w4": 12}),
        proposed_action=ActionOut(kind="practice", detail={"skill": "subtraction"}),
        evidence_summary="Subtraction has been practised for four sessions without moving.",
        teacher_status="pending",
    )
    fields.update(overrides)
    return RecommendationOut(**fields)


# --- domain ----------------------------------------------------------------------------


def test_evidence_filter_drops_mastery_and_research_labels():
    """`docs/10` section 6's own example evidence carries `mastery_current`. Rule 3 of
    `app/domain/sessions.py` forbids serving absolute mastery in any form, so it is stripped on
    the way out whatever a future generator stores."""

    evidence = {
        "mastery_current": 0.44,
        "mastery_slope_w4": 0.001,
        "opportunities_w4": 12,
        "population": "DD",
        "dd_subtype": "x",
        "prob_class_2plus": 0.9,
        "prob_class_3": 0.1,
        "risk_level": "High",
    }
    assert filter_evidence(evidence) == {"mastery_slope_w4": 0.001, "opportunities_w4": 12}


def test_evidence_filter_tolerates_missing_evidence():
    assert filter_evidence(None) == {}
    assert filter_evidence({}) == {}


def test_an_unknown_action_kind_is_valid():
    """D7 froze the vocabulary by decision, not by schema (`docs/13` section 5): an unknown kind
    must render through a fallback, not fail validation."""

    body = ModifyRequest(teacher_modified_action={"kind": "insert_spaced_review", "detail": {}})
    assert body.teacher_modified_action.kind == "insert_spaced_review"


def test_a_blank_modified_kind_is_rejected():
    with pytest.raises(ValidationError):
        ModifyRequest(teacher_modified_action={"kind": "   ", "detail": {}})


def test_modify_requires_exactly_one_action():
    """`decide` refuses a mismatched call before touching a database."""

    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(recommendation_service.decide(None, TEACHER, RECO, "modified"))
    with pytest.raises(ValueError):
        asyncio.run(
            recommendation_service.decide(
                None, TEACHER, RECO, "accepted", modified_action=ActionOut(kind="review")
            )
        )


def test_expiry_is_measured_against_the_learners_latest_session():
    assert recommendation_service._is_expired(10, 11) is True
    assert recommendation_service._is_expired(10, 10) is False
    # No known session is no evidence of expiry.
    assert recommendation_service._is_expired(10, None) is False


# --- HTTP ------------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    app = create_app()

    async def _principal():
        return Principal(teacher_profile_id=TEACHER, resolution="demo")

    async def _session():
        yield None

    app.dependency_overrides[dependencies.current_principal] = _principal
    app.dependency_overrides[dependencies.db_session] = _session
    with TestClient(app) as test_client:
        yield test_client


def test_list_serves_the_disclosure_and_no_forbidden_field(client, monkeypatch):
    seen = {}

    async def _list(_session, teacher, student, *, model_version, status_filter):
        seen["status_filter"] = status_filter
        return RecommendationListResponse(student_id=student, recommendations=[_reco()])

    monkeypatch.setattr(recommendation_service, "list_for_student", _list)
    response = client.get(f"/api/v1/t3/students/{LEARNER}/recommendations")
    assert response.status_code == 200
    body = response.json()
    assert body["disclosure"] == DISCLOSURE
    assert body["recommendations"][0]["proposed_action"]["kind"] == "practice"
    assert body["recommendations"][0]["b_applied_at_intervention_session"] is None
    assert seen["status_filter"] == "active"
    assert_no_forbidden_fields(body)


def test_list_accepts_status_all_and_rejects_anything_else(client, monkeypatch):
    async def _list(_session, teacher, student, *, model_version, status_filter):
        return RecommendationListResponse(student_id=student, recommendations=[])

    monkeypatch.setattr(recommendation_service, "list_for_student", _list)
    assert client.get(f"/api/v1/t3/students/{LEARNER}/recommendations?status=all").status_code == 200
    assert client.get(f"/api/v1/t3/students/{LEARNER}/recommendations?status=bogus").status_code == 422


def test_list_for_an_invisible_learner_is_403(client, monkeypatch):
    async def _list(*_args, **_kwargs):
        raise recommendation_service.LearnerNotVisibleError("x")

    monkeypatch.setattr(recommendation_service, "list_for_student", _list)
    assert client.get(f"/api/v1/t3/students/{LEARNER}/recommendations").status_code == 403


@pytest.mark.parametrize(
    "action, decision", [("accept", "accepted"), ("dismiss", "dismissed")]
)
def test_accept_and_dismiss_reach_the_service_with_the_right_decision(
    client, monkeypatch, action, decision
):
    seen = {}

    async def _decide(_session, teacher, reco_id, got, *, modified_action=None):
        seen.update(teacher=teacher, reco_id=reco_id, decision=got, modified=modified_action)
        return _reco(teacher_status=got)

    monkeypatch.setattr(recommendation_service, "decide", _decide)
    response = client.post(f"/api/v1/t3/recommendations/{RECO}/{action}")
    assert response.status_code == 200
    assert response.json()["teacher_status"] == decision
    assert seen == dict(teacher=TEACHER, reco_id=RECO, decision=decision, modified=None)


def test_modify_passes_the_teachers_action(client, monkeypatch):
    seen = {}

    async def _decide(_session, teacher, reco_id, got, *, modified_action=None):
        seen["action"] = modified_action
        return _reco(teacher_status="modified", teacher_modified_action=modified_action)

    monkeypatch.setattr(recommendation_service, "decide", _decide)
    response = client.post(
        f"/api/v1/t3/recommendations/{RECO}/modify",
        json={"teacher_modified_action": {"kind": "review", "detail": {"skill": "place_value"}}},
    )
    assert response.status_code == 200
    assert seen["action"].kind == "review"
    assert response.json()["teacher_modified_action"]["detail"] == {"skill": "place_value"}


def test_modify_without_a_body_is_422(client):
    assert client.post(f"/api/v1/t3/recommendations/{RECO}/modify").status_code == 422


@pytest.mark.parametrize("reason", ["already_decided", "expired"])
def test_an_illegal_transition_is_409_with_a_named_reason(client, monkeypatch, reason):
    async def _decide(*_args, **_kwargs):
        raise recommendation_service.RecommendationConflictError(reason)

    monkeypatch.setattr(recommendation_service, "decide", _decide)
    response = client.post(f"/api/v1/t3/recommendations/{RECO}/accept")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == reason


def test_an_unknown_or_invisible_recommendation_is_one_indistinguishable_403(client, monkeypatch):
    async def _decide(*_args, **_kwargs):
        raise recommendation_service.LearnerNotVisibleError("x")

    monkeypatch.setattr(recommendation_service, "decide", _decide)
    assert client.post(f"/api/v1/t3/recommendations/{RECO}/dismiss").status_code == 403


def test_every_recommendation_route_requires_a_principal(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    with TestClient(create_app()) as bare:
        assert bare.get(f"/api/v1/t3/students/{LEARNER}/recommendations").status_code in (401, 403)
        for action in ("accept", "dismiss"):
            assert bare.post(f"/api/v1/t3/recommendations/{RECO}/{action}").status_code in (401, 403)


def test_no_route_can_create_a_recommendation(monkeypatch):
    """The trigger -> action mapping is undecided (`docs/13` section 5, `QUESTIONS_FOR_ML_TEAM_4`).
    The only writes permitted are the three teacher decisions on an existing recommendation."""

    _set_env(monkeypatch)
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    writes = sorted(
        path
        for path, operations in paths.items()
        if "recommendation" in path and set(operations) & {"post", "put", "patch", "delete"}
    )
    assert writes == [
        "/api/v1/t3/recommendations/{recommendation_id}/accept",
        "/api/v1/t3/recommendations/{recommendation_id}/dismiss",
        "/api/v1/t3/recommendations/{recommendation_id}/modify",
    ]


def test_the_service_never_writes_the_write_back_columns():
    """D10. No `.values(...)` write and no ORM constructor in the service may name
    `b_applied_*` / `c_applied_*` -- not even to None, where a later edit could quietly change
    the value. Reading them into a response is fine, so this inspects WRITES only, by syntax
    tree rather than by text. The live suite additionally proves both stay NULL after a real
    decision."""

    import ast
    from pathlib import Path

    tree = ast.parse(Path(recommendation_service.__file__).read_text(encoding="utf-8"))
    write_callees = {"values", "Recommendation", "RecommendationTransition", "insert", "update"}
    offending = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if callee not in write_callees:
            continue
        offending += [
            kw.arg
            for kw in node.keywords
            if kw.arg in {"b_applied_at_intervention_session", "c_applied_at_intervention_session"}
        ]
    assert offending == []
