"""The declarative base and the shared MetaData for Component 3's own tables.

Everything mapped on this `Base` is a `t3_` table Component 3 owns, plus the minimal shadow
of `classrooms` needed to express one foreign key (see `models.py`). `migrations/env.py`
points `target_metadata` at `Base.metadata`; `component3_include_object` still filters the
autogenerate/upgrade diff down to `t3_` objects, so nothing here can emit DDL against a
student-app table.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable, predictable constraint names so an autogenerate diff is reproducible and a
# downgrade drops exactly what an upgrade created.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


metadata = Base.metadata
