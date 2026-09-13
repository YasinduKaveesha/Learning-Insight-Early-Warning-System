"""recommendation transition log (work order B7)

Creates exactly one table: ``t3_recommendation_transitions``.

WHY THIS EXISTS: ``docs/13`` section 6 makes the distribution of teacher decisions (accept /
dismiss / modify) the evaluation signal for the recommendation logic, and requires the log to be
COMPLETE, not best-effort. ``t3_recommendations`` holds only the latest status. This table holds
every decision, written in the same transaction as the status change, with the state machine
pinned by constraints: a decision always leaves ``pending``, happens at most once per
recommendation, and carries a modified action exactly when it is a modification.

No recommendation is generated or created here -- the trigger -> action mapping is still open
(``dev_docs/QUESTIONS_FOR_ML_TEAM_4.md``).

Revision ID: 0009_reco_transitions
Revises: 0008_teacher_bindings
Create Date: 2026-09-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_reco_transitions"
down_revision: Union[str, Sequence[str], None] = "0008_teacher_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "t3_recommendation_transitions",
        sa.Column("transition_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_id", sa.UUID(), nullable=False),
        sa.Column("teacher_profile_id", sa.UUID(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=True),
        sa.Column(
            "teacher_modified_action",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "occurred_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Reduced provenance (plan section 4) -- full six-column set.
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
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "from_status = 'pending'", name=op.f("ck_t3_reco_transition_from_pending")
        ),
        sa.CheckConstraint(
            "to_status IN ('accepted', 'dismissed', 'modified')",
            name=op.f("ck_t3_reco_transition_to_status"),
        ),
        sa.CheckConstraint(
            "(teacher_modified_action IS NOT NULL) = (to_status = 'modified')",
            name=op.f("ck_t3_reco_transition_modified"),
        ),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_recommendation_transitions_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["t3_recommendations.recommendation_id"],
            name=op.f("fk_t3_reco_transitions_recommendation_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "transition_id", name=op.f("pk_t3_recommendation_transitions")
        ),
        sa.UniqueConstraint("recommendation_id", name=op.f("uq_t3_reco_transition_once")),
    )


def downgrade() -> None:
    op.drop_table("t3_recommendation_transitions")
