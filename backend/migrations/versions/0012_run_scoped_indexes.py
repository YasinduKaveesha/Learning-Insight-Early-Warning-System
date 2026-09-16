"""0012 -- indexes that lead with the pipeline run.

Every read the dashboard makes of `t3_predictions`, `t3_panel` and `t3_recommendations` filters
on `pipeline_run_id` first -- a run is the unit the API serves -- and then narrows to a class's
learners. The existing indexes all lead with `student_id`, so none of them serves a run-scoped
read. Measured cost on the demo is small (the tables hold hundreds of rows); the indexes exist
because every run adds a generation beside the last one, and a run-wide scan grows with that.

Additive and reversible: indexes only, no data change.
"""

from __future__ import annotations

from alembic import op

revision = "0012_run_scoped_indexes"
down_revision = "0011_class_key_is_invite_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_t3_predictions_run_student"),
        "t3_predictions",
        ["pipeline_run_id", "student_id"],
    )
    op.create_index(
        op.f("ix_t3_panel_run_student"),
        "t3_panel",
        ["pipeline_run_id", "student_id", "intervention_session_number"],
    )
    op.create_index(
        op.f("ix_t3_recommendations_run_student"),
        "t3_recommendations",
        ["pipeline_run_id", "student_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_t3_recommendations_run_student"), table_name="t3_recommendations")
    op.drop_index(op.f("ix_t3_panel_run_student"), table_name="t3_panel")
    op.drop_index(op.f("ix_t3_predictions_run_student"), table_name="t3_predictions")
