"""teacher bindings (work order B2.3)

Creates exactly one table: ``t3_teacher_bindings``.

WHY THIS EXISTS: the dashboard frontend has no login screen and never will for the demo.
Supabase anonymous sign-in is enabled, so the frontend gets a real, signature-verifiable JWT
with no login UI -- but an anonymous token's ``sub`` identifies no teacher. This table maps
that durable anonymous subject onto one ``teacher_profiles`` row drawn from
``T3_DEMO_TEACHER_POOL``, so ``app.application.principal_resolution.resolve_principal`` can
answer "who is this" for a demo device without Component 3 ever provisioning an ``app_users``
or ``teacher_profiles`` row itself -- that remains the student app's exclusive job. Demo-only:
meant to be dropped whole once real teacher login ships.

``teacher_profile_id`` carries a UNIQUE constraint on purpose -- one demo device claims one
teacher, so two concurrent demo sessions never fight over the same class list.

This table carries the full six-column reduced provenance set (``ProvenanceMixin``, plan
section 4) like ``t3_demo_learner_map`` and ``t3_classroom_keys`` -- ``supabase_subject`` is an
opaque JWT claim, not a pipeline output, so there is no separate ``pipeline_run_id`` PK member
to let it stand in for the sixth column; ``pipeline_run_id`` here is a plain ``uuid NOT NULL``
with no FK, the same choice those two tables made.

Revision ID: 0008_teacher_bindings
Revises: 0007_demo_learner_map
Create Date: 2026-09-01

(Revision id is 21 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_teacher_bindings"
down_revision: Union[str, Sequence[str], None] = "0007_demo_learner_map"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "t3_teacher_bindings",
        sa.Column("supabase_subject", sa.String(length=255), nullable=False),
        sa.Column("teacher_profile_id", sa.UUID(), nullable=False),
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
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_teacher_bindings_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["teacher_profile_id"],
            ["teacher_profiles.teacher_profile_id"],
            name="fk_t3_teacher_bindings_teacher_profile_id_teacher_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("supabase_subject", name=op.f("pk_t3_teacher_bindings")),
        sa.UniqueConstraint(
            "teacher_profile_id",
            name=op.f("uq_t3_teacher_bindings_teacher_profile_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("t3_teacher_bindings")
