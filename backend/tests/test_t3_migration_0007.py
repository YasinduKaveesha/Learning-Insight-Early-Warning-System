"""Structural guards on the B4.1 migration source (work order B4.1).

`ast`-parsed, standard library only, so this runs in the pinned `c3-ews` env without a
database or SQLAlchemy. Mirrors the technique in `test_t3_migration_0006.py`. Checks the DDL
Alembic will actually execute -- both uniqueness directions and the format CHECK are
load-bearing (a many-to-one mapping in either direction could misattribute a child's
analytics), so this asserts on the migration source, not just the ORM model.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0007_demo_learner_map.py"
)


def _module() -> ast.Module:
    return ast.parse(_MIGRATION.read_text(encoding="utf-8"), str(_MIGRATION))


def _calls(attr: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(_module())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
    ]


def _create_table_calls() -> dict[str, ast.Call]:
    return {
        c.args[0].value: c
        for c in _calls("create_table")
        if c.args and isinstance(c.args[0], ast.Constant)
    }


def _sub_calls(call: ast.Call, attr: str) -> list[ast.Call]:
    return [
        a
        for a in call.args[1:]
        if isinstance(a, ast.Call)
        and isinstance(a.func, ast.Attribute)
        and a.func.attr == attr
    ]


def _column_names(create_table: ast.Call) -> list[str]:
    out = []
    for c in _sub_calls(create_table, "Column"):
        for a in c.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append(a.value)
                break
    return out


def _check_predicates(create_table: ast.Call) -> list[str]:
    out = []
    for c in _sub_calls(create_table, "CheckConstraint"):
        for a in c.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append(a.value)
                break
    return out


@pytest.fixture(scope="module")
def table() -> ast.Call:
    calls = _create_table_calls()
    assert set(calls) == {"t3_demo_learner_map"}, sorted(calls)
    return calls["t3_demo_learner_map"]


def test_revision_chain_and_id_length() -> None:
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0007_demo_learner_map"' in src
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0006_recommendations"' in src
    )
    assert len("0007_demo_learner_map") <= 32


def test_columns_present(table: ast.Call) -> None:
    cols = set(_column_names(table))
    expected = {
        "learner_id",
        "research_student_id",
        "created_at_utc",
        "updated_at_utc",
        "source_class",
        "source_system",
        "parameter_source_status",
        "pipeline_run_id",
    }
    assert expected <= cols, sorted(expected - cols)


def test_format_check_present(table: ast.Call) -> None:
    predicates = _check_predicates(table)
    assert any("research_student_id ~" in p and "STU-" in p for p in predicates), predicates


def test_learner_id_is_primary_key(table: ast.Call) -> None:
    (pk,) = _sub_calls(table, "PrimaryKeyConstraint")
    names = [a.value for a in pk.args if isinstance(a, ast.Constant)]
    assert names == ["learner_id"], names


def test_research_student_id_has_unique_constraint(table: ast.Call) -> None:
    uniques = _sub_calls(table, "UniqueConstraint")
    assert any(
        any(
            isinstance(a, ast.Constant) and a.value == "research_student_id"
            for a in u.args
        )
        for u in uniques
    ), "no UniqueConstraint on research_student_id"


def test_foreign_key_targets_b_learners_with_restrict(table: ast.Call) -> None:
    (fk,) = _sub_calls(table, "ForeignKeyConstraint")
    joined = ast.dump(fk)
    assert "b_learners.learner_id" in joined
    for kw in fk.keywords:
        if kw.arg == "ondelete":
            assert kw.value.value == "RESTRICT"


def test_downgrade_drops_the_table() -> None:
    src = _MIGRATION.read_text(encoding="utf-8")
    body = src.split("def downgrade()", 1)[1]
    assert "drop_table" in body
    assert "t3_demo_learner_map" in body
