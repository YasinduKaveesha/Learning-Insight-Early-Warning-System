"""`app.application.run_cache` -- what it may keep, and what it must not.

The cache is only safe because of three properties, each pinned here:

1. Run data is keyed by `pipeline_run_id`, so a NEW run is never answered with the old one.
2. A cold key is loaded ONCE however many requests arrive together.
3. A batched history read stores each learner separately, so a later single-learner read is a hit.

And one negative: suggestion status is never cached -- a teacher's decision shows at once.
"""

from __future__ import annotations

import asyncio
import types
import uuid

import pytest

from app.application import data_access
from app.application import run_cache as run_cache_module
from app.application.run_cache import RunCache

RUN_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
RUN_B = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000002")
LEARNER_1 = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001")
LEARNER_2 = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")


def _row(**kw):
    return types.SimpleNamespace(**kw)


def test_run_data_is_keyed_by_run_so_a_new_run_is_never_served_the_old_one(monkeypatch) -> None:
    calls: list[uuid.UUID] = []

    async def fake_predictions(_session, run_id, **_kw):
        calls.append(run_id)
        return [_row(student_id=LEARNER_1, t=run_id.int % 100)]

    monkeypatch.setattr(data_access, "predictions_for_run", fake_predictions)
    cache = RunCache()

    async def go():
        a1 = await cache.predictions(None, RUN_A)
        a2 = await cache.predictions(None, RUN_A)
        b1 = await cache.predictions(None, RUN_B)
        return a1, a2, b1

    a1, a2, b1 = asyncio.run(go())
    assert calls == [RUN_A, RUN_B]  # RUN_A read once, RUN_B read separately
    assert a1 is a2
    assert a1[0].t != b1[0].t


def test_a_cold_key_is_loaded_once_under_concurrent_requests(monkeypatch) -> None:
    calls = 0

    async def slow_panel(_session, _run_id, **_kw):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return [_row(student_id=LEARNER_1)]

    monkeypatch.setattr(data_access, "panel_rows_for_run", slow_panel)
    cache = RunCache()

    async def go():
        return await asyncio.gather(*(cache.panel(None, RUN_A) for _ in range(12)))

    results = asyncio.run(go())
    assert calls == 1
    assert all(r is results[0] for r in results)


def test_expired_run_data_is_read_again(monkeypatch) -> None:
    calls = 0

    async def fake_predictions(_session, _run_id, **_kw):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(data_access, "predictions_for_run", fake_predictions)
    monkeypatch.setattr(run_cache_module, "RUN_DATA_TTL_SECONDS", 0.0)
    cache = RunCache()

    async def go():
        await cache.predictions(None, RUN_A)
        await cache.predictions(None, RUN_A)

    asyncio.run(go())
    assert calls == 2


def test_an_active_run_error_is_raised_and_not_remembered(monkeypatch) -> None:
    attempts = 0

    async def failing_then_ok(_session, *, active_model_version):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise data_access.ActivePipelineRunError("no run yet")
        return _row(pipeline_run_id=RUN_A)

    monkeypatch.setattr(data_access, "active_pipeline_run", failing_then_ok)
    cache = RunCache()

    async def go():
        with pytest.raises(data_access.ActivePipelineRunError):
            await cache.active_run(None, model_version="1.0.0")
        return await cache.active_run(None, model_version="1.0.0")

    assert asyncio.run(go()).pipeline_run_id == RUN_A
    assert attempts == 2


def test_a_batched_history_read_makes_each_learner_a_later_cache_hit(monkeypatch) -> None:
    batched: list[list[uuid.UUID]] = []
    single: list[uuid.UUID] = []

    async def fake_batch(_session, _run_id, student_ids):
        batched.append(list(student_ids))
        return [
            _row(student_id=LEARNER_1, intervention_session_number=2),
            _row(student_id=LEARNER_1, intervention_session_number=1),
            _row(student_id=LEARNER_2, intervention_session_number=1),
        ]

    async def fake_single(_session, _run_id, student_id):
        single.append(student_id)
        return []

    monkeypatch.setattr(data_access, "session_history_for_students", fake_batch)
    monkeypatch.setattr(data_access, "session_history_for_student", fake_single)
    cache = RunCache()

    async def go():
        grouped = await cache.history_for_students(None, RUN_A, [LEARNER_1, LEARNER_2])
        one = await cache.history_for_student(None, RUN_A, LEARNER_1)
        again = await cache.history_for_students(None, RUN_A, [LEARNER_1, LEARNER_2])
        return grouped, one, again

    grouped, one, again = asyncio.run(go())
    assert batched == [[LEARNER_1, LEARNER_2]]  # the second batched call was a pure hit
    assert single == []  # the single-learner read never touched the database
    assert [r.intervention_session_number for r in one] == [1, 2]  # sorted per learner
    assert grouped[LEARNER_2] == again[LEARNER_2]


def test_a_learner_with_no_history_is_cached_as_empty_not_refetched(monkeypatch) -> None:
    batched = 0

    async def fake_batch(_session, _run_id, student_ids):
        nonlocal batched
        batched += 1
        return []

    monkeypatch.setattr(data_access, "session_history_for_students", fake_batch)
    cache = RunCache()

    async def go():
        first = await cache.history_for_students(None, RUN_A, [LEARNER_1])
        await cache.history_for_students(None, RUN_A, [LEARNER_1])
        return first

    assert asyncio.run(go()) == {LEARNER_1: []}
    assert batched == 1


def test_the_cache_never_holds_suggestion_status() -> None:
    """Decisions must show on the next request. The cache has no suggestion reader at all,
    and this pins that: adding one would need this test changed, deliberately."""

    cache_methods = {name for name in dir(RunCache) if not name.startswith("_")}
    assert not any("handled" in name or "recommend" in name or "suggest" in name for name in cache_methods)
