"""The reduced six-column provenance set (`docs/04` section 2).

Component 3's tables hold synthetic analytics derived from synthetic sessions and there is
no authenticated actor to record, so they use this reduced set -- **not** the live student
app's seventeen-column `ProvenanceMixin` (which carries `actor_user_id`, `request_id` and
`operation_or_event_type`). Do not copy that one in.

    created_at_utc           timestamptz not null default now()
    updated_at_utc           timestamptz not null default now()
    source_class             varchar(16) not null  CHECK IN (REAL, SYNTHETIC, IMPORTED, TEST)
    source_system            varchar(128) not null
    parameter_source_status  varchar(32) not null
    pipeline_run_id          uuid not null

`t3_pipeline_runs` is the one exception: its primary key *is* `pipeline_run_id`, so it mixes
in `ProvenanceCoreMixin` (the five non-key columns) and lets the PK serve as the sixth --
see `models.py`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

_SOURCE_CLASS_VALUES = ("REAL", "SYNTHETIC", "IMPORTED", "TEST")


def source_class_check() -> CheckConstraint:
    """The `source_class` enumeration CHECK; the naming convention names it
    `ck_<table>_source_class`.

    Spelled out in each table's `__table_args__` rather than on a mixin `__table_args__` so a
    table that adds its own constraints (like `t3_classroom_keys`) does not have to fight
    declarative attribute merging to keep this one.
    """

    # Bare constraint name -- the MetaData naming convention adds the `ck_<table>_` prefix.
    values = ", ".join(f"'{v}'" for v in _SOURCE_CLASS_VALUES)
    return CheckConstraint(f"source_class IN ({values})", name="source_class")


class ProvenanceCoreMixin:
    """The five provenance columns that are never a primary key."""

    @declared_attr
    def created_at_utc(cls) -> Mapped[dt.datetime]:
        return mapped_column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        )

    @declared_attr
    def updated_at_utc(cls) -> Mapped[dt.datetime]:
        return mapped_column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        )

    @declared_attr
    def source_class(cls) -> Mapped[str]:
        return mapped_column(String(16), nullable=False)

    @declared_attr
    def source_system(cls) -> Mapped[str]:
        return mapped_column(String(128), nullable=False)

    @declared_attr
    def parameter_source_status(cls) -> Mapped[str]:
        return mapped_column(String(32), nullable=False)


class ProvenanceMixin(ProvenanceCoreMixin):
    """The full reduced set: the five core columns plus a non-key `pipeline_run_id`.

    Every `t3_` table except `t3_pipeline_runs` mixes this in.
    """

    @declared_attr
    def pipeline_run_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(PgUUID(as_uuid=True), nullable=False)
