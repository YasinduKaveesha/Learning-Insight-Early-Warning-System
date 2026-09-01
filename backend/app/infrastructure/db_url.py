"""Canonical Postgres connection-string handling for Component 3.

One place that knows how to turn whatever ``DATABASE_URL`` the environment hands us into a
URL asyncpg will accept, how to recognise the Supabase transaction pooler, and how to print
a URL without leaking credentials. ``migration_guard`` and the Alembic env both import from
here so pooler detection cannot drift between the two.

Holds no connection and is import-safe without a database.

Two consumers, two entry points:

* **Alembic / the loader** call :func:`normalise_async_url` -- they want a plain URL string
  and run on the *direct* connection (port 5432). :func:`assert_direct_connection` (in
  ``migration_guard``) refuses the pooler outright.
* **The API engine** calls :func:`normalise_database_url`, which returns a
  :class:`NormalisedUrl`: the async URL *plus* the asyncpg ``connect_args`` and the
  prepared-statement-cache kwargs, because on the API path ``sslmode=require`` must become
  an unverified ``ssl.SSLContext`` and the pooler must disable prepared-statement caching.
  See backend_plan.md section 2, "Two connection-string traps".

Both entry points route every ``sslmode`` value through the one :func:`_ssl_for_sslmode`,
so the two can no longer disagree about what ``require`` means (work order B2.2). They
differ only in what they can *carry*: a string URL cannot hold an ``ssl.SSLContext``, so
the string form passes the mode name to asyncpg, which builds an equivalent context.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_ASYNC_SCHEME = "postgresql+asyncpg"

#: Schemes we rewrite to the asyncpg driver. Anything already ``+asyncpg`` is left alone.
_REWRITE_SCHEMES = frozenset(
    {"postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"}
)

#: libpq query parameters asyncpg does not understand and would raise ``TypeError`` on.
#: ``sslmode`` is handled specially (translated, not just dropped); the rest are noise.
_LIBPQ_ONLY_PARAMS = frozenset(
    {"sslmode", "target_session_attrs", "gssencmode", "channel_binding"}
)

#: Supabase pooler signals (backend_plan.md section 2).
_POOLER_PORT = 6543
_POOLER_HOST_MARKER = "pooler"


def normalise_async_url(url: str) -> str:
    """Return ``url`` with the asyncpg driver forced and libpq-only params removed.

    * ``postgres`` / ``postgresql`` / ``+psycopg2`` / ``+psycopg`` schemes become
      ``postgresql+asyncpg``; an already-async scheme is untouched.
    * ``sslmode`` is validated by the shared :func:`_ssl_for_sslmode` and then carried
      through as asyncpg's ``ssl`` query parameter under its own libpq name --
      ``sslmode=require`` becomes ``ssl=require``, not ``ssl=true`` -- unless the URL
      already carries an explicit ``ssl``. An unrecognised value raises
      :class:`InvalidDatabaseUrl` without echoing it.
    * Other libpq-only params (``target_session_attrs`` etc.) are dropped: asyncpg raises
      ``TypeError: connect() got an unexpected keyword argument`` on them.
    * Every other query parameter (``application_name``, ...) is preserved in order.

    This is the string-only form used for the *direct* (port 5432) connection Alembic and
    the loader run on -- Alembic's ``env.py`` hands SQLAlchemy nothing but this string, so
    it has to be self-sufficient; it cannot carry an ``ssl.SSLContext`` object. The API
    engine wants :func:`normalise_database_url` instead, which returns real connect args.

    **Both entry points now agree** (work order B2.2). This function used to map every
    non-``disable`` mode to ``ssl=true``, which asked for full chain *and hostname*
    verification where libpq's ``require`` means "encrypt, do not verify"; against the
    Supabase pooler that fails with ``CERTIFICATE_VERIFY_FAILED``, an error that reads
    like a credentials problem. (``ssl=true`` was in fact doubly wrong: asyncpg parses a
    string ``ssl`` as an sslmode name and rejects ``"true"`` outright with
    ``ClientConfigurationError: `sslmode` parameter must be one of: ...``. It has never
    fired because the live URL carries no ``sslmode``.) asyncpg's ``ssl`` accepts exactly
    the libpq vocabulary :func:`_ssl_for_sslmode` validates, and derives
    ``check_hostname`` from it the same way, so passing the mode name through keeps one
    meaning for one word.
    """

    parts = urlsplit(url)

    scheme = _ASYNC_SCHEME if parts.scheme in _REWRITE_SCHEMES else parts.scheme

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    has_ssl = any(k == "ssl" for k, _ in pairs)

    query: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == "sslmode":
            # Validate through the SAME function the API path uses, so a value this
            # project accepts on one entry point cannot be refused on the other, and a
            # nonsense value raises identically (without echoing it) on both.
            mode = value.strip().lower()
            _ssl_for_sslmode(mode)
            if not has_ssl:
                query.append(("ssl", mode))
            continue
        if key in _LIBPQ_ONLY_PARAMS:
            continue
        query.append((key, value))

    return urlunsplit(
        (scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def is_pooler_url(url: str) -> bool:
    """True if the URL points at the Supabase transaction pooler.

    Signalled by port ``6543`` or a ``pooler`` hostname. The pooler multiplexes connections
    and breaks asyncpg prepared-statement caching, so migrations must not run through it.
    """

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return port == _POOLER_PORT or _POOLER_HOST_MARKER in host


def redact_url(url: str) -> str:
    """``scheme://***:***@host:port/db`` -- safe to print or log."""

    parts = urlsplit(url)
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    auth = "***:***@" if (parts.username or parts.password) else ""
    return f"{parts.scheme}://{auth}{host}{port}{parts.path}"


