"""D30 — the demo stagger: assignment properties, and the truncation invariant.

WHY THIS FILE EXISTS
--------------------
D30 requires that the **entire** learner view truncates at the assigned session `t` — session
history, the trajectory chip, `sessions_completed`, everything, not only the prediction. An
as-of-session-7 forecast displayed beside 25 sessions of visible history is a chronology violation
in the display layer even though the model never saw the future.

The implementation achieves that by cutting the SOURCE (`scripts/filter_research_source.py`) rather
than filtering in the service layer, so every downstream table inherits the cut. That is the right
design, and it also means nothing in the service tests would notice if it regressed. Hence this
file.

Two halves:

* **Assignment properties** — pure, no database. These are the ones that catch a silent change to
  the balance or to determinism, either of which would break reproducibility of the demo.
* **The served invariant** — runs only when ``T3_DEMO_DB_URL`` points at the demo database, and
  skips cleanly otherwise. The demo database is not the test database (`upadya_test`), and the two
  must never be confused: demo rows placed in `upadya_test` collide with the live fixtures'
  `t3_demo_learner_map` entries and break 18 tests.
"""

from __future__ import annotations

import collections
import importlib.util
import json
import os
import uuid
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND_ROOT / "scripts" / "filter_research_source.py"


def _load_filter_module():
    """Import the operational script by path -- it lives in `scripts/`, not in `app/`."""

    spec = importlib.util.spec_from_file_location("_filter_research_source", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ==========================================================================================
# Assignment properties -- no database.
# ==========================================================================================


@pytest.fixture(scope="module")
def filter_module():
    if not _SCRIPT.exists():
        pytest.skip("scripts/filter_research_source.py is absent")
    return _load_filter_module()


@pytest.fixture
def ids() -> list[str]:
    return [f"STU-{i:04d}" for i in range(1, 121)]


def test_assignment_is_deterministic_for_a_given_seed(filter_module, ids) -> None:
    """Reproducibility of the demo depends on this, and D30 forbids re-drawing."""

    first = filter_module.stagger_assignment(ids, 20260914)
    second = filter_module.stagger_assignment(list(reversed(ids)), 20260914)
    assert first == second, "assignment must depend only on the seed and the SORTED id list"


def test_a_different_seed_gives_a_different_assignment(filter_module, ids) -> None:
    assert filter_module.stagger_assignment(ids, 20260914) != filter_module.stagger_assignment(
        ids, 20260915
    )


def test_every_learner_is_assigned_exactly_one_grid_point(filter_module, ids) -> None:
    assignment = filter_module.stagger_assignment(ids, 20260914)
    assert set(assignment) == set(ids)
    assert set(assignment.values()) <= set(filter_module.SUPERVISED_GRID)


def test_assignment_is_balanced_across_the_grid(filter_module, ids) -> None:
    """Balanced, not merely unbiased in expectation.

    120 learners over 9 grid points cannot divide evenly, so the contract is that no grid point
    differs from another by more than one learner. A regression to iid uniform sampling would still
    look "random" while failing this.
    """

    spread = collections.Counter(filter_module.stagger_assignment(ids, 20260914).values())
    assert len(spread) == len(filter_module.SUPERVISED_GRID), "every grid point must be used"
    assert max(spread.values()) - min(spread.values()) <= 1
    assert sum(spread.values()) == len(ids)


def test_grid_matches_the_supervised_snapshots(filter_module) -> None:
    """The grid is the model's, not this script's invention."""

    assert filter_module.SUPERVISED_GRID == (3, 5, 7, 9, 11, 13, 15, 17, 19)


def test_recorded_assignment_matches_the_recorded_seed(filter_module) -> None:
    """The committed audit record must be reproducible from its own declared seed.

    This is what makes "never re-drawn" checkable: if someone re-rolls and keeps the old seed in
    the file, this fails.
    """

    record_path = _BACKEND_ROOT / "scripts" / "demo_stagger_assignment.json"
    if not record_path.exists():
        pytest.skip("no stagger assignment recorded yet")

    record = json.loads(record_path.read_text(encoding="utf-8"))
    recomputed = filter_module.stagger_assignment(list(record["assignment"]), record["seed"])
    assert recomputed == {k: int(v) for k, v in record["assignment"].items()}


# ==========================================================================================
# The served invariant -- demo database only, skips cleanly without it.
# ==========================================================================================

_DEMO_URL = os.environ.get("T3_DEMO_DB_URL")

demo_db = pytest.mark.skipif(
    not _DEMO_URL,
    reason="set T3_DEMO_DB_URL to the demo database to check the D30 truncation invariant",
)


def _query(sql: str, params: dict | None = None):
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.infrastructure.db_url import normalise_async_url

    async def _run():
        engine = create_async_engine(normalise_async_url(_DEMO_URL))
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                return (await session.execute(text(sql), params or {})).all()
        finally:
            await engine.dispose()

    return asyncio.run(_run())


@pytest.fixture(scope="module")
def recorded_assignment() -> dict[str, int]:
    path = _BACKEND_ROOT / "scripts" / "demo_stagger_assignment.json"
    if not path.exists():
        pytest.skip("no stagger assignment recorded")
    record = json.loads(path.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in record["assignment"].items()}


@demo_db
def test_no_panel_session_exceeds_the_assigned_t(recorded_assignment) -> None:
    """The invariant D30 exists to guarantee, checked at the source of everything downstream."""

    rows = _query(
        "SELECT d.research_student_id, MAX(p.intervention_session_number) "
        "FROM t3_panel p JOIN t3_demo_learner_map d ON d.learner_id = p.student_id "
        "GROUP BY d.research_student_id"
    )
    if not rows:
        pytest.skip("demo database carries no panel rows")

    offenders = [
        (sid, int(latest), recorded_assignment[sid])
        for sid, latest in rows
        if sid in recorded_assignment and int(latest) > recorded_assignment[sid]
    ]
    assert not offenders, f"sessions served beyond the assigned t: {offenders[:5]}"


@demo_db
def test_no_prediction_exceeds_the_assigned_t(recorded_assignment) -> None:
    rows = _query(
        "SELECT d.research_student_id, p.t FROM t3_predictions p "
        "JOIN t3_demo_learner_map d ON d.learner_id = p.student_id"
    )
    if not rows:
        pytest.skip("demo database carries no predictions")

    offenders = [
        (sid, int(t), recorded_assignment[sid])
        for sid, t in rows
        if sid in recorded_assignment and int(t) > recorded_assignment[sid]
    ]
    assert not offenders, f"predictions served beyond the assigned t: {offenders[:5]}"


@demo_db
def test_sessions_completed_equals_the_snapshot_index() -> None:
    """`sessions_completed == t` on every prediction row.

    True on the un-staggered build and it must stay true: the warm-up floor (D6) is evaluated
    against `sessions_completed`, so a learner whose count disagreed with their snapshot index
    could be shown as past the floor while their history says otherwise.
    """

    rows = _query(
        "SELECT COUNT(*) FROM t3_predictions WHERE sessions_completed IS DISTINCT FROM t"
    )
    assert rows[0][0] == 0
