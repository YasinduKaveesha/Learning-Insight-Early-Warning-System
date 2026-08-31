"""demo learner map (work order B4.1)

Creates exactly one table: ``t3_demo_learner_map``.

WHY THIS EXISTS: ``app.application.t3_loader.SqlLearnerResolver`` matches the research
dataset's ``student_id`` ("STU-0001", ...) against ``b_learners.name`` -- documented in its
own docstring as "the seam" for live-integration wiring, not yet connected. Live ``name``
values are empty/unrelated, so zero panel rows have ever actually been written. This table is
a demo-only bridge, mapping each research ``student_id`` to exactly one live
``b_learners.learner_id``, so a resolver can be wired without inventing a live correspondence
that does not exist yet (that remains a live-integration decision, backend_plan.md section
11 / 5.1 D9 / D15).

Both directions are unique on purpose -- this is load-bearing, not incidental. A many-to-one
mapping in either direction could misattribute one child's analytics to another:

* ``learner_id`` is the PRIMARY KEY -- at most one ``research_student_id`` per learner.
* ``research_student_id`` carries a UNIQUE constraint -- at most one ``learner_id`` per
  research student.

``research_student_id`` also carries a CHECK enforcing the exact research id format
(``STU-`` + four digits, case-sensitive) so a near-miss like ``STU-1`` or ``stu-0001`` is
rejected by the database rather than silently mismatched.

This table carries the full six-column reduced provenance set (``ProvenanceMixin``, plan
section 4) like ``t3_classroom_keys`` -- ``learner_id`` is a foreign key into the
``b_learners`` shadow, not a pipeline output, so there is no separate ``pipeline_run_id`` PK
member to let it stand in for the sixth column.

Revision ID: 0007_demo_learner_map
Revises: 0006_recommendations
Create Date: 2026-09-01

(Revision id is 25 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_demo_learner_map"
down_revision: Union[str, Sequence[str], None] = "0006_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "t3_demo_learner_map",
        sa.Column("learner_id", sa.UUID(), nullable=False),
        sa.Column("research_student_id", sa.String(length=16), nullable=False),
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
            "research_student_id ~ '^STU-[0-9]{4}$'",
            name=op.f("ck_t3_demo_learner_map_format"),
        ),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_demo_learner_map_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["b_learners.learner_id"],
            name="fk_t3_demo_learner_map_learner_id_b_learners",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("learner_id", name=op.f("pk_t3_demo_learner_map")),
        sa.UniqueConstraint(
            "research_student_id",
            name=op.f("uq_t3_demo_learner_map_research_student_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("t3_demo_learner_map")
