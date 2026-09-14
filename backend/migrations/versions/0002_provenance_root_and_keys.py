"""provenance root and classroom keys (work order B3.2)

Creates exactly two tables:

* ``t3_pipeline_runs``  -- the provenance root (docs/04 sections 2, 7; plan section 4.1).
  Its primary key IS ``pipeline_run_id``, so it carries only the five non-key reduced
  provenance columns and lets the PK serve as the sixth -- the one provenance exception.
* ``t3_classroom_keys`` -- the permanent class key (D1; docs/04 section 3.1, plan 4.2),
  with the six-column reduced provenance set, a ``UNIQUE`` ``class_key`` and the format
  CHECK ``class_key ~ '^[0-9A-Z]{6}$'`` (deliberately permissive at rest -- excluding
  0/O/1/I is a generation rule, not a storage rule).

The foreign key ``t3_classroom_keys.classroom_id -> classrooms.classroom_id`` references a
student-app table Component 3 does not own; ``component3_include_object`` keeps every
migration (this one and the autogenerate guard-check) from ever emitting DDL against it.

Revision ID: 0002_provenance_root_and_keys
Revises: 0001_initial_baseline
Create Date: 2026-08-31

(Revision id kept <= 32 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_provenance_root_and_keys"
down_revision: Union[str, Sequence[str], None] = "0001_initial_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "t3_pipeline_runs",
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        sa.Column(
            "started_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dataset_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        # Reduced provenance -- five columns; the primary key is the sixth (pipeline_run_id).
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
            name=op.f("ck_t3_pipeline_runs_source_class"),
        ),
        sa.PrimaryKeyConstraint("pipeline_run_id", name=op.f("pk_t3_pipeline_runs")),
    )
    op.create_table(
        "t3_classroom_keys",
        sa.Column("classroom_id", sa.UUID(), nullable=False),
        sa.Column("class_key", sa.CHAR(length=6), nullable=False),
        # Reduced provenance -- full six-column set.
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
            "class_key ~ '^[0-9A-Z]{6}$'",
            name=op.f("ck_t3_classroom_keys_format"),
        ),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_classroom_keys_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.classroom_id"],
            name="fk_t3_classroom_keys_classroom_id_classrooms",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("classroom_id", name=op.f("pk_t3_classroom_keys")),
        sa.UniqueConstraint("class_key", name="uq_t3_classroom_keys_class_key"),
    )


def downgrade() -> None:
    op.drop_table("t3_classroom_keys")
    op.drop_table("t3_pipeline_runs")