# ======================================================================================
# The API-engine entry point (backend_plan.md section 2).
# ======================================================================================

# Full set of libpq-only query parameters asyncpg's ``connect()`` rejects as keyword
# arguments -- a URL that works in ``psql`` raises
# ``TypeError: connect() got an unexpected keyword argument '<name>'``. We translate
# ``sslmode`` (below) and strip the rest rather than forward them blindly (rule 4):
#
#   sslmode          -- translated to the ``ssl`` connect arg, then removed
#   sslcert          -- client-cert auth; asyncpg wants an ssl.SSLContext instead
#   sslkey           -- "
#   sslrootcert      -- "
#   sslcrl           -- "
#   sslcompression   -- libpq TLS-compression toggle; no asyncpg equivalent
#   sslsni           -- libpq SNI toggle; asyncpg always sends SNI
#   gssencmode       -- GSSAPI encryption negotiation; asyncpg has no GSS transport
#   krbsrvname       -- Kerberos service name; same
#   channel_binding  -- libpq SCRAM channel-binding preference; not an asyncpg kwarg
#   target_session_attrs -- libpq multi-host read/write routing; not an asyncpg kwarg
_API_STRIP_PARAMS = frozenset(
    {
        "sslmode",
        "sslcert",
        "sslkey",
        "sslrootcert",
        "sslcrl",
        "sslcompression",
        "sslsni",
        "gssencmode",
        "krbsrvname",
        "channel_binding",
        "target_session_attrs",
    }
)


class InvalidDatabaseUrl(ValueError):
    """``DATABASE_URL`` could not be normalised. The message never contains the password."""


@dataclass(frozen=True)
class NormalisedUrl:
    """Result of :func:`normalise_database_url`.

    * ``async_url``       -- the ``postgresql+asyncpg://`` URL, libpq-only params stripped.
    * ``connect_args``    -- for ``create_async_engine(..., connect_args=...)``; may carry
                             ``ssl`` and ``statement_cache_size``.
    * ``dialect_kwargs``  -- carries ``prepared_statement_cache_size`` when a pooler is
                             detected. NOTE: despite the name this is a *DBAPI* argument in
                             SQLAlchemy's asyncpg dialect, so it must be merged into
                             ``connect_args`` (or put in the URL query), never passed to
                             ``create_async_engine`` as a keyword -- that raises
                             ``TypeError: Invalid argument(s)``. ``db/engine.py`` merges it.
                             Kept in its own bucket because it configures SQLAlchemy's
                             statement-cache emulation, a different cache from asyncpg's
                             own ``statement_cache_size``.
    * ``pooler_detected`` -- so the caller can log that the pooler path is in use.
    """

    async_url: str = field(repr=False)  # carries the password; see __repr__
    connect_args: dict[str, object]
    dialect_kwargs: dict[str, object]
    pooler_detected: bool

    def __repr__(self) -> str:
        return (
            f"NormalisedUrl(async_url={redact_url(self.async_url)!r}, "
            f"connect_args_keys={sorted(self.connect_args)}, "
            f"dialect_kwargs={self.dialect_kwargs!r}, "
            f"pooler_detected={self.pooler_detected})"
        )


