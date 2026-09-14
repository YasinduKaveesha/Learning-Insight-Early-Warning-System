"""recommendations (work order B3.5)

Creates exactly one table: ``t3_recommendations`` (plan section 4.6; ``docs/13``).

SCHEMA ONLY. The state machine, the transition service, expiry logic and every endpoint
are B7. Here they are columns, five CHECK constraints and one partial unique index.

Two constraints carry the weight:

* ``ck_t3_reco_ethical_gate`` -- a recommendation that is ``pending`` or ``dismissed`` must
  never alter Component B or C behaviour (SF-027, rule 3-F5). It is a database constraint,
  not a validator, so a new endpoint added later cannot bypass it. Do not relax it, do not
  move it into a service.
* ``uq_t3_reco_active`` -- at most one *active* recommendation per
  ``(student_id, target_component)``. Partial, not total: a ``dismissed`` recommendation
  must not block a new one for the same learner and target.

There is deliberately NO write-back path built here (D10): the
``b_applied_at_intervention_session`` / ``c_applied_at_intervention_session`` columns exist
and stay NULL for all of v1. There is NO CHECK enumerating the four ``proposed_action``
kinds -- the vocabulary is closed by decision (D7), not by schema, and an unrecognised kind
must render a readable fallback rather than crash. There is NO trigger -> action mapping --
D7 froze the vocabulary, not the mapping.

``pipeline_run_id`` carries the FK to ``t3_pipeline_runs`` (a recommendation is a pipeline
output, the same choice as ``t3_panel`` / ``t3_features_at_t`` / ``t3_predictions``) and is
the sixth reduced-provenance column; the other five are the B3.2 precedent set.
``student_id`` uses the ``b_learners`` shadow-table pattern; ``component3_include_object``
keeps this migration from emitting DDL against ``b_learners``.

Revision ID: 0006_recommendations
Revises: 0005_panel_source_ids_c_guards
Create Date: 2026-09-01

(Revision id is 19 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_recommendations"
down_revision: Union[str, Sequence[str], None] = "0005_panel_source_ids_c_guards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# B7's author must see this: trigger.evidence must never contain `population`, `dd_subtype`,
# any latent trait, or any cluster label (docs/13 "Evidence constraints"; rule 3-F1).
# Enforcement is B7's job; this comment is carried on the column so it is not lost.
_TRIGGER_COMMENT = (
    "Why the recommendation was raised, with its evidence ({type, evidence}). "
    "trigger.evidence must NEVER contain population, dd_subtype, any latent trait, or any "
    "cluster label (docs/13; rule 3-F1). Enforcement is B7's job."
)


def upgrade() -> None:
    op.create_table(
        "t3_recommendations",
        sa.Column("recommendation_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("issued_at_intervention_session", sa.Integer(), nullable=False),
        sa.Column("expires_after_session", sa.Integer(), nullable=False),
        sa.Column("target_component", sa.String(length=8), nullable=False),
        sa.Column(
            "trigger",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment=_TRIGGER_COMMENT,
        ),
        sa.Column("proposed_action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_summary", sa.String(length=280), nullable=False),
        sa.Column(
            "teacher_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "teacher_modified_action",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("decided_at_utc", sa.DateTime(timezone=True), nullable=True),
        # D10: no write-back path in v1. These exist for a future in which write-back is
        # approved and stay NULL for all of v1. The ethical gate below governs them.
        sa.Column("b_applied_at_intervention_session", sa.Integer(), nullable=True),
        sa.Column("c_applied_at_intervention_session", sa.Integer(), nullable=True),
        # Reduced provenance -- five non-key columns; pipeline_run_id (FK) is the sixth.
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
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
            "target_component IN ('B', 'C', 'both')",
            name=op.f("ck_t3_reco_target"),
        ),
        sa.CheckConstraint(
            "teacher_status IN ('pending', 'accepted', 'dismissed', 'modified')",
            name=op.f("ck_t3_reco_status"),
        ),
        sa.CheckConstraint(
            "expires_after_session <= issued_at_intervention_session + 5",
            name=op.f("ck_t3_reco_expiry"),
        ),
        sa.CheckConstraint(
            "(teacher_modified_action IS NOT NULL) = (teacher_status = 'modified')",
            name=op.f("ck_t3_reco_modified"),
        ),
        # The ethical gate. A pending or dismissed recommendation must never have applied a
        # change to Component B or C. Database constraint, not application logic, on purpose
        # (SF-027, rule 3-F5). Do not relax it, do not move it into a service.
        sa.CheckConstraint(
            "teacher_status IN ('accepted', 'modified') "
            "OR (b_applied_at_intervention_session IS NULL "
            "AND c_applied_at_intervention_session IS NULL)",
            name=op.f("ck_t3_reco_ethical_gate"),
        ),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_recommendations_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["t3_pipeline_runs.pipeline_run_id"],
            name="fk_t3_recommendations_pipeline_run_id_t3_pipeline_runs",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["b_learners.learner_id"],
            name="fk_t3_recommendations_student_id_b_learners",
        ),
        sa.PrimaryKeyConstraint("recommendation_id", name=op.f("pk_t3_recommendations")),
    )
    # The active-recommendation invariant. Partial, not total -- a dismissed recommendation
    # must not block a new one for the same (student_id, target_component).
    op.create_index(
        "uq_t3_reco_active",
        "t3_recommendations",
        ["student_id", "target_component"],
        unique=True,
        postgresql_where=sa.text(
            "teacher_status IN ('pending', 'accepted', 'modified')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_t3_reco_active", table_name="t3_recommendations")
    op.drop_table("t3_recommendations")
