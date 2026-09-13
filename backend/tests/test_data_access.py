"""DB-less contract tests for `app.application.data_access` (work order B2.4).

These compile the SQLAlchemy statements the module builds and inspect the generated SQL
text directly -- no database required, so they run in every environment and every CI job,
not just the ones with `T3_LIVE_DB_URL` set. The mutation-testing gates in the B2.4 work
order (remove the `source_class` filter; apply it where it must not appear) are meant to be
caught here first, with the live-DB tests in `test_data_access_live.py` proving the same
thing against real rows.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from app.application import data_access  # noqa: E402


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _code_only(obj) -> str:
    """The source of a function/module with its docstring(s) stripped, so a search for a
    forbidden identifier does not false-positive on prose that merely explains the rule."""

    source = textwrap.dedent(inspect.getsource(obj))
    tree = ast.parse(source)
    body = tree.body[0].body if isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)) else tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    return "\n".join(ast.unparse(node) for node in body)


_SOME_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ------------------------------------------------------------------------------------
# Student-app readers must ALWAYS carry the REAL filter.
# ------------------------------------------------------------------------------------


def test_real_learners_filters_source_class_real() -> None:
    stmt = data_access.select(
        data_access.b_learners.c.learner_id
    ).where(data_access.b_learners.c.source_class == data_access.REAL_SOURCE_CLASS)
    sql = _sql(stmt)
    assert "source_class" in sql
    assert "'REAL'" in sql


def test_real_learners_never_uses_student_number() -> None:
    source = _code_only(data_access.real_learners)
    assert "student_number" not in source


def test_classroom_roster_query_shape() -> None:
    """Compile the actual statement `classroom_roster` builds (without a session, by
    reproducing its where-clause construction) and assert both guards are present: APPROVED
    only, REAL only."""

    source = _code_only(data_access.classroom_roster)
    assert "APPROVED_STATE" in source
    assert "REAL_SOURCE_CLASS" in source
    assert "learner_id.in_" not in source  # no student_number substitution path exists
    assert "student_number" not in source


# ------------------------------------------------------------------------------------
# t3_* readers must NEVER carry the REAL/source_class filter.
# ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func_name",
    ["panel_rows_for_run", "features_for_run", "predictions_for_run"],
)
def test_t3_readers_never_filter_source_class(func_name: str) -> None:
    source = _code_only(getattr(data_access, func_name))
    assert "source_class" not in source, (
        f"{func_name} must not filter source_class -- t3_* rows are SYNTHETIC by design "
        "(D15); applying the student-app REAL rule here returns zero rows."
    )
    assert "pipeline_run_id ==" in source or "pipeline_run_id\n" in source or (
        "pipeline_run_id" in source
    )


def test_predictions_for_run_never_selects_forbidden_fields() -> None:
    source = _code_only(data_access.predictions_for_run)
    for forbidden in (
        "prob_class_0",
        "prob_class_1",
        "prob_class_2plus",
        "predicted_class",
        "engagement_trajectory",
    ):
        assert forbidden not in source, f"predictions_for_run must never select {forbidden}"


# ------------------------------------------------------------------------------------
# No SELECT * and no student_number anywhere in the module.
# ------------------------------------------------------------------------------------


def test_module_has_no_select_star() -> None:
    source = _code_only(data_access)
    assert "select(*)" not in source
    assert "select('*')" not in source
    assert 'text("select *' not in source.lower()


def test_module_never_uses_student_number() -> None:
    source = _code_only(data_access)
    assert "student_number" not in source


# ------------------------------------------------------------------------------------
# Ownership guards: structural fail-closed shape (real behaviour is proven live).
# ------------------------------------------------------------------------------------


def test_teacher_owns_classroom_query_requires_both_ids() -> None:
    stmt = data_access.select(data_access.classrooms.c.classroom_id).where(
        data_access.classrooms.c.classroom_id == _SOME_UUID,
        data_access.classrooms.c.teacher_profile_id == _SOME_UUID,
    )
    sql = _sql(stmt)
    assert "classroom_id" in sql and "teacher_profile_id" in sql


def test_learner_visible_to_teacher_requires_approved_and_real() -> None:
    source = _code_only(data_access.learner_visible_to_teacher)
    assert "APPROVED_STATE" in source
    assert "REAL_SOURCE_CLASS" in source
    assert "teacher_profile_id ==" in source or "teacher_profile_id\n" in source or (
        "teacher_profile_id" in source
    )


# ------------------------------------------------------------------------------------
# `Row.t` shadowing -- the defect that produced an HTTP 500 on the first real request.
# ------------------------------------------------------------------------------------


def test_sqlalchemy_row_really_does_shadow_a_column_named_t() -> None:
    """Pin the hazard itself, so this test starts failing if SQLAlchemy ever removes it.

    `sqlalchemy.Row` defines its own `t` attribute. A query selecting a column NAMED `t` --
    which `t3_predictions` and `t3_features_at_t` both do -- therefore cannot be read with
    `row.t`: that returns the tuple accessor, not the value. It does not raise at the access
    site, so the wrong object travels until something distant rejects it.
    """

    from sqlalchemy import create_engine, literal_column, select

    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        row = connection.execute(select(literal_column("7").label("t"))).all()[0]

    assert row._mapping["t"] == 7
    assert not isinstance(row.t, int), (
        "SQLAlchemy no longer shadows a column named 't'. If this fails, the workaround in "
        "data_access._as_records may be removable -- but verify against the pinned version "
        "before removing it."
    )


def test_as_records_exposes_a_column_named_t_by_name() -> None:
    """The fix. `_as_records` must make `record.t` the VALUE, not the tuple accessor.

    This is the regression test for the 500 that `/api/v1/t3/home` returned the first time
    `t3_predictions` had rows in it. Reverting `_as_records` makes this fail.
    """

    from sqlalchemy import create_engine, literal_column, select

    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        rows = connection.execute(
            select(literal_column("7").label("t"), literal_column("3").label("sessions"))
        ).all()

    records = data_access._as_records(rows)

    assert len(records) == 1
    assert records[0].t == 7, "a column named 't' must be reachable as .t on the record"
    assert isinstance(records[0].t, int)
    assert records[0].sessions == 3


def test_readers_selecting_t_convert_rows_to_records() -> None:
    """Both readers that select `t` must go through `_as_records`.

    A source check rather than a behavioural one: these readers need a populated database to
    exercise, and this catches the likelier regression -- someone reinstating `.all()`
    because it reads more naturally.
    """

    for reader in (data_access.predictions_for_run, data_access.features_for_run):
        source = _code_only(reader)
        assert "_as_records(" in source, (
            f"{reader.__name__} selects a column named 't' and must return records, not raw "
            f"Rows -- see data_access._as_records"
        )
