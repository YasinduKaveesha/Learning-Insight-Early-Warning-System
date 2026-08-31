"""Component 3's owned tables.

Added one work order at a time so that real `t3_` tables in both metadata and database are
what make the autogenerate guard-check meaningful:

* B3.2 -- `t3_pipeline_runs` (provenance root), `t3_classroom_keys` (permanent class key).
* B3.3 -- `t3_panel` (one row per learner per intervention session),
  `t3_features_at_t` (the model input matrix, one row per `(student_id, t)`).
* B3.4 -- `t3_predictions` (the model output), `t3_model_versions` (the model card).

Still not created here: `t3_recommendations` (that is B3.5).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CHAR,
    REAL,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import desc as sa_desc
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.infrastructure.db.provenance import (
    ProvenanceCoreMixin,
    ProvenanceMixin,
    source_class_check,
)

# --------------------------------------------------------------------------------------
# Shadows of student-app tables. Component 3 never creates, alters or drops these -- they
# belong to the live app. Each one-column stand-in exists only so a foreign key from a
# `t3_` table can be expressed in metadata. `component3_include_object` excludes them from
# every migration by name; the guard-check probe proves that.
# --------------------------------------------------------------------------------------
classrooms = Table(
    "classrooms",
    Base.metadata,
    Column("classroom_id", PgUUID(as_uuid=True), primary_key=True),
    info={"component3_shadow": True},
)

b_learners = Table(
    "b_learners",
    Base.metadata,
    Column("learner_id", PgUUID(as_uuid=True), primary_key=True),
    info={"component3_shadow": True},
)


class PipelineRun(ProvenanceCoreMixin, Base):
    """`t3_pipeline_runs` -- the provenance root (`docs/04` sections 2, 7; plan section 4.1).

    THE ONE PROVENANCE EXCEPTION. Every other `t3_` table carries all six reduced provenance
    columns via `ProvenanceMixin`. Here the primary key *is* `pipeline_run_id`, so the table
    mixes in only the five non-key provenance columns (`ProvenanceCoreMixin`) and lets the
    primary key serve as the sixth. Applying the full mixin would give the table a second,
    self-referential `pipeline_run_id` -- if you are about to add a self-referencing foreign
    key here, this is the paragraph to re-read.
    """

    __tablename__ = "t3_pipeline_runs"
    __table_args__ = (source_class_check(),)

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True
    )
    started_at_utc: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dataset_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClassroomKey(ProvenanceMixin, Base):
    """`t3_classroom_keys` -- the permanent class key (D1; `docs/04` section 3.1, plan 4.2).

    Generated once at class creation and **never rotated**: there is no setter and no
    `UPDATE` path for `class_key` anywhere in the codebase. The format CHECK permits `0`,
    `O`, `1`, `I` at rest on purpose -- excluding those is a generation rule
    (`app.application.class_key`), not a storage rule -- so it is not tightened here.

    Carries the full six-column `ProvenanceMixin`: `docs/04` section 3.1 lists only
    `classroom_id` and `class_key`, but `plan/backend_plan.md` section 4 says every new table
    carries the reduced set, and the build plan wins.
    """

    __tablename__ = "t3_classroom_keys"
    __table_args__ = (
        UniqueConstraint("class_key", name="uq_t3_classroom_keys_class_key"),
        # Bare name -> naming convention -> `ck_t3_classroom_keys_format` (plan section 4.2).
        CheckConstraint("class_key ~ '^[0-9A-Z]{6}$'", name="format"),
        source_class_check(),
    )

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "classrooms.classroom_id",
            name="fk_t3_classroom_keys_classroom_id_classrooms",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    class_key: Mapped[str] = mapped_column(CHAR(6), nullable=False)


class Panel(ProvenanceCoreMixin, Base):
    """`t3_panel` -- one row per learner per intervention session (plan section 4.3).

    Keyed by `intervention_session_number` (not `t`): this table holds **every** session,
    while `t3_features_at_t` holds only the snapshot subset keyed by `t`. Every `t` is an
    `intervention_session_number`; not every session is a snapshot. The two names are kept
    apart on purpose -- collapsing them hides which rows are supervised.

    Every Component B / Component C measure keeps its `b_` / `c_` prefix. Both components
    carry an accuracy rate and a timing measure; a previous build silently collapsed them
    into one column when Component B's value won a name collision, destroying the D2 / 3-F9
    distinction. There is no unprefixed `accuracy_rate`, `response_time` or `latency` here.

    `pipeline_run_id` is part of the primary key, carries the FK to `t3_pipeline_runs`, and
    serves as the sixth reduced-provenance column -- so the class mixes in only the five
    non-key provenance columns (`ProvenanceCoreMixin`), the same pattern as `t3_pipeline_runs`.
    """

    __tablename__ = "t3_panel"
    __table_args__ = (
        # Bare name -> naming convention -> `ck_t3_panel_nonempty` (plan section 4.3).
        CheckConstraint("b_present OR c_present", name="nonempty"),
        source_class_check(),
        Index(
            "ix_t3_panel_learner_session",
            "student_id",
            "intervention_session_number",
        ),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "b_learners.learner_id",
            name="fk_t3_panel_student_id_b_learners",
        ),
        primary_key=True,
    )
    intervention_session_number: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )
    intervention_session_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    b_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    c_present: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Component B -- all nullable (b_present may be false).
    b_accuracy_rate: Mapped[float | None] = mapped_column(REAL, nullable=True)
    b_total_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_correct_responses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_hint_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_median_item_response_time_sec: Mapped[float | None] = mapped_column(REAL, nullable=True)
    b_item_response_time_std_sec: Mapped[float | None] = mapped_column(REAL, nullable=True)
    b_mastery: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 7 skills
    b_mastery_certified: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    b_mastery_slope_w4: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    b_opportunities_w4: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    b_error_class_dist: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Component C -- all nullable (c_present may be false).
    c_accuracy_rate: Mapped[float | None] = mapped_column(REAL, nullable=True)
    c_task_completion_rate: Mapped[float | None] = mapped_column(REAL, nullable=True)
    c_median_game_task_latency_sec: Mapped[float | None] = mapped_column(REAL, nullable=True)
    c_difficulty_floor_hits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    c_engagement_score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    c_engagement_components: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    c_frustration_index: Mapped[float | None] = mapped_column(REAL, nullable=True)
    c_frustration_components: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    c_learner_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    c_state_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    c_telemetry_quality_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    c_current_difficulty_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    c_difficulty_trend: Mapped[str | None] = mapped_column(String(16), nullable=True)

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "t3_pipeline_runs.pipeline_run_id",
            name="fk_t3_panel_pipeline_run_id_t3_pipeline_runs",
        ),
        primary_key=True,
    )


class FeaturesAtT(ProvenanceCoreMixin, Base):
    """`t3_features_at_t` -- the model input matrix (plan section 4.4; docs/04 section 4).

    ONE ROW PER `(student_id, t)`, never one row per student. The composite primary key
    carries `t` so the system can ask "what did we know at session 9, and were we right?";
    a per-student table collapses time and makes the early-detection curve impossible.

    The 58 features are stored as `jsonb` keyed by name, not as 58 columns, so the schema
    survives a `feature_version` change and the "did the order match `feature_names_in_`?"
    check stays a loader-time runtime assertion rather than a migration.

    THERE IS NO `population` COLUMN, AND NO `dd_subtype`. Not nullable, not "for debugging"
    (rule 3-F1, SF-031). They are audit-only labels with no meaning for a real learner and
    are not stored anywhere in this database.

    `pipeline_run_id` is part of the primary key, carries the FK to `t3_pipeline_runs`, and
    is the sixth reduced-provenance column -- so only `ProvenanceCoreMixin` is mixed in.
    """

    __tablename__ = "t3_features_at_t"
    __table_args__ = (
        source_class_check(),
        Index("ix_t3_features_at_t_student_t", "student_id", "t"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "b_learners.learner_id",
            name="fk_t3_features_at_t_student_id_b_learners",
        ),
        primary_key=True,
    )
    t: Mapped[int] = mapped_column(Integer, primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "t3_pipeline_runs.pipeline_run_id",
            name="fk_t3_features_at_t_pipeline_run_id_t3_pipeline_runs",
        ),
        primary_key=True,
    )


class Prediction(ProvenanceCoreMixin, Base):
    """`t3_predictions` -- the model output, one row per
    `(student_id, t, model_version, pipeline_run_id)` (plan section 4.5; docs/04 section 4).

    SCHEMA ONLY. The decision layer (B5) computes `watch_flag`, `rank_within_t`, both
    trajectory columns and the explanation; here they are columns with constraints.

    Two traps, both resolved in favour of `plan/backend_plan.md` section 4.5:

    * **`ck_t3_predictions_watch_flag` uses `COALESCE(predicted_class, -1)`, not a bare
      `predicted_class >= 1`.** `predicted_class` is nullable (a learner below the warm-up
      floor has no prediction); a bare comparison evaluates to NULL for those rows and
      PostgreSQL PASSES a CHECK that is NULL -- leaving `watch_flag` unconstrained exactly
      on the Getting Started learners. `COALESCE(..., -1)` forces it to FALSE so the
      constraint bites. `docs/04` line 277 has the bare form; do not use it.
    * **There is no `CHECK ((risk_level IS NULL) = (evidence_status <> 'sufficient_evidence'))`.**
      It is unsatisfiable against real data (every produced row has `risk_level = NULL` and
      `evidence_status = 'sufficient_evidence'`). `risk_level_status` carries that meaning.

    `prob_class_*` and `predicted_class` are SERVER-ONLY -- never serialised. So is
    `engagement_trajectory` (D17). `ck_t3_predictions_no_high` is the schema-level guarantee
    that no code path can ever emit a High tier.

    `pipeline_run_id` (PK member + FK to `t3_pipeline_runs`) is the sixth reduced-provenance
    column, so only `ProvenanceCoreMixin` is mixed in.
    """

    __tablename__ = "t3_predictions"
    __table_args__ = (
        CheckConstraint(
            "evidence_status IN ('sufficient_evidence', 'insufficient_exposure', "
            "'insufficient_future_evidence', 'censored_by_observation_end', "
            "'administratively_missing')",
            name="evidence",
        ),
        CheckConstraint(
            "practice_trajectory IN ('improving', 'stable', 'needs_attention', 'unknown') "
            "AND engagement_trajectory IN ('improving', 'stable', 'needs_attention', "
            "'unknown')",
            name="trajectory",
        ),
        CheckConstraint(
            "watch_flag = (COALESCE(predicted_class, -1) >= 1 AND sessions_completed >= 3)",
            name="watch_flag",
        ),
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('Low', 'Moderate')",
            name="no_high",
        ),
        source_class_check(),
        Index("ix_t3_predictions_latest", "student_id", sa_desc("t")),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "b_learners.learner_id",
            name="fk_t3_predictions_student_id_b_learners",
        ),
        primary_key=True,
    )
    t: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(32), primary_key=True)

    evidence_status: Mapped[str] = mapped_column(String(32), nullable=False)
    sessions_completed: Mapped[int] = mapped_column(Integer, nullable=False)

    # Server-only. NEVER serialised to any client.
    prob_class_0: Mapped[float | None] = mapped_column(REAL, nullable=True)
    prob_class_1: Mapped[float | None] = mapped_column(REAL, nullable=True)
    prob_class_2plus: Mapped[float | None] = mapped_column(REAL, nullable=True)
    predicted_class: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # The teacher-facing signal (computed by B5, not here).
    watch_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rank_within_t: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_percentile_within_t: Mapped[float | None] = mapped_column(REAL, nullable=True)

    # Descriptive (D4, D11, D12). engagement_trajectory is STORED, NEVER SERVED (D17).
    practice_trajectory: Mapped[str] = mapped_column(String(16), nullable=False)
    engagement_trajectory: Mapped[str] = mapped_column(String(16), nullable=False)

    # Explanation.
    risk_explanation: Mapped[str | None] = mapped_column(String(280), nullable=True)
    shap_top3: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Pending -- kept nullable and unpopulated (no validated tier exists).
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_level_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="CALIBRATION_PENDING"
    )

    # Prediction-specific provenance (in addition to the reduced set).
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    artefact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    inference_timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "t3_pipeline_runs.pipeline_run_id",
            name="fk_t3_predictions_pipeline_run_id_t3_pipeline_runs",
        ),
        primary_key=True,
    )


class ModelVersion(ProvenanceMixin, Base):
    """`t3_model_versions` -- the model card, one row per deployed artefact (plan section 4.7;
    docs/04 section 4). Answers "which exact model produced this teacher-facing result?".

    Populated from `dev_docs/MODEL_CARD.md` and `notebooks/outputs/models/model_card.json`;
    migration 0004 seeds the single `1.0.0` row.

    Carries the full six-column `ProvenanceMixin` (with `pipeline_run_id` a plain
    `uuid NOT NULL`, no FK -- the same choice B3.2 made for `t3_classroom_keys`, since this
    is a registry row, not a pipeline output, and `t3_pipeline_runs` references model
    versions rather than the other way round). `plan` section 4 requires the reduced
    provenance set on every new table; `deployed_at_utc` is the domain timestamp on top.
    """

    __tablename__ = "t3_model_versions"
    __table_args__ = (source_class_check(),)

    model_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    artefact_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    artefact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    training_dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    training_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    sklearn_version: Mapped[str] = mapped_column(String(16), nullable=False)
    headline_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list] = mapped_column(JSONB, nullable=False)
    deployed_at_utc: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
