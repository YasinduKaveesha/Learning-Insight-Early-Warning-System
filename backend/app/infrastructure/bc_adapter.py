"""The B/C adapter -- the ONE place in the codebase that reads either data source.

Work order B4. In v1 (decision D15) the analytics path is fed by the research dataset:
``dataset/source/so2_joined_dataset_seed20260828_n300.jsonl`` -- 7,500 records, 300 learners
x sessions 1-25, each record carrying ``mapping``, ``b_to_3`` and ``c_to_3``. When the live
contract layer arrives (Components B and C shipping session-number allocation) there must be
exactly ONE file to repoint: this one. Do not scatter payload reads through services.

Responsibilities, and nothing else:

* read the payloads;
* map them to the ``t3_panel`` shape with the ``b_`` / ``c_`` prefixes preserved;
* record ``b_present`` / ``c_present``.

NOT here: feature engineering (that is ``app/infrastructure/feature_builder.py``), learner
resolution, provenance stamping or any database write (that is ``app/application/t3_loader``).

Rules that are not optional (backend_plan.md section 5.1, work order B4):

* **The ``b_`` / ``c_`` prefixes are mandatory.** Both payloads carry ``accuracy_rate`` and
  both carry a timing measure. A previous build collapsed them when Component B's value won
  a column collision. ``b_to_3.accuracy_rate`` -> ``b_accuracy_rate``;
  ``c_to_3.accuracy_rate`` -> ``c_accuracy_rate``. Never one field.
* **A null is never a zero.** ``b_to_3.mastery_slope_w4`` is ``None`` for early sessions;
  it stays ``None``. A censored slope is not a flat slope.
* **Do not derive a session ordinal.** The source provides ``intervention_session_number``
  -- it is used verbatim. Never ``ROW_NUMBER() OVER (ORDER BY created_at_utc)`` (D9).
* **Never open ``dataset/audit/``.** ``t3_audit_labels_*.csv`` carries ``population`` and
  ``dd_subtype``; rule 3-F1 keeps them out of this database. This module does not know that
  directory exists -- it maps a fixed whitelist of keys, so ``population`` / ``dd_subtype``
  cannot appear in the output even if a future source file carried them.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

__all__ = [
    "SKILLS",
    "PANEL_FIELDS",
    "read_source",
    "read_manifest",
    "map_record",
    "load_panel_records",
]

#: The seven skills, in the order docs/06 lists them. ``b_to_3`` carries them as flat
#: ``mastery_<skill>`` floats; the panel folds them into the ``b_mastery`` jsonb keyed by
#: skill name (same treatment for ``mastery_certified``, ``mastery_slope_w4``,
#: ``opportunities_w4`` and ``error_class_dist``, which the source already delivers as maps).
SKILLS: tuple[str, ...] = (
    "counting",
    "number_sense",
    "place_value",
    "addition",
    "subtraction",
    "multiplication",
    "division",
)

#: Every key a mapped record may contain. Exactly the ``t3_panel`` business columns (no
#: provenance -- the loader adds that). Anything not in here is dropped, by construction.
PANEL_FIELDS: frozenset[str] = frozenset(
    {
        "student_id",
        "intervention_session_number",
        "intervention_session_date",
        "intervention_session_id",
        "b_session_id",
        "c_session_id",
        "b_present",
        "c_present",
        # Component B, all b_-prefixed.
        "b_accuracy_rate",
        "b_total_questions",
        "b_correct_responses",
        "b_hint_requests",
        "b_median_item_response_time_sec",
        "b_item_response_time_std_sec",
        "b_mastery",
        "b_mastery_certified",
        "b_mastery_slope_w4",
        "b_opportunities_w4",
        "b_error_class_dist",
        # Component C, all c_-prefixed.
        "c_accuracy_rate",
        "c_task_completion_rate",
        "c_median_game_task_latency_sec",
        "c_difficulty_floor_hits",
        "c_engagement_score",
        "c_engagement_components",
        "c_frustration_index",
        "c_frustration_components",
        "c_learner_state",
        "c_state_reason",
        "c_telemetry_quality_status",
        "c_current_difficulty_level",
        "c_difficulty_trend",
        "c_session_technical_issue_flag",
        "c_inactive_time_sec",
    }
)

#: Audit-only labels. They have no meaning for a real learner (rule 3-F1) and must never
#: enter this database. The adapter can only emit ``PANEL_FIELDS``, so they cannot appear in
#: a mapped record -- ``load_panel_records`` asserts that anyway, as a tripwire.
_FORBIDDEN_KEYS: frozenset[str] = frozenset({"population", "dd_subtype"})


def read_manifest(path: str | Path) -> dict[str, Any]:
    """Return the dataset manifest JSON (``so2_manifest_*.json``) as a dict.

    The loader stores this verbatim in ``t3_pipeline_runs.dataset_manifest``.
    """

    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_source(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield one raw record per non-blank line of the joined dataset (``*.jsonl``).

    Streamed rather than read whole -- the file is ~26 MB / 7,500 lines.
    """

    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _map_b(b: dict[str, Any]) -> dict[str, Any]:
    """Component B payload -> the ``b_``-prefixed panel columns.

    ``mastery_slope_w4`` values that are ``None`` in the source stay ``None`` here.
    """

    return {
        "b_accuracy_rate": b.get("accuracy_rate"),
        "b_total_questions": b.get("total_questions"),
        "b_correct_responses": b.get("correct_responses"),
        "b_hint_requests": b.get("hint_requests"),
        "b_median_item_response_time_sec": b.get("b_median_item_response_time_sec"),
        "b_item_response_time_std_sec": b.get("b_item_response_time_std_sec"),
        # The seven flat mastery_<skill> floats fold into one jsonb keyed by skill name.
        "b_mastery": {skill: b.get(f"mastery_{skill}") for skill in SKILLS},
        "b_mastery_certified": b.get("mastery_certified"),
        "b_mastery_slope_w4": b.get("mastery_slope_w4"),
        "b_opportunities_w4": b.get("opportunities_w4"),
        "b_error_class_dist": b.get("error_class_dist"),
    }


