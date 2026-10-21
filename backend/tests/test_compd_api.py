"""CompD's teacher side, served by Component 3 (owner direction 2026-10-21) -- offline.

Covers what the routes RETURN and refuse, with the readers and the bank stubbed: the students
dashboard against hand-computed compD maths, the never-served fields, 404/409/422 mapping, the
options rule, the AI drafts against a stand-in Gemini, and that no route works without a
principal or offers a PUT/PATCH/DELETE. The question bank against a real database is
`test_compd_questions_live.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.api.routes import compd as compd_routes
from app.application import compd_maths, compd_service, data_access
from app.domain.compd import CompdProfile, CompdProfileStats, CompdStudentPerformance, CompdStudentSummary
from app.domain.principal import Principal
from app.infrastructure import compd_ai
from app.infrastructure.compd_ai import GEMINI_MODEL, build_prompt
from tests.test_dashboard_api import TEACHER, _set_env, assert_no_forbidden_fields

PREFIX = "/api/v1/t3/compd"
AMAL = uuid.UUID("11111111-1111-4111-8111-111111111111")
BIMAL = uuid.UUID("22222222-2222-4222-8222-222222222222")
CHAMAL = uuid.UUID("33333333-3333-4333-8333-333333333333")
RUN_1 = uuid.UUID("44444444-4444-4444-8444-444444444444")
RUN_2 = uuid.UUID("55555555-5555-4555-8555-555555555555")
T0 = dt.datetime(2026, 10, 20, 9, 30, tzinfo=dt.timezone.utc)
T1 = dt.datetime(2026, 10, 21, 9, 30, tzinfo=dt.timezone.utc)
BANNED_PROMPT_TERMS = (
    "diagnos", "dyscalculia", "disorder", "deficit", "disability", "impairment", "screening", "detected",
)
ALL_ROUTES = [
    ("get", f"{PREFIX}/dashboard"),
    ("get", f"{PREFIX}/students/{AMAL}/profiles"),
    ("get", f"{PREFIX}/questions"),
    ("post", f"{PREFIX}/questions"),
    ("post", f"{PREFIX}/questions/{uuid.uuid4()}/update"),
    ("post", f"{PREFIX}/questions/{uuid.uuid4()}/delete"),
    ("post", f"{PREFIX}/questions/drafts"),
]


def _answer(question_id, topic, *, matched, seconds, run, at, attempts=1, assist=False):
    return SimpleNamespace(
        learner_id=AMAL, session_id=run, question_id=question_id, topic=topic,
        response_time_sec=seconds, attempts=attempts, response_matched=matched,
        assist_used=assist, created_at_utc=at,
    )


def _stored_profile(learner_id, run, *, memory="medium", speed="Moderate", at=T1, accuracy=0.75):
    return SimpleNamespace(
        learner_id=learner_id, session_id=run, memory_level=memory, attention_level="medium",
        number_sense_level="high", processing_speed_level=speed, generated_at=at,
        # What the student app stores, including values the dashboard must never serve.
        features={
            "accuracy": accuracy, "avg_response_time_ms": 3000.0, "response_time_std_ms": 12.0,
            "avg_attempts": 1.25, "retry_rate": 0.25, "hint_rate": 0.25,
            "mean_clicks_per_question": 1.0, "total_questions": 4,
        },
        confidence_score=0.83,
        model_version="rule-based-v2",
    )


@pytest.fixture
def stub_reads(monkeypatch):
    learners = [
        SimpleNamespace(learner_id=CHAMAL, name="chamal", grade=None, classroom_name=None),
        SimpleNamespace(learner_id=AMAL, name="Amal", grade=2, classroom_name="Grade 2 Gold"),
        SimpleNamespace(learner_id=BIMAL, name="Bimal", grade=3, classroom_name="Other Teacher's Class"),
    ]
    answers = [
        _answer("a", "Addition", matched=True, seconds=2.0, run=RUN_1, at=T0),
        _answer("b", "Addition", matched=False, seconds=4.0, run=RUN_1, at=T0, attempts=2, assist=True),
        _answer("c", "Counting", matched=True, seconds=3.0, run=RUN_2, at=T1),
        _answer("d", "Addition", matched=True, seconds=3.0, run=RUN_2, at=T1),
    ]

    async def _learners(_session):
        return learners

    async def _learner(_session, learner_id):
        return next((l for l in learners if l.learner_id == learner_id), None)

    async def _interactions(_session):
        return answers

    async def _latest(_session):
        return [_stored_profile(AMAL, RUN_2), _stored_profile(BIMAL, RUN_1, memory="low", speed="Slow")]

    async def _history(_session, learner_id, limit):
        rows = [_stored_profile(AMAL, RUN_2, at=T1), _stored_profile(AMAL, RUN_1, at=T0, accuracy=0.5)]
        return rows[:limit] if learner_id == AMAL else []

    monkeypatch.setattr(data_access, "compd_learners", _learners)
    monkeypatch.setattr(data_access, "compd_learner", _learner)
    monkeypatch.setattr(data_access, "compd_interactions", _interactions)
    monkeypatch.setattr(data_access, "compd_latest_profiles", _latest)
    monkeypatch.setattr(data_access, "compd_profile_history", _history)


def _app(monkeypatch, *, gemini_key=None):
    _set_env(monkeypatch)
    if gemini_key is None:
        monkeypatch.setenv("GEMINI_API_KEY", "")
    else:
        monkeypatch.setenv("GEMINI_API_KEY", gemini_key)
    from app.infrastructure.settings import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()

    async def _principal():
        return Principal(teacher_profile_id=TEACHER, resolution="real")

    async def _session():
        yield None

    app.dependency_overrides[dependencies.current_principal] = _principal
    app.dependency_overrides[dependencies.db_session] = _session
    return app


@pytest.fixture
def client(monkeypatch):
    with TestClient(_app(monkeypatch)) as test_client:
        yield test_client


# ---------------------------------------------------------------- routes and guards


def test_the_six_paths_seven_operations_and_nothing_else(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    paths = {
        path: sorted(methods)
        for path, methods in (
            (p, [m for m in ops if m in {"get", "post", "put", "patch", "delete"}])
            for p, ops in create_app().openapi()["paths"].items()
        )
        if path.startswith(PREFIX)
    }
    assert paths == {
        f"{PREFIX}/dashboard": ["get"],
        f"{PREFIX}/students/{{student_id}}/profiles": ["get"],
        f"{PREFIX}/questions": ["get", "post"],
        f"{PREFIX}/questions/{{question_id}}/update": ["post"],
        f"{PREFIX}/questions/{{question_id}}/delete": ["post"],
        f"{PREFIX}/questions/drafts": ["post"],
    }


@pytest.mark.parametrize("method,path", ALL_ROUTES)
def test_every_route_requires_a_principal(monkeypatch, method, path):
    _set_env(monkeypatch)
    from app.main import create_app

    with TestClient(create_app()) as bare:
        call = getattr(bare, method)
        response = call(path, json={}) if method == "post" else call(path)
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------- the students dashboard


def test_dashboard_lists_every_real_child_by_name_with_compds_maths(client, stub_reads):
    response = client.get(f"{PREFIX}/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert_no_forbidden_fields(body)

    students = body["students"]
    assert [s["name"] for s in students] == ["Amal", "Bimal", "chamal"], "by name, case-insensitively"
    amal, bimal, chamal = students
    assert amal["classroom_name"] == "Grade 2 Gold"
    assert amal["grade"] == "2"
    assert bimal["classroom_name"] == "Other Teacher's Class", "every teacher's classes are listed"
    assert chamal["classroom_name"] is None

    # Four answers, two runs: 3/4 correct, 3.0s mean, attempts 5/4, one retry, one hint.
    assert amal["performance"] == {
        "total_questions": 4, "completed_sessions": 2, "accuracy": 0.75, "avg_response_time_sec": 3.0,
        "avg_attempts": 1.25, "retry_rate": 0.25, "hint_rate": 0.25, "last_topic": "Addition",
        "topics": [
            {"topic": "Addition", "total_questions": 3, "accuracy": 0.67, "avg_response_time_sec": 3.0,
             "retry_rate": 0.33, "hint_rate": 0.33},
            {"topic": "Counting", "total_questions": 1, "accuracy": 1.0, "avg_response_time_sec": 3.0,
             "retry_rate": 0.0, "hint_rate": 0.0},
        ],
    }
    assert amal["total_interactions"] == 4
    assert amal["last_activity_date"].startswith("2026-10-21T09:30")
    assert chamal["latest_profile"] is None
    assert chamal["last_activity_date"] is None
    assert chamal["performance"]["avg_attempts"] == 1.0

    assert body["stats"] == {
        "total_students": 3, "students_with_profiles": 2, "total_interactions": 4,
        "average_accuracy": 0.75, "average_response_time_sec": 3.0,
        "needs_support_count": 1,  # Bimal: a low level and Slow speed
    }


def test_a_profile_carries_levels_text_and_stats_but_no_confidence_or_model(client, stub_reads):
    profile = client.get(f"{PREFIX}/dashboard").json()["students"][0]["latest_profile"]
    assert set(profile) == {
        "session_id", "memory_level", "attention_level", "number_sense_level",
        "processing_speed_level", "recommendation", "features", "generated_at",
    }
    assert set(profile["features"]) == {
        "accuracy", "avg_response_time_ms", "retry_rate", "hint_rate", "total_questions",
    }
    text = json.dumps(profile)
    assert "confidence" not in text and "model_version" not in text and "rule-based" not in text
    # 0.75 is not below compD's 0.75 threshold, so it reads as good accuracy.
    assert profile["recommendation"].startswith("The student demonstrated good accuracy overall.")


def test_student_profiles_are_newest_first_bounded_and_404_for_unknown(client, stub_reads):
    response = client.get(f"{PREFIX}/students/{AMAL}/profiles")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Amal"
    assert body["classroom_name"] == "Grade 2 Gold"
    assert [p["session_id"] for p in body["items"]] == [str(RUN_2), str(RUN_1)]
    assert_no_forbidden_fields(body)

    assert len(client.get(f"{PREFIX}/students/{AMAL}/profiles?limit=1").json()["items"]) == 1
    assert client.get(f"{PREFIX}/students/{AMAL}/profiles?limit=0").status_code == 422
    assert client.get(f"{PREFIX}/students/{AMAL}/profiles?limit=101").status_code == 422
    assert client.get(f"{PREFIX}/students/{CHAMAL}/profiles").json()["items"] == []
    assert client.get(f"{PREFIX}/students/{uuid.uuid4()}/profiles").status_code == 404


# ---------------------------------------------------------------- compD's rules, by hand


def _summary(total, accuracy, seconds, profile=None):
    return CompdStudentSummary(
        student_id=uuid.uuid4(), name=None, grade=None, classroom_name=None,
        total_interactions=total, latest_profile=profile, last_activity_date=None,
        performance=CompdStudentPerformance(
            total_questions=total, completed_sessions=1 if total else 0, accuracy=accuracy,
            avg_response_time_sec=seconds, avg_attempts=1.0, retry_rate=0.0, hint_rate=0.0,
            last_topic=None, topics=[],
        ),
    )


def _profile(**levels):
    base = {"memory_level": "medium", "attention_level": "medium", "number_sense_level": "medium",
            "processing_speed_level": "Moderate"}
    base.update(levels)
    return CompdProfile(
        session_id=uuid.uuid4(), recommendation="-", generated_at=T0,
        features=CompdProfileStats(accuracy=0.5, avg_response_time_ms=1.0, retry_rate=0.0, hint_rate=0.0, total_questions=1),
        **base,
    )


def test_needs_support_at_compds_boundaries():
    assert compd_maths.needs_support(_summary(0, 0.0, 0.0, _profile(processing_speed_level="Slow")))
    assert compd_maths.needs_support(_summary(0, 0.0, 0.0, _profile(memory_level="low")))
    assert not compd_maths.needs_support(_summary(0, 0.0, 0.0, _profile()))
    assert compd_maths.needs_support(_summary(5, 0.59, 3.0))
    assert not compd_maths.needs_support(_summary(5, 0.6, 3.0)), "0.6 is not below 0.6"
    assert not compd_maths.needs_support(_summary(4, 0.0, 3.0)), "fewer than 5 questions"


def test_dashboard_stats_are_weighted_by_question_count():
    """4 at 0.75 / 3.0s and 5 at 0.4 / 5.0s: (3 + 2) / 9 = 0.56, 37 / 9 = 4.1s."""

    stats = compd_maths.dashboard_stats([
        _summary(4, 0.75, 3.0), _summary(5, 0.4, 5.0), _summary(0, 0.0, 0.0, _profile(processing_speed_level="Slow")),
    ])
    assert stats.model_dump() == {
        "total_students": 3, "students_with_profiles": 1, "total_interactions": 9,
        "average_accuracy": 0.56, "average_response_time_sec": 4.1, "needs_support_count": 2,
    }


def test_the_recommendation_is_compds_text():
    text = compd_maths.recommendation(
        {"memory_level": "low", "attention_level": "high", "number_sense_level": "high", "processing_speed_level": "Slow"},
        accuracy=0.4,
        avg_response_time_ms=9000.0,
    )
    insight, tips = text.split("\n\n")
    assert insight == (
        "The student answered less than half of the questions correctly. Response times were higher "
        "than expected, suggesting the student may need more thinking time. Areas that may need "
        "additional support: memory, processing speed."
    )
    assert tips.startswith("Memory support:") and "Processing speed support:" in tips
    strong = compd_maths.recommendation(
        {"memory_level": "high", "attention_level": "high", "number_sense_level": "high", "processing_speed_level": "Fast"},
        accuracy=0.9,
        avg_response_time_ms=2000.0,
    )
    assert strong.endswith("Great performance! Continue with current activities and gradually increase the challenge level to maintain growth.")


# ---------------------------------------------------------------- the question bank's routes


def _question(**overrides):
    body = {"question_code": "ADD-1", "topic": "Addition", "difficulty": "Easy",
            "question_text": "2 + 3 = ?", "correct_answer": "5", "options": ["4", "6"]}
    body.update(overrides)
    return body


def test_create_applies_the_options_rule_before_the_bank_sees_it(client, monkeypatch):
    seen = []

    async def _create(_session, teacher, body):
        seen.append((teacher, body))
        return {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": T0.isoformat()}

    monkeypatch.setattr(compd_service, "create_question", _create)
    response = client.post(f"{PREFIX}/questions", json=_question())
    assert response.status_code == 201, response.text
    assert seen[0][0] == TEACHER, "the author is the signed-in teacher"
    assert seen[0][1].options == ["4", "6", "5"], "the answer is appended"

    for bad in (
        _question(options=["5"]),                          # only the answer
        _question(options=["1", "2", "3", "4", "6", "7"]),  # 7 with the answer
        _question(options=["1", " "]),
        _question(topic="Number Comparison"),               # Q11: the four topics
        _question(question_text="x" * 501),
        _question(question_code="C" * 33),
        {**_question(), "expected_response": "5"},          # unknown fields are refused
    ):
        assert client.post(f"{PREFIX}/questions", json=bad).status_code == 422, bad
    assert len(seen) == 1


def test_a_code_clash_is_409_and_an_unknown_question_404(client, monkeypatch):
    async def _clash(*_args, **_kwargs):
        raise compd_service.CompdConflictError()

    async def _missing(*_args, **_kwargs):
        raise compd_service.CompdNotFoundError()

    async def _bad_options(*_args, **_kwargs):
        raise compd_service.CompdOptionsError("add at least one other option")

    monkeypatch.setattr(compd_service, "create_question", _clash)
    assert client.post(f"{PREFIX}/questions", json=_question()).status_code == 409

    monkeypatch.setattr(compd_service, "update_question", _missing)
    assert client.post(f"{PREFIX}/questions/{uuid.uuid4()}/update", json={"question_text": "x"}).status_code == 404
    monkeypatch.setattr(compd_service, "update_question", _clash)
    assert client.post(f"{PREFIX}/questions/{uuid.uuid4()}/update", json={"question_code": "X"}).status_code == 409
    monkeypatch.setattr(compd_service, "update_question", _bad_options)
    assert client.post(f"{PREFIX}/questions/{uuid.uuid4()}/update", json={"options": ["5"]}).status_code == 422

    monkeypatch.setattr(compd_service, "delete_question", _missing)
    assert client.post(f"{PREFIX}/questions/{uuid.uuid4()}/delete").status_code == 404

    assert client.post(f"{PREFIX}/questions/{uuid.uuid4()}/update", json={}).status_code == 422
    assert client.get(f"{PREFIX}/questions?topic=Algebra").status_code == 422
    assert client.get(f"{PREFIX}/questions?limit=101").status_code == 422


# ---------------------------------------------------------------- AI drafts, against a stand-in Gemini


def _gemini(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _drafts_client(monkeypatch, handler, *, key="test-gemini-key-not-real"):
    app = _app(monkeypatch, gemini_key=key)
    monkeypatch.setattr(compd_ai, "RETRY_PAUSE_SECONDS", 0)
    app.dependency_overrides[compd_routes.ai_transport] = lambda: httpx.MockTransport(handler)
    return TestClient(app)


DRAFT_BODY = {"topic": "Subtraction", "difficulty": "Medium", "count": 5, "instructions": "Use fruit"}


def test_drafts_are_returned_unsaved_topic_forced_garbage_dropped(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return _gemini({"questions": [
            {"topic": "Fractions", "difficulty": "Impossible", "question_text": "9 - 4 = ?",
             "correct_answer": "5", "options": ["4", "6"]},
            {"topic": "Subtraction", "difficulty": "Easy", "question_text": "7 - 2 = ?",
             "correct_answer": "5", "options": ["5", "3", "4"]},
            {"question_text": "", "correct_answer": "1", "options": ["1", "2"]},
            {"question_text": "One option", "correct_answer": "1", "options": ["1"]},
            "not an object",
        ]})

    async def _never(*_args, **_kwargs):
        raise AssertionError("a draft must never be saved by the drafts route")

    monkeypatch.setattr(compd_service, "create_question", _never)
    with _drafts_client(monkeypatch, handler) as client:
        response = client.post(f"{PREFIX}/questions/drafts", json=DRAFT_BODY)
    assert response.status_code == 200, response.text
    drafts = response.json()["drafts"]
    assert len(drafts) == 2
    assert {d["topic"] for d in drafts} == {"Subtraction"}
    assert drafts[0]["difficulty"] == "Medium" and drafts[1]["difficulty"] == "Easy"
    assert drafts[0]["options"] == ["4", "6", "5"]

    request = seen[0]
    assert GEMINI_MODEL in str(request.url)
    assert "test-gemini-key-not-real" not in str(request.url), "the key is a header, never the URL"
    assert request.headers["x-goog-api-key"] == "test-gemini-key-not-real"
    prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
    assert prompt == build_prompt("Subtraction", "Medium", 5, "Use fruit"), "only the four request values"
    assert "children aged 6-8" in prompt
    assert not any(term in prompt.lower() for term in BANNED_PROMPT_TERMS)


@pytest.mark.parametrize(
    "reply,status_code",
    [
        (_gemini("not json at all"), 422),
        (_gemini({"questions": []}), 422),
        (httpx.ReadTimeout("timed out"), 503),
        (httpx.ConnectError("unreachable"), 503),
        (httpx.Response(500, json={"error": "boom"}), 503),
        (httpx.Response(200, json={"candidates": []}), 503),
    ],
)
def test_nothing_usable_is_422_and_an_unavailable_ai_is_503(monkeypatch, reply, status_code):
    def handler(request):
        if isinstance(reply, Exception):
            raise reply
        return reply

    with _drafts_client(monkeypatch, handler) as client:
        response = client.post(f"{PREFIX}/questions/drafts", json=DRAFT_BODY)
    assert response.status_code == status_code, response.text
    assert "test-gemini-key-not-real" not in response.text


def test_a_busy_model_falls_back_and_a_final_answer_is_not_retried(monkeypatch):
    # Live 2026-10-21: gemini-3.6-flash answered 503 "high demand" on most calls.
    models: list[str] = []

    def busy_then_fine(request):
        models.append(request.url.path)
        if GEMINI_MODEL in request.url.path:
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        return _gemini({"questions": [{"question_text": "2 + 2 = ?", "correct_answer": "4", "options": ["3", "4"]}]})

    with _drafts_client(monkeypatch, busy_then_fine) as client:
        response = client.post(f"{PREFIX}/questions/drafts", json=DRAFT_BODY)
    assert response.status_code == 200, response.text
    assert len(response.json()["drafts"]) == 1
    assert len(models) == 2 and compd_ai.FALLBACK_MODEL in models[1]

    calls: list[httpx.Request] = []

    def bad_key(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})

    with _drafts_client(monkeypatch, bad_key) as client:
        assert client.post(f"{PREFIX}/questions/drafts", json=DRAFT_BODY).status_code == 503
    assert len(calls) == 1, "a bad key is final: no second attempt"

    busy: list[httpx.Request] = []
    with _drafts_client(monkeypatch, lambda request: busy.append(request) or httpx.Response(503)) as client:
        assert client.post(f"{PREFIX}/questions/drafts", json=DRAFT_BODY).status_code == 503
    assert len(busy) == len(compd_ai.ATTEMPT_MODELS)


def test_with_no_key_gemini_is_never_called(monkeypatch):
    called = []
    with _drafts_client(monkeypatch, lambda request: called.append(request), key="") as client:
        assert client.post(f"{PREFIX}/questions/drafts", json=DRAFT_BODY).status_code == 503
    assert not called
    with _drafts_client(monkeypatch, lambda request: _gemini({})) as client:
        assert client.post(f"{PREFIX}/questions/drafts", json={**DRAFT_BODY, "count": 0}).status_code == 422
        assert client.post(f"{PREFIX}/questions/drafts", json={**DRAFT_BODY, "count": 11}).status_code == 422
        assert client.post(f"{PREFIX}/questions/drafts", json={**DRAFT_BODY, "instructions": "x" * 301}).status_code == 422


def test_no_write_path_toward_the_student_apps_compd_tables():
    """compD's data stays the student app's: Component 3 only READS `d_*`. The same regexes as
    `test_no_bc_writeback.py`, which covers `b_*`/`c_*` and the identity tables but not `d_*`."""

    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    sql_write = re.compile(r"(insert\s+into|update|delete\s+from)\s+[\"']?d_[a-z_]+\b", re.IGNORECASE)
    core_write = re.compile(
        r"\bd_[a-z_]+\s*\.\s*(insert|update|delete)\s*\(|\b(insert|update|delete)\s*\(\s*d_[a-z_]+\b",
        re.IGNORECASE,
    )
    hits = [
        f"{path.relative_to(backend)}:{n}"
        for root in (backend / "app", backend / "scripts")
        for path in sorted(root.rglob("*.py"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if sql_write.search(line) or core_write.search(line)
    ]
    assert not hits, hits
