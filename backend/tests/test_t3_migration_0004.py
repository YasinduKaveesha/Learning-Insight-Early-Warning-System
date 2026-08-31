"""Structural guards on the B3.4 migration source (work order B3.4).

`ast`-parsed, standard library only, so this runs in the pinned `c3-ews` env (no SQLAlchemy,
no database driver). It checks the DDL Alembic will execute -- stronger than a model-only
check, which still passes if a constraint is weakened in a hand-written migration. The
live-schema equivalents are in `test_t3_predictions_live.py` and skip without a database.

The two traps this is built to catch:

* `ck_t3_predictions_watch_flag` MUST use `COALESCE(predicted_class, -1)`, not a bare
  `predicted_class >= 1` (which PostgreSQL passes when `predicted_class` is NULL).
* the unsatisfiable `CHECK ((risk_level IS NULL) = (evidence_status <> 'sufficient_evidence'))`
  MUST NOT be present.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0004_predictions_model_versions.py"
)

_FORBIDDEN_COLUMNS = {"population", "dd_subtype"}


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


def _first_str(call: ast.Call) -> str:
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
    return ""


def _column_names(create_table: ast.Call) -> list[str]:
    return [_first_str(c) for c in _sub_calls(create_table, "Column")]


def _check_texts(create_table: ast.Call) -> list[str]:
    return [_first_str(c) for c in _sub_calls(create_table, "CheckConstraint")]


def _pk_columns(create_table: ast.Call) -> list[str]:
    for c in _sub_calls(create_table, "PrimaryKeyConstraint"):
        return [a.value for a in c.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return []


@pytest.fixture(scope="module")
def tables() -> dict[str, ast.Call]:
    calls = _create_table_calls()
    assert set(calls) == {"t3_predictions", "t3_model_versions"}, sorted(calls)
    return calls


# --- the watch-flag trap ---------------------------------------------------------------

def test_watch_flag_check_uses_coalesce_not_bare_comparison(tables: dict[str, ast.Call]) -> None:
    checks = _check_texts(tables["t3_predictions"])
    watch = [t for t in checks if "watch_flag" in t and "predicted_class" in t]
    assert len(watch) == 1, watch
    text = watch[0]
    assert "COALESCE(predicted_class, -1)" in text, (
        f"watch_flag CHECK is the bare form -- NULL predicted_class rows escape it: {text!r}"
    )
    assert "sessions_completed >= 3" in text


def test_unsatisfiable_risk_level_check_is_absent(tables: dict[str, ast.Call]) -> None:
    joined = " ".join(_check_texts(tables["t3_predictions"]))
    assert "evidence_status <>" not in joined and "(risk_level IS NULL) =" not in joined, (
        "the unsatisfiable risk_level/evidence_status CHECK has been reinstated"
    )


# --- the other four constraints -------------------------------------------------------

def test_no_high_tier_check(tables: dict[str, ast.Call]) -> None:
    joined = " ".join(_check_texts(tables["t3_predictions"]))
    assert "risk_level IS NULL OR risk_level IN ('Low', 'Moderate')" in joined
    assert "'High'" not in joined


def test_evidence_and_trajectory_enums(tables: dict[str, ast.Call]) -> None:
    joined = " ".join(_check_texts(tables["t3_predictions"]))
    for value in (
        "sufficient_evidence",
        "insufficient_exposure",
        "insufficient_future_evidence",
        "censored_by_observation_end",
        "administratively_missing",
    ):
        assert f"'{value}'" in joined, value
    assert "practice_trajectory IN ('improving', 'stable', 'needs_attention', 'unknown')" in joined
    assert "engagement_trajectory IN ('improving', 'stable', 'needs_attention', 'unknown')" in joined


def test_predictions_primary_key_and_index(tables: dict[str, ast.Call]) -> None:
    assert _pk_columns(tables["t3_predictions"]) == [
        "student_id",
        "t",
        "model_version",
        "pipeline_run_id",
    ]
    indexes = [_first_str(c) for c in _calls("create_index")]
    assert "ix_t3_predictions_latest" in indexes


def test_server_only_columns_present_and_nullable(tables: dict[str, ast.Call]) -> None:
    cols = _column_names(tables["t3_predictions"])
    for name in ("prob_class_0", "prob_class_1", "prob_class_2plus", "predicted_class"):
        assert name in cols, name


def test_no_audit_label_columns(tables: dict[str, ast.Call]) -> None:
    for name, call in tables.items():
        cols = set(_column_names(call))
        assert _FORBIDDEN_COLUMNS.isdisjoint(cols), (name, sorted(_FORBIDDEN_COLUMNS & cols))


# --- the seed row --------------------------------------------------------------------

def test_migration_seeds_the_one_model_version() -> None:
    inserts = _calls("bulk_insert")
    assert len(inserts) == 1, "expected exactly one op.bulk_insert (the model-card seed row)"
    source = _MIGRATION.read_text(encoding="utf-8")
    assert '"model_version": "1.0.0"' in source
    assert "019f000be16f533630b6e5d3215bf86597745a725cb13c5b989d03f45769db15" in source
    assert '"sklearn_version": "1.9.0"' in source
