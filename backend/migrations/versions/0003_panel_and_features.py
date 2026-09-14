"""panel and features_at_t (work order B3.3)

Creates exactly two tables:

* ``t3_panel``          -- one row per learner per intervention session, keyed by
  ``(student_id, intervention_session_number, pipeline_run_id)``. Every Component B / C
  measure keeps its ``b_`` / ``c_`` prefix (plan section 4.3). ``ck_t3_panel_nonempty``
  (``b_present OR c_present``) mirrors rule 3-F10 -- an empty session must fail loudly.
* ``t3_features_at_t``  -- the model input matrix, one row per ``(student_id, t)``, keyed by
  ``(student_id, t, feature_version, pipeline_run_id)``. The 58 features live in one
  ``jsonb`` column, not 58 columns. NO ``population`` column, NO ``dd_subtype`` (rule 3-F1).

Both carry the five non-key reduced provenance columns; ``pipeline_run_id`` is the sixth and
also the FK to ``t3_pipeline_runs`` and part of the primary key. The foreign keys to
``b_learners`` and ``t3_pipeline_runs`` reference tables Component 3 does not own for the
learner side; ``component3_include_object`` keeps every migration from emitting DDL against
``b_learners``.

Revision ID: 0003_panel_and_features
Revises: 0002_provenance_root_and_keys
Create Date: 2026-08-31

(Revision id kept <= 32 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_panel_and_features"
down_revision: Union[str, Sequence[str], None] = "0002_provenance_root_and_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "t3_features_at_t",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("t", sa.Integer(), nullable=False),
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        # Reduced provenance -- five non-key columns; pipeline_run_id (PK + FK) is the sixth.
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_class", sa.String(length=16), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("parameter_source_status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_features_at_t_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["t3_pipeline_runs.pipeline_run_id"],
            name="fk_t3_features_at_t_pipeline_run_id_t3_pipeline_runs",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["b_learners.learner_id"],
            name="fk_t3_features_at_t_student_id_b_learners",
        ),
        sa.PrimaryKeyConstraint(
            "student_id",
            "t",
            "feature_version",
            "pipeline_run_id",
            name=op.f("pk_t3_features_at_t"),
        ),
    )
    op.create_index(
        "ix_t3_features_at_t_student_t",
        "t3_features_at_t",
        ["student_id", "t"],
        unique=False,
    )
    op.create_table(
        "t3_panel",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("intervention_session_number", sa.Integer(), nullable=False),
        sa.Column("intervention_session_date", sa.Date(), nullable=False),
        sa.Column("b_present", sa.Boolean(), nullable=False),
        sa.Column("c_present", sa.Boolean(), nullable=False),
        # Component B -- all nullable (b_present may be false).
        sa.Column("b_accuracy_rate", sa.REAL(), nullable=True),
        sa.Column("b_total_questions", sa.Integer(), nullable=True),
        sa.Column("b_correct_responses", sa.Integer(), nullable=True),
        sa.Column("b_hint_requests", sa.Integer(), nullable=True),
        sa.Column("b_median_item_response_time_sec", sa.REAL(), nullable=True),
        sa.Column("b_item_response_time_std_sec", sa.REAL(), nullable=True),
        sa.Column("b_mastery", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("b_mastery_certified", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("b_mastery_slope_w4", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("b_opportunities_w4", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("b_error_class_dist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Component C -- all nullable (c_present may be false).
        sa.Column("c_accuracy_rate", sa.REAL(), nullable=True),
        sa.Column("c_task_completion_rate", sa.REAL(), nullable=True),
        sa.Column("c_median_game_task_latency_sec", sa.REAL(), nullable=True),
        sa.Column("c_difficulty_floor_hits", sa.Integer(), nullable=True),
        sa.Column("c_engagement_score", sa.REAL(), nullable=True),
        sa.Column("c_engagement_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("c_frustration_index", sa.REAL(), nullable=True),
        sa.Column("c_frustration_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("c_learner_state", sa.String(length=32), nullable=True),
        sa.Column("c_state_reason", sa.String(length=64), nullable=True),
        sa.Column("c_telemetry_quality_status", sa.String(length=32), nullable=True),
        sa.Column("c_current_difficulty_level", sa.Integer(), nullable=True),
        sa.Column("c_difficulty_trend", sa.String(length=16), nullable=True),
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        # Reduced provenance -- five non-key columns; pipeline_run_id (PK + FK) is the sixth.
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_class", sa.String(length=16), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("parameter_source_status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_panel_source_class"),
        ),
        sa.CheckConstraint("b_present OR c_present", name=op.f("ck_t3_panel_nonempty")),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["t3_pipeline_runs.pipeline_run_id"],
            name="fk_t3_panel_pipeline_run_id_t3_pipeline_runs",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["b_learners.learner_id"],
            name="fk_t3_panel_student_id_b_learners",
        ),
        sa.PrimaryKeyConstraint(
            "student_id",
            "intervention_session_number",
            "pipeline_run_id",
            name=op.f("pk_t3_panel"),
        ),
    )
    op.create_index(
        "ix_t3_panel_learner_session",
        "t3_panel",
        ["student_id", "intervention_session_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_t3_panel_learner_session", table_name="t3_panel")
    op.drop_table("t3_panel")
    op.drop_index("ix_t3_features_at_t_student_t", table_name="t3_features_at_t")
    op.drop_table("t3_features_at_t")
