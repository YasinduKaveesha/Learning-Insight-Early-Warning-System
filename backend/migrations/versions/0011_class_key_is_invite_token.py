"""0011 -- the class key becomes the student app's join code (D49).

WHY THIS MIGRATION EXISTS
-------------------------
Until now Component 3 **minted its own** six-character key into ``t3_classroom_keys`` while a
learner joins by redeeming a code the student application issued and hashed into
``classroom_invites.token_hash``. The two were never the same string, so a teacher read a code
aloud that resolved to nothing -- verified on all six demo classrooms, where
``sha256(upper(class_key))`` matched no live invite hash.

D49 makes the student app's code the single official one. Component 3 stores the plaintext so a
teacher can re-read it forever, which is what D1 always intended: the live ``classroom_invites``
returns its token once and keeps only a hash, so the readable copy has to live here.

WHAT CHANGES
------------
The student app's canonical code is **8** characters from ``23456789ABCDEFGHJKMNPQRSTUVWXYZ``.
``class_key`` is ``CHAR(6)`` with a ``^[0-9A-Z]{6}$`` CHECK, so storing one would fail today.

* ``class_key``: ``CHAR(6)`` -> ``VARCHAR(16)``. Wider than the 8 it needs, so a future format
  change is a CHECK change rather than another column migration. ``VARCHAR`` also drops
  ``CHAR``'s blank padding, which would otherwise pad an 8-character code in a 16-wide column.
* the format CHECK: ``^[0-9A-Z]{6}$`` -> ``^[0-9A-Z]{8}$``. Still deliberately permissive at
  rest: excluding the ambiguous 0/O/1/I/L is the *generator's* rule, and the generator now lives
  in the student app.

``UNIQUE (class_key)``, the primary key and the ``ON DELETE RESTRICT`` foreign key to
``classrooms`` are all untouched.

EXISTING ROWS
-------------
Six rows hold unredeemable six-character keys. They are **left as they are** by this migration --
a data repair belongs in a script that can talk to the student app's API, not in DDL. They fail
the new CHECK, so the constraint is added ``NOT VALID`` and the repair script
(``scripts/backfill_class_keys.py``) validates it once every row carries a real token.

Downgrade is lossy by nature: an 8-character token cannot fit a ``CHAR(6)`` column, so it drops
the rows rather than truncating a join code into a string that silently resolves to nothing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_class_key_is_invite_token"
down_revision = "0010_reco_expiry_closure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw SQL for the constraint, not op.drop_constraint / op.create_check_constraint: the
    # metadata carries a naming convention (`ck_%(table_name)s_%(constraint_name)s`), so those
    # helpers would re-prefix an already-prefixed name into
    # `ck_t3_classroom_keys_ck_t3_classroom_keys_format`, which does not exist. 0002 sidestepped
    # this with `name=op.f(...)`; spelling the name literally is clearer here.
    op.execute("ALTER TABLE t3_classroom_keys DROP CONSTRAINT ck_t3_classroom_keys_format")
    op.alter_column(
        "t3_classroom_keys",
        "class_key",
        existing_type=sa.CHAR(length=6),
        type_=sa.String(length=16),
        existing_nullable=False,
        postgresql_using="btrim(class_key)",
    )
    # NOT VALID: the six pre-D49 rows still hold six-character keys and are repaired by
    # scripts/backfill_class_keys.py, which runs VALIDATE CONSTRAINT when it finishes.
    op.execute(
        "ALTER TABLE t3_classroom_keys "
        "ADD CONSTRAINT ck_t3_classroom_keys_format "
        "CHECK (class_key ~ '^[0-9A-Z]{8}$') NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE t3_classroom_keys DROP CONSTRAINT ck_t3_classroom_keys_format")
    # An 8-character join code does not fit CHAR(6). Truncating one would leave a key that looks
    # valid and resolves to nothing -- exactly the defect D49 removed -- so drop instead.
    op.execute("DELETE FROM t3_classroom_keys WHERE length(btrim(class_key)) <> 6")
    op.alter_column(
        "t3_classroom_keys",
        "class_key",
        existing_type=sa.String(length=16),
        type_=sa.CHAR(length=6),
        existing_nullable=False,
    )
    op.execute(
        "ALTER TABLE t3_classroom_keys "
        "ADD CONSTRAINT ck_t3_classroom_keys_format "
        "CHECK (class_key ~ '^[0-9A-Z]{6}$')"
    )
