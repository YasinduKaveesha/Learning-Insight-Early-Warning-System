"""Component 3's owned tables.

Added one work order at a time so that real `t3_` tables in both metadata and database are
what make the autogenerate guard-check meaningful:

* B3.2 -- `t3_pipeline_runs` (provenance root), `t3_classroom_keys` (permanent class key).
* B3.3 -- `t3_panel` (one row per learner per intervention session),
  `t3_features_at_t` (the model input matrix, one row per `(student_id, t)`).

Still not created here: `t3_predictions`, `t3_recommendations`, `t3_model_versions`.
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
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
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