def _ssl_for_sslmode(sslmode: str) -> object:
    """Translate a libpq ``sslmode`` value to asyncpg's ``ssl`` connect argument.

    Do NOT collapse ``require`` to ``ssl=True``. libpq's ``require`` means *encrypt, do not
    verify*; ``ssl=True`` verifies both the certificate chain and the hostname and fails
    against the Supabase pooler with ``CERTIFICATE_VERIFY_FAILED`` -- an error that reads
    like a credentials problem and sends the next engineer looking in entirely the wrong
    place (backend_plan.md section 2, trap 1).
    """

    normalised = sslmode.strip().lower()

    if normalised in {"disable", "allow", "prefer"}:
        # disable = no TLS; allow/prefer = opportunistic. ssl=False still lets the server
        # upgrade the connection if it insists, so it is safe for all three, and we do not
        # force TLS the operator did not ask for.
        return False

    if normalised == "require":
        # encrypt, do not verify anything.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    if normalised == "verify-ca":
        # verify the chain, but not that the hostname matches the certificate.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
        return ctx

    if normalised == "verify-full":
        # verify the chain AND the hostname -- the one case ssl=True is correct.
        return True

    # Do not echo the value -- it is attacker/operator-controlled and could be a secret.
    raise InvalidDatabaseUrl(
        "unrecognised sslmode value (expected one of: disable, allow, prefer, require, "
        "verify-ca, verify-full)"
    )


def normalise_database_url(url: str) -> NormalisedUrl:
    """Normalise ``DATABASE_URL`` for the API's SQLAlchemy async + asyncpg engine.

    Pure: no I/O, no engine, no connection. See the module docstring for how this differs
    from :func:`normalise_async_url`.
    """

    if not isinstance(url, str) or not url.strip():
        raise InvalidDatabaseUrl("DATABASE_URL is empty")

    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:  # pragma: no cover - urlsplit rarely raises
        raise InvalidDatabaseUrl(f"could not parse {redact_url(url)}: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme in _REWRITE_SCHEMES:
        new_scheme = _ASYNC_SCHEME
    elif scheme == _ASYNC_SCHEME:
        new_scheme = _ASYNC_SCHEME
    else:
        raise InvalidDatabaseUrl(
            f"unsupported scheme {parts.scheme!r} in {redact_url(url)}; "
            "expected postgresql://, postgres:// or postgresql+asyncpg://"
        )

    connect_args: dict[str, object] = {}
    dialect_kwargs: dict[str, object] = {}

    kept_params: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered == "sslmode":
            connect_args["ssl"] = _ssl_for_sslmode(value)
            continue
        if lowered in _API_STRIP_PARAMS:
            continue
        kept_params.append((key, value))

    new_query = urlencode(kept_params)

    pooler_detected = is_pooler_url(url)
    if pooler_detected:
        # The transaction pooler multiplexes many clients onto few connections and breaks
        # asyncpg's prepared-statement cache. Symptom: an INTERMITTENT
        # ``prepared statement "__asyncpg_stmt_x__" does not exist`` under concurrency --
        # not a clean startup failure. Disable BOTH caches (section 2, trap 2).
        connect_args["statement_cache_size"] = 0
        dialect_kwargs["prepared_statement_cache_size"] = 0

    async_url = urlunsplit(
        (new_scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )

    return NormalisedUrl(
        async_url=async_url,
        connect_args=connect_args,
        dialect_kwargs=dialect_kwargs,
        pooler_detected=pooler_detected,
    )
