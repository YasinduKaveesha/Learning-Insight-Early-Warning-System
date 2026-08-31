"""initial baseline -- no schema, establishes the t3_ chain

Creates no tables. Running ``alembic upgrade head`` on this revision only causes Alembic
to create its own bookkeeping table, ``t3_alembic_version`` (see migrations/env.py). The
student app's ``alembic_version`` is left untouched. Component 3's real tables arrive in
later work orders.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-08-31
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001_initial_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
