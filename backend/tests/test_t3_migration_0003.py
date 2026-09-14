"""Structural guards on the B3.3 migration source itself (work order B3.3, gates 5 and 6).

These parse `migrations/versions/0003_panel_and_features.py` with `ast` -- standard library
only, so they run in the pinned `c3-ews` env, which has no SQLAlchemy or database driver.
They check the DDL that Alembic will actually execute, which is stronger than a model-only
check: a model-only assertion still passes if a column is slipped in via a hand-written
migration. The live-schema equivalents (which also cover a hand-migration path) are in
`test_t3_live_schema.py` and skip when no database is configured.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0003_panel_and_features.py"
)

# The prior build collapsed Component B and Component C into shared columns when B's value
# won a name collision (plan section 4.3). Any measure of this shape must stay prefixed.
_COLLISION_PRONE = re.compile(r"accuracy|response_time|latency|duration", re.IGNORECASE)

_FORBIDDEN_COLUMNS = {"population", "dd_subtype"}


def _create_table_calls() -> dict[str, ast.Call]:
    tree = ast.parse(_MIGRATION.read_text(encoding="utf-8"), str(_MIGRATION))
    calls: dict[str, ast.Call] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "create_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            calls[node.args[0].value] = node
    return calls


def _string_args(call: ast.Call) -> list[str]:
    return [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def _column_names(create_table: ast.Call) -> list[str]:
    names: list[str] = []
    for arg in create_table.args[1:]:
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "Column"
            and arg.args
            and isinstance(arg.args[0], ast.Constant)
        ):
            names.append(arg.args[0].value)
    return names


def _primary_key_columns(create_table: ast.Call) -> list[str]:
    for arg in create_table.args[1:]:
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "PrimaryKeyConstraint"
        ):
            return _string_args(arg)
    return []


@pytest.fixture(scope="module")
def tables() -> dict[str, ast.Call]:
    calls = _create_table_calls()
    assert set(calls) == {"t3_panel", "t3_features_at_t"}, sorted(calls)
    return calls


def test_gate5_panel_bc_measures_keep_their_prefix(tables: dict[str, ast.Call]) -> None:
    offenders = [
        name
        for name in _column_names(tables["t3_panel"])
        if _COLLISION_PRONE.search(name) and not name.startswith(("b_", "c_"))
    ]
    assert offenders == [], f"unprefixed B/C-collision-prone columns on t3_panel: {offenders}"


def test_gate6_features_primary_key_contains_t(tables: dict[str, ast.Call]) -> None:
    pk = _primary_key_columns(tables["t3_features_at_t"])
    assert "t" in pk, f"t3_features_at_t PK does not contain 't' (one row per student?): {pk}"
    assert pk == ["student_id", "t", "feature_version", "pipeline_run_id"], pk


def test_no_audit_label_columns_in_either_table(tables: dict[str, ast.Call]) -> None:
    for table_name, call in tables.items():
        cols = set(_column_names(call))
        assert _FORBIDDEN_COLUMNS.isdisjoint(cols), (
            f"{table_name} declares an audit-only label column: "
            f"{sorted(_FORBIDDEN_COLUMNS & cols)}"
        )


def test_panel_primary_key_is_learner_session_run(tables: dict[str, ast.Call]) -> None:
    assert _primary_key_columns(tables["t3_panel"]) == [
        "student_id",
        "intervention_session_number",
        "pipeline_run_id",
    ]
