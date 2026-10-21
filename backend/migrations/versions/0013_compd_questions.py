"""compD question bank (owner direction 2026-10-21: the dashboard serves compD itself)

Creates exactly one table: ``t3_compd_questions``, the shared question bank of compD's teacher
side. ``app.infrastructure.db.models.CompdQuestionRecord`` carries the reasoning (the shared
bank, the hard delete, why ``options`` is an array or SQL NULL); this file only mirrors it.

It references the student app's ``teacher_profiles`` read-only, RESTRICT, as
``t3_teacher_bindings`` does. It creates nothing outside ``t3_`` and seeds no row (owner Q12).

Revision ID: 0013_compd_questions
Revises: 0012_run_scoped_indexes
Create Date: 2026-10-21

(Revision id is 20 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_compd_questions"
down_revision: Union[str, Sequence[str], None] = "0012_run_scoped_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "t3_compd_questions",
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("question_code", sa.String(length=32), nullable=True),
        sa.Column("topic", sa.String(length=16), nullable=False),
        sa.Column("difficulty", sa.String(length=8), nullable=False),
        sa.Column("question_text", sa.String(length=500), nullable=False),
        sa.Column("correct_answer", sa.String(length=255), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_teacher_profile_id", sa.UUID(), nullable=False),
        sa.Column("updated_by_teacher_profile_id", sa.UUID(), nullable=True),
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
            "topic IN ('Counting', 'Addition', 'Subtraction', 'Division')",
            name=op.f("ck_t3_compd_questions_topic"),
        ),
        sa.CheckConstraint(
            "difficulty IN ('Easy', 'Medium', 'Hard')",
            name=op.f("ck_t3_compd_questions_difficulty"),
        ),
        sa.CheckConstraint(
            "question_text <> ''", name=op.f("ck_t3_compd_questions_question_text_nonblank")
        ),
        sa.CheckConstraint(
            "correct_answer <> ''", name=op.f("ck_t3_compd_questions_correct_answer_nonblank")
        ),
        sa.CheckConstraint(
            "options IS NULL OR jsonb_typeof(options) = 'array'",
            name=op.f("ck_t3_compd_questions_options_array"),
        ),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_compd_questions_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_teacher_profile_id"],
            ["teacher_profiles.teacher_profile_id"],
            name="fk_t3_compd_questions_created_by_teacher_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_teacher_profile_id"],
            ["teacher_profiles.teacher_profile_id"],
            name="fk_t3_compd_questions_updated_by_teacher_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("question_id", name=op.f("pk_t3_compd_questions")),
    )
    # Partial, so any number of questions may have no code -- which `create_table` cannot express.
    op.create_index(
        "uq_t3_compd_questions_question_code",
        "t3_compd_questions",
        ["question_code"],
        unique=True,
        postgresql_where=sa.text("question_code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_t3_compd_questions_question_code", table_name="t3_compd_questions")
    op.drop_table("t3_compd_questions")
