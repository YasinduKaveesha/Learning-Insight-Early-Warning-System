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

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
# Connection-string handling. Full normalisation (ssl translation, pooler cache disabling)
# lands with the database work order; B3.1 needs only the driver rewrite, the sslmode strip
# so asyncpg does not choke, and the pooler refusal.
# --------------------------------------------------------------------------------------

_ASYNC_SCHEME = "postgresql+asyncpg"


def normalise_async_url(url: str) -> str:
    """Force the asyncpg driver and drop the libpq-only ``sslmode`` query parameter.

    ``sslmode`` is valid in ``psql`` but asyncpg raises ``TypeError: connect() got an
    unexpected keyword argument 'sslmode'`` on it (backend_plan.md section 2).
    """

    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
        scheme = _ASYNC_SCHEME
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "sslmode"]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def is_pooler_url(url: str) -> bool:
    """True if the URL points at the Supabase transaction pooler (port 6543 / ``pooler`` host)."""

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return port == 6543 or "pooler" in host


def redact_url(url: str) -> str:
    """``scheme://***:***@host:port/db`` -- safe to print."""

    parts = urlsplit(url)
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    auth = "***:***@" if (parts.username or parts.password) else ""
    return f"{parts.scheme}://{auth}{host}{port}{parts.path}"


def assert_direct_connection(url: str) -> None:
    """Raise if the URL resolves to the transaction pooler. Called before every migration."""

    if is_pooler_url(url):
        raise RuntimeError(
            "Refusing to run Alembic through the Supabase transaction pooler "
            f"({redact_url(url)}). The pooler multiplexes connections and breaks asyncpg "
            "prepared-statement caching; run migrations on the direct connection (port 5432). "
            "See backend_plan.md section 2."
        )
