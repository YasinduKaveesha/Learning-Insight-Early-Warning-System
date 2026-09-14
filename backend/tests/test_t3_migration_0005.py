"""Structural guards on the B4 migration source (work order B4, gate 1 half).

`ast`-parsed, standard library only -- runs in the pinned `c3-ews` env (no SQLAlchemy, no
driver). It checks the DDL Alembic will execute: exactly five additive, nullable columns on
`t3_panel`, the primary key untouched, and none of the other ~15 Component C detail fields.
The live-schema equivalent skips without a database.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0005_panel_source_ids_c_guards.py"
)

_EXPECTED = {
    "intervention_session_id",
    "b_session_id",
    "c_session_id",
    "c_session_technical_issue_flag",
    "c_inactive_time_sec",
}

# Deliberately NOT added by this work order -- they stay recoverable by re-running the loader.
_MUST_NOT_ADD = {
    "c_policy_version",
    "c_composite_formula_version",
    "c_state_rule_version",
    "c_time_in_target_band_sec",
    "c_session_duration_sec",
    "c_consecutive_error_max",
    "c_total_attempt_count",
    "b_session_technical_issue_flag",
    "population",
    "dd_subtype",
}


def _tree() -> ast.Module:
    return ast.parse(_MIGRATION.read_text(encoding="utf-8"), str(_MIGRATION))


def _calls(attr: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(_tree())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attr
    ]


def _func_body(name: str) -> list[ast.stmt]:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.body
    raise AssertionError(f"no {name}() in the migration")


def _op_calls_in(name: str, attr: str) -> list[ast.Call]:
    out: list[ast.Call] = []
    for stmt in _func_body(name):
        for n in ast.walk(stmt):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == attr
            ):
                out.append(n)
    return out


def _added_column(call: ast.Call) -> tuple[str, str, bool]:
    """(table, column_name, nullable) for an `op.add_column(table, sa.Column(...))` call."""

    table = call.args[0].value
    col = call.args[1]
    col_name = next(a.value for a in col.args if isinstance(a, ast.Constant))
    nullable = True
    for kw in col.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable = kw.value.value
    return table, col_name, nullable


def test_revision_chain_and_id_length():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0005_panel_source_ids_c_guards"' in src
    assert 'down_revision: Union[str, Sequence[str], None] = "0004_predictions_model_versions"' in src
    assert len("0005_panel_source_ids_c_guards") <= 32


def test_upgrade_adds_exactly_the_five_columns_all_nullable_on_t3_panel():
    adds = [_added_column(c) for c in _op_calls_in("upgrade", "add_column")]
    assert {name for _, name, _ in adds} == _EXPECTED
    for table, name, nullable in adds:
        assert table == "t3_panel", (name, table)
        assert nullable is True, f"{name} must be nullable"


def test_upgrade_does_not_add_other_c_detail_fields():
    src = _MIGRATION.read_text(encoding="utf-8")
    for forbidden in _MUST_NOT_ADD:
        assert f'"{forbidden}"' not in src, forbidden


def test_primary_key_is_not_touched():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "PrimaryKeyConstraint" not in src
    assert "drop_constraint" not in src and "create_primary_key" not in src
    # no column is dropped or created-table in upgrade
    assert _op_calls_in("upgrade", "drop_column") == []
    assert _op_calls_in("upgrade", "create_table") == []


def test_downgrade_drops_exactly_the_five_columns():
    drops = {
        c.args[1].value
        for c in _op_calls_in("downgrade", "drop_column")
        if len(c.args) >= 2 and isinstance(c.args[1], ast.Constant)
    }
    assert drops == _EXPECTED
