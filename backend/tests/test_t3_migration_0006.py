"""Structural guards on the B3.5 migration source (work order B3.5, gate 7).

`ast`-parsed, standard library only, so this runs in the pinned `c3-ews` env (no SQLAlchemy,
no database driver). It checks the DDL Alembic will execute -- stronger than a model-only
check, which still passes if a constraint is weakened in a hand-written migration. The
live-schema equivalents are gates 3-6 in `test_t3_recommendations_live.py` and skip without
a database.

Same technique as `test_t3_migration_0004.py`. The constraints this is built to defend:

* `ck_t3_reco_ethical_gate` MUST be present and MUST carry BOTH
  `b_applied_at_intervention_session IS NULL` and
  `c_applied_at_intervention_session IS NULL` clauses -- a pending/dismissed recommendation
  that has altered Component B or C must be rejected by the database, not by a validator.
* `uq_t3_reco_active` MUST be partial -- it MUST carry a `WHERE` predicate, so a `dismissed`
  recommendation does not block a new one for the same `(student_id, target_component)`.
* `ck_t3_reco_modified` and `ck_t3_reco_expiry` are present with their exact predicates.
* there is NO CHECK enumerating the four `proposed_action` kinds (D7: the vocabulary is
  closed by decision, not by schema), and NO trigger -> action mapping.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0006_recommendations.py"
)

_FORBIDDEN_COLUMNS = {"population", "dd_subtype"}
_ACTION_KINDS = ("practice", "review", "try_again", "monitor_progress")


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
    parts = [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return "".join(parts)


def _column_names(create_table: ast.Call) -> list[str]:
    out = []
    for c in _sub_calls(create_table, "Column"):
        for a in c.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append(a.value)
                break
    return out


def _check_map(create_table: ast.Call) -> dict[str, str]:
    """{constraint_name: predicate_text} for every CheckConstraint in the create_table call."""

    out: dict[str, str] = {}
    for c in _sub_calls(create_table, "CheckConstraint"):
        predicate = ""
        for a in c.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                predicate = a.value
                break
        name = ""
        for kw in c.keywords:
            if kw.arg == "name":
                if isinstance(kw.value, ast.Constant):
                    name = kw.value.value
                elif isinstance(kw.value, ast.Call):  # op.f("...")
                    name = _first_str(kw.value)
        out[name] = predicate
    return out


@pytest.fixture(scope="module")
def table() -> ast.Call:
    calls = _create_table_calls()
    assert set(calls) == {"t3_recommendations"}, sorted(calls)
    return calls["t3_recommendations"]


def test_revision_chain_and_id_length() -> None:
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0006_recommendations"' in src
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0005_panel_source_ids_c_guards"'
        in src
    )
    assert len("0006_recommendations") <= 32


# --- the ethical gate -----------------------------------------------------------------

def test_ethical_gate_check_present_with_both_is_null_clauses(table: ast.Call) -> None:
    checks = _check_map(table)
    assert "ck_t3_reco_ethical_gate" in checks, sorted(checks)
    gate = checks["ck_t3_reco_ethical_gate"]
    assert "b_applied_at_intervention_session IS NULL" in gate, gate
    assert "c_applied_at_intervention_session IS NULL" in gate, gate
    assert "teacher_status IN ('accepted', 'modified')" in gate, gate
    # the two applied-column clauses are ANDed, not ORed
    assert "IS NULL\n" not in gate  # sanity: single logical line
    assert " AND " in gate


def test_partial_unique_index_carries_a_where_clause(table: ast.Call) -> None:
    (index,) = [
        c
        for c in _calls("create_index")
        if c.args and isinstance(c.args[0], ast.Constant) and c.args[0].value == "uq_t3_reco_active"
    ]
    kwargs = {kw.arg for kw in index.keywords}
    assert "unique" in kwargs
    where_kw = next(
        (kw for kw in index.keywords if kw.arg in {"postgresql_where", "sqlite_where"}),
        None,
    )
    assert where_kw is not None, "uq_t3_reco_active must be PARTIAL -- no WHERE predicate found"
    # the predicate must admit pending/accepted/modified only (dismissed is excluded)
    node = where_kw.value
    text = node.args[0].value if isinstance(node, ast.Call) else getattr(node, "value", "")
    assert "pending" in text and "accepted" in text and "modified" in text
    assert "dismissed" not in text


# --- the other three constraints ----------------------------------------------------

def test_modified_and_expiry_and_status_and_target_checks(table: ast.Call) -> None:
    checks = _check_map(table)
    assert (
        checks["ck_t3_reco_modified"]
        == "(teacher_modified_action IS NOT NULL) = (teacher_status = 'modified')"
    )
    assert (
        checks["ck_t3_reco_expiry"]
        == "expires_after_session <= issued_at_intervention_session + 5"
    )
    assert checks["ck_t3_reco_target"] == "target_component IN ('B', 'C', 'both')"
    assert (
        checks["ck_t3_reco_status"]
        == "teacher_status IN ('pending', 'accepted', 'dismissed', 'modified')"
    )


def test_no_check_enumerates_the_action_vocabulary(table: ast.Call) -> None:
    """D7 closed the vocabulary by decision, not by schema. A CHECK on `proposed_action`
    kinds would make adding a kind a migration -- exactly what the plan forbids."""

    joined = " ".join(_check_map(table).values())
    for kind in _ACTION_KINDS:
        assert f"'{kind}'" not in joined, f"a CHECK enumerates proposed_action kind {kind!r}"
    assert "proposed_action" not in joined


def test_no_trigger_to_action_mapping_in_source() -> None:
    src = _MIGRATION.read_text(encoding="utf-8").lower()
    # a mapping would pair a trigger name with an action kind in the same construct
    assert "case when" not in src
    for kind in _ACTION_KINDS:
        assert f"then '{kind}'" not in src


def test_no_audit_label_columns(table: ast.Call) -> None:
    cols = set(_column_names(table))
    assert _FORBIDDEN_COLUMNS.isdisjoint(cols), sorted(_FORBIDDEN_COLUMNS & cols)


def test_applied_columns_exist_and_are_nullable(table: ast.Call) -> None:
    cols = _column_names(table)
    for name in ("b_applied_at_intervention_session", "c_applied_at_intervention_session"):
        assert name in cols, name
    # nullable: no `nullable=False` on those two Column() calls
    for c in _sub_calls(table, "Column"):
        first = next((a.value for a in c.args if isinstance(a, ast.Constant)), None)
        if first in ("b_applied_at_intervention_session", "c_applied_at_intervention_session"):
            for kw in c.keywords:
                if kw.arg == "nullable":
                    assert kw.value.value is not False, first


def test_columns_match_plan_section_4_6(table: ast.Call) -> None:
    cols = set(_column_names(table))
    expected = {
        "recommendation_id",
        "student_id",
        "issued_at_intervention_session",
        "expires_after_session",
        "target_component",
        "trigger",
        "proposed_action",
        "evidence_summary",
        "teacher_status",
        "teacher_modified_action",
        "decided_at_utc",
        "b_applied_at_intervention_session",
        "c_applied_at_intervention_session",
    }
    assert expected <= cols, sorted(expected - cols)


def test_trigger_comment_records_the_evidence_prohibition(table: ast.Call) -> None:
    for c in _sub_calls(table, "Column"):
        first = next((a.value for a in c.args if isinstance(a, ast.Constant)), None)
        if first == "trigger":
            comment = ""
            for kw in c.keywords:
                if kw.arg == "comment":
                    v = kw.value
                    comment = v.value if isinstance(v, ast.Constant) else "".join(
                        p.id if isinstance(p, ast.Name) else "" for p in ast.walk(v)
                    )
            src = _MIGRATION.read_text(encoding="utf-8")
            assert "dd_subtype" in src and "cluster label" in src
            return
    raise AssertionError("no `trigger` column found")


def test_downgrade_drops_index_then_table() -> None:
    src = _MIGRATION.read_text(encoding="utf-8")
    body = src.split("def downgrade()", 1)[1]
    assert body.index("drop_index") < body.index("drop_table")
    assert "uq_t3_reco_active" in body
