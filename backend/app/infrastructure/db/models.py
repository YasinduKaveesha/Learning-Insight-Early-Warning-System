"""Component 3's owned tables for work order B3.2: the provenance root and the class key.

Scope is exactly two tables -- `t3_pipeline_runs` and `t3_classroom_keys`. The other five
`t3_` tables in `docs/04` section 4 are deliberately not created here: real `t3_` tables in
both metadata and database are what make the autogenerate guard-check meaningful, so they
arrive one work order at a time.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.infrastructure.db.provenance import (
    ProvenanceCoreMixin,
    ProvenanceMixin,
    source_class_check,
)

# --------------------------------------------------------------------------------------
# Shadow of a student-app table. Component 3 never creates, alters or drops `classrooms`
# -- it belongs to the live app. This one-column stand-in exists only so the foreign key
# from `t3_classroom_keys.classroom_id` can be expressed in metadata. `component3_include_
# object` excludes it from every migration by name; the guard-check probe proves that.
# --------------------------------------------------------------------------------------
classrooms = Table(
    "classrooms",
    Base.metadata,
    Column("classroom_id", PgUUID(as_uuid=True), primary_key=True),
    info={"component3_shadow": True},
)


class PipelineRun(ProvenanceCoreMixin, Base):
    """`t3_pipeline_runs` -- the provenance root (`docs/04` sections 2, 7; plan section 4.1).

    THE ONE PROVENANCE EXCEPTION. Every other `t3_` table carries all six reduced provenance
    columns via `ProvenanceMixin`. Here the primary key *is* `pipeline_run_id`, so the table
    mixes in only the five non-key provenance columns (`ProvenanceCoreMixin`) and lets the
    primary key serve as the sixth. Applying the full mixin would give the table a second,
    self-referential `pipeline_run_id` -- if you are about to add a self-referencing foreign
    key here, this is the paragraph to re-read.
    """

    __tablename__ = "t3_pipeline_runs"
    __table_args__ = (source_class_check(),)

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True
    )
    started_at_utc: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dataset_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClassroomKey(ProvenanceMixin, Base):
    """`t3_classroom_keys` -- the permanent class key (D1; `docs/04` section 3.1, plan 4.2).

    Generated once at class creation and **never rotated**: there is no setter and no
    `UPDATE` path for `class_key` anywhere in the codebase. The format CHECK permits `0`,
    `O`, `1`, `I` at rest on purpose -- excluding those is a generation rule
    (`app.application.class_key`), not a storage rule -- so it is not tightened here.

    Carries the full six-column `ProvenanceMixin`: `docs/04` section 3.1 lists only
    `classroom_id` and `class_key`, but `plan/backend_plan.md` section 4 says every new table
    carries the reduced set, and the build plan wins.
    """

    __tablename__ = "t3_classroom_keys"
    __table_args__ = (
        UniqueConstraint("class_key", name="uq_t3_classroom_keys_class_key"),
        # Bare name -> naming convention -> `ck_t3_classroom_keys_format` (plan section 4.2).
        CheckConstraint("class_key ~ '^[0-9A-Z]{6}$'", name="format"),
        source_class_check(),
    )

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "classrooms.classroom_id",
            name="fk_t3_classroom_keys_classroom_id_classrooms",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    class_key: Mapped[str] = mapped_column(CHAR(6), nullable=False)
