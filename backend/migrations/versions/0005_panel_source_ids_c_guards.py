"""panel source ids and Component C safety guards (work order B4)

Five additive, nullable columns on ``t3_panel``. The source payloads
(``dataset/source/so2_joined_dataset_seed20260828_n300.jsonl``) carry fields that
``docs/04`` section 4 specifies but ``backend_plan.md`` section 4.3 omitted:

* ``intervention_session_id`` / ``b_session_id`` / ``c_session_id`` -- the source's own
  identifiers (``mapping.*``). Stored as ``varchar`` to match the source type
  (``"STU-0001-I-001"`` etc.), not ``uuid``.
* ``c_session_technical_issue_flag`` (boolean) / ``c_inactive_time_sec`` (real) -- a safety
  requirement, not a nicety: ``backend_plan.md`` section 3 states a technical fault must
  NEVER be rendered as disengagement, and ``c_telemetry_quality_status`` alone cannot make
  that distinction.

The other ~15 Component C detail fields (``docs/04`` section 4) are deliberately NOT added:
they stay recoverable by re-running the loader, and this work order stays small.

The primary key is unchanged -- still
``(student_id, intervention_session_number, pipeline_run_id)``. It is NOT switched to
``docs/04``'s ``(student_id, intervention_session_id)``.

Revision ID: 0005_panel_source_ids_c_guards
Revises: 0004_predictions_model_versions
Create Date: 2026-09-01

(Revision id is 30 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_panel_source_ids_c_guards"
down_revision: Union[str, Sequence[str], None] = "0004_predictions_model_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "t3_panel",
        sa.Column("intervention_session_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "t3_panel",
        sa.Column("b_session_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "t3_panel",
        sa.Column("c_session_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "t3_panel",
        sa.Column("c_session_technical_issue_flag", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "t3_panel",
        sa.Column("c_inactive_time_sec", sa.REAL(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("t3_panel", "c_inactive_time_sec")
    op.drop_column("t3_panel", "c_session_technical_issue_flag")
    op.drop_column("t3_panel", "c_session_id")
    op.drop_column("t3_panel", "b_session_id")
    op.drop_column("t3_panel", "intervention_session_id")