def _map_c(c: dict[str, Any]) -> dict[str, Any]:
    """Component C payload -> the ``c_``-prefixed panel columns.

    ``c_to_3.accuracy_rate`` lands in ``c_accuracy_rate`` -- never merged with the Component
    B accuracy, never merged with any timing measure (rule 3-F9).
    """

    return {
        "c_accuracy_rate": c.get("accuracy_rate"),
        "c_task_completion_rate": c.get("task_completion_rate"),
        "c_median_game_task_latency_sec": c.get("c_median_game_task_latency_sec"),
        "c_difficulty_floor_hits": c.get("difficulty_floor_hits"),
        "c_engagement_score": c.get("engagement_score"),
        "c_engagement_components": c.get("engagement_components"),
        "c_frustration_index": c.get("frustration_index"),
        "c_frustration_components": c.get("frustration_components"),
        "c_learner_state": c.get("learner_state"),
        "c_state_reason": c.get("state_reason"),
        "c_telemetry_quality_status": c.get("telemetry_quality_status"),
        "c_current_difficulty_level": c.get("current_difficulty_level"),
        "c_difficulty_trend": c.get("difficulty_trend"),
        # Migration 0005 -- the two safety guards.
        "c_session_technical_issue_flag": c.get("session_technical_issue_flag"),
        "c_inactive_time_sec": c.get("inactive_time_sec"),
    }


_B_COLUMNS: tuple[str, ...] = tuple(_map_b({}).keys())
_C_COLUMNS: tuple[str, ...] = tuple(_map_c({}).keys())


def map_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Map one raw joined-dataset record to the ``t3_panel`` shape.

    Keys of the result are a subset of :data:`PANEL_FIELDS`, always. The session number is
    read straight from ``mapping.intervention_session_number`` -- never derived.
    """

    mapping = raw["mapping"]
    b_present = bool(mapping["b_present"])
    c_present = bool(mapping["c_present"])

    record: dict[str, Any] = {
        "student_id": mapping["student_id"],
        "intervention_session_number": mapping["intervention_session_number"],
        "intervention_session_date": _parse_date(mapping["intervention_session_date"]),
        "intervention_session_id": mapping.get("intervention_session_id"),
        "b_session_id": mapping.get("b_session_id"),
        "c_session_id": mapping.get("c_session_id"),
        "b_present": b_present,
        "c_present": c_present,
    }

    if b_present and raw.get("b_to_3") is not None:
        record.update(_map_b(raw["b_to_3"]))
    else:
        record.update({col: None for col in _B_COLUMNS})

    if c_present and raw.get("c_to_3") is not None:
        record.update(_map_c(raw["c_to_3"]))
    else:
        record.update({col: None for col in _C_COLUMNS})

    return record


def load_panel_records(source_path: str | Path) -> list[dict[str, Any]]:
    """Read the joined dataset and return every record in ``t3_panel`` shape.

    Raises ``ValueError`` if a mapped record carries a quarantined label (it cannot, by
    construction -- this is a tripwire) or an empty session (``b_present`` and
    ``c_present`` both false, which rule 3-F10 forbids).
    """

    records: list[dict[str, Any]] = []
    for raw in read_source(source_path):
        record = map_record(raw)

        leaked = _FORBIDDEN_KEYS.intersection(record)
        if leaked:
            raise ValueError(
                f"mapped record carries quarantined label(s) {sorted(leaked)} -- "
                "rule 3-F1 forbids these in this database"
            )
        if not (record["b_present"] or record["c_present"]):
            raise ValueError(
                "empty intervention session (b_present and c_present both false) for "
                f"{record['student_id']} #{record['intervention_session_number']} -- rule 3-F10"
            )
        records.append(record)
    return records
