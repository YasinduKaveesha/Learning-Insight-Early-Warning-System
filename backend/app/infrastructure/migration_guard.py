"""Safety rails for Component 3's Alembic environment.

Component 3 shares one Supabase database with the live student app. That app runs its own
Alembic and sets no ``version_table``, so it owns the default ``alembic_version`` table and
has 36 tables that are absent from Component 3's metadata. Two rules keep our migration
chain from corrupting theirs:

* **Ownership filter.** Every autogenerate / upgrade comparison is filtered to objects
  Component 3 owns -- tables whose name starts with ``t3_`` and the indexes / constraints /
  columns that belong to them. Without it, ``alembic revision --autogenerate`` compares our
  (near-empty) metadata against the whole database and emits ``op.drop_table(...)`` for all
  36 student tables.
* **Direct connection only.** Alembic refuses to run through the Supabase transaction
  pooler (port 6543 or a ``pooler`` hostname), which breaks asyncpg prepared statements
  (backend_plan.md section 2). Migrations use port 5432.

This module holds no database connection and is import-safe without one, so the ownership
test can run in CI with no database.
"""

from __future__ import annotations

from app.infrastructure.db_url import is_pooler_url, normalise_async_url, redact_url

__all__ = [
    "assert_direct_connection",
    "component3_include_object",
    "is_pooler_url",
    "normalise_async_url",
    "owns_table_name",
    "redact_url",
]

T3_PREFIX = "t3_"

#: Component 3's private Alembic bookkeeping table. NOT the default ``alembic_version``.
OWNED_VERSION_TABLE = "t3_alembic_version"


def owns_table_name(name: str | None) -> bool:
    """True only for a table Component 3 created (``t3_`` prefix)."""

    return bool(name) and name.startswith(T3_PREFIX)


def _parent_table_name(object_: object) -> str | None:
    """Best-effort resolution of the table an index / constraint / column hangs off."""

    for attr in ("table", "parent"):
        parent = getattr(object_, attr, None)
        parent_name = getattr(parent, "name", None)
        if isinstance(parent_name, str):
            return parent_name
    return None


def component3_include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: ARG001 -- deliberately ignored; see module docstring
    compare_to: object | None,  # noqa: ARG001 -- deliberately ignored
) -> bool:
    """Return ``True`` only for schema objects Component 3 owns.

    A non-``t3_`` table is excluded regardless of ``reflected`` or ``compare_to``. A filter
    that only rejects the ``reflected=True`` side still lets ``op.drop_table`` through for a
    table that exists in the database but not in our metadata -- which is every student-app
    table.
    """

    if type_ == "table":
        return owns_table_name(name)

    parent_table = _parent_table_name(object_)
    if parent_table is not None:
        return owns_table_name(parent_table)

    # An object we cannot attribute to a table: exclude it rather than risk emitting a drop.
    return False


# --------------------------------------------------------------------------------------
# Connection-string handling lives in ``db_url`` -- imported above and re-exported so the
# Alembic env and callers keep a single import site. Pooler detection must not be duplicated.
# --------------------------------------------------------------------------------------


def assert_direct_connection(url: str) -> None:
    """Raise if the URL resolves to the transaction pooler. Called before every migration."""

    if is_pooler_url(url):
        raise RuntimeError(
            "Refusing to run Alembic through the Supabase transaction pooler "
            f"({redact_url(url)}). The pooler multiplexes connections and breaks asyncpg "
            "prepared-statement caching; run migrations on the direct connection (port 5432). "
            "See backend_plan.md section 2."
        )
