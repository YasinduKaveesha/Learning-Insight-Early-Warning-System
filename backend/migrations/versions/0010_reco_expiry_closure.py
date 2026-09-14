"""recommendation expiry closure (decision D47)

Alters two Component 3 tables; creates none.

WHY THIS EXISTS: the ML team's ruling on expiry (``dev_docs/ANSWERS_TO_APP_TEAM_5.md`` Q6):

1. expiry closes a suggestion's active period WHATEVER its ``teacher_status``;
2. expiry NEVER changes ``teacher_status`` -- an acceptance stays an acceptance;
3. the closure is logged as a SYSTEM event, with no teacher id and a distinct event type;
4. the one-active-suggestion constraint covers OPEN suggestions only;
5. the generator writes the closure when the learner's current session passes
   ``expires_after_session``.

``uq_t3_reco_active`` could not previously depend on expiry, because expiry depends on the
learner's current session, which is not stored on the row. A closure the generator WRITES is
stored, so the index can depend on it.

``t3_recommendations``
  + ``closed_at_session``, ``closed_at_utc`` (both null, or both set)
  + CHECK a closure happens only after ``expires_after_session``
  ~ ``uq_t3_reco_active`` gains ``AND closed_at_session IS NULL``

``t3_recommendation_transitions``
  + ``event_type`` in (``teacher_decision``, ``expiry_closure``), default ``teacher_decision``
  ~ ``teacher_profile_id`` nullable: set exactly for a teacher decision
  ~ the three state-machine CHECKs apply to teacher decisions; a closure must have
    ``to_status = from_status`` (the database itself refuses a closure that changes the decision)
    and no modified action
  ~ ``uq_t3_reco_transition_once`` becomes a partial unique index over teacher decisions, with a
    sibling ``uq_t3_reco_closure_once`` over closures

Revision ID: 0010_reco_expiry_closure
Revises: 0009_reco_transitions
Create Date: 2026-09-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_reco_expiry_closure"
down_revision: Union[str, Sequence[str], None] = "0009_reco_transitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "teacher_status IN ('pending', 'accepted', 'modified')"


def upgrade() -> None:
    # --- t3_recommendations ---------------------------------------------------------------
    op.add_column("t3_recommendations", sa.Column("closed_at_session", sa.Integer(), nullable=True))
    op.add_column(
        "t3_recommendations",
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_closure_pair"),
        "t3_recommendations",
        "(closed_at_session IS NULL) = (closed_at_utc IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_closure_after_expiry"),
        "t3_recommendations",
        "closed_at_session IS NULL OR closed_at_session > expires_after_session",
    )
    op.drop_index("uq_t3_reco_active", table_name="t3_recommendations")
    op.create_index(
        "uq_t3_reco_active",
        "t3_recommendations",
        ["student_id", "target_component"],
        unique=True,
        postgresql_where=sa.text(f"{_ACTIVE} AND closed_at_session IS NULL"),
    )

    # --- t3_recommendation_transitions ----------------------------------------------------
    op.add_column(
        "t3_recommendation_transitions",
        sa.Column(
            "event_type",
            sa.String(length=32),
            server_default="teacher_decision",
            nullable=False,
        ),
    )
    op.alter_column(
        "t3_recommendation_transitions", "teacher_profile_id", existing_type=sa.UUID(), nullable=True
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_event_type"),
        "t3_recommendation_transitions",
        "event_type IN ('teacher_decision', 'expiry_closure')",
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_actor"),
        "t3_recommendation_transitions",
        "(teacher_profile_id IS NOT NULL) = (event_type = 'teacher_decision')",
    )

    for name in (
        "ck_t3_reco_transition_from_pending",
        "ck_t3_reco_transition_to_status",
        "ck_t3_reco_transition_modified",
    ):
        op.drop_constraint(op.f(name), "t3_recommendation_transitions", type_="check")

    op.create_check_constraint(
        op.f("ck_t3_reco_transition_from_pending"),
        "t3_recommendation_transitions",
        "(event_type = 'teacher_decision' AND from_status = 'pending') "
        "OR (event_type = 'expiry_closure' AND from_status IN ('pending', 'accepted', 'modified'))",
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_to_status"),
        "t3_recommendation_transitions",
        "(event_type = 'teacher_decision' AND to_status IN ('accepted', 'dismissed', 'modified')) "
        "OR (event_type = 'expiry_closure' AND to_status = from_status)",
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_modified"),
        "t3_recommendation_transitions",
        "(event_type = 'teacher_decision' "
        "AND (teacher_modified_action IS NOT NULL) = (to_status = 'modified')) "
        "OR (event_type = 'expiry_closure' AND teacher_modified_action IS NULL)",
    )

    op.drop_constraint(op.f("uq_t3_reco_transition_once"), "t3_recommendation_transitions", type_="unique")
    op.create_index(
        "uq_t3_reco_transition_once",
        "t3_recommendation_transitions",
        ["recommendation_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'teacher_decision'"),
    )
    op.create_index(
        "uq_t3_reco_closure_once",
        "t3_recommendation_transitions",
        ["recommendation_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'expiry_closure'"),
    )


def downgrade() -> None:
    # Closure events cannot be represented in the 0009 schema. Refuse rather than silently
    # delete research-log rows.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM t3_recommendation_transitions "
        "WHERE event_type = 'expiry_closure') THEN RAISE EXCEPTION "
        "'0010 downgrade refused: expiry_closure events exist in t3_recommendation_transitions'; "
        "END IF; END $$;"
    )

    op.drop_index("uq_t3_reco_closure_once", table_name="t3_recommendation_transitions")
    op.drop_index("uq_t3_reco_transition_once", table_name="t3_recommendation_transitions")
    op.create_unique_constraint(
        op.f("uq_t3_reco_transition_once"), "t3_recommendation_transitions", ["recommendation_id"]
    )
    for name in (
        "ck_t3_reco_transition_modified",
        "ck_t3_reco_transition_to_status",
        "ck_t3_reco_transition_from_pending",
        "ck_t3_reco_transition_actor",
        "ck_t3_reco_transition_event_type",
    ):
        op.drop_constraint(op.f(name), "t3_recommendation_transitions", type_="check")
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_from_pending"),
        "t3_recommendation_transitions",
        "from_status = 'pending'",
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_to_status"),
        "t3_recommendation_transitions",
        "to_status IN ('accepted', 'dismissed', 'modified')",
    )
    op.create_check_constraint(
        op.f("ck_t3_reco_transition_modified"),
        "t3_recommendation_transitions",
        "(teacher_modified_action IS NOT NULL) = (to_status = 'modified')",
    )
    op.alter_column(
        "t3_recommendation_transitions", "teacher_profile_id", existing_type=sa.UUID(), nullable=False
    )
    op.drop_column("t3_recommendation_transitions", "event_type")

    op.drop_index("uq_t3_reco_active", table_name="t3_recommendations")
    op.create_index(
        "uq_t3_reco_active",
        "t3_recommendations",
        ["student_id", "target_component"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
    )
    op.drop_constraint(op.f("ck_t3_reco_closure_after_expiry"), "t3_recommendations", type_="check")
    op.drop_constraint(op.f("ck_t3_reco_closure_pair"), "t3_recommendations", type_="check")
    op.drop_column("t3_recommendations", "closed_at_utc")
    op.drop_column("t3_recommendations", "closed_at_session")
