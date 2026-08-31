"""Safety gate for T3_LIVE_DB_URL (work order B0.1).

This project has already had a shared database wiped once by a test run pointed at the
wrong target. The four live-DB test files (`test_t3_live_schema`, `test_t3_loader`,
`test_t3_predictions_live`, `test_t3_recommendations_live`) all mutate data -- inserts,
downgrades/upgrades, or rely on rollback discipline elsewhere in the suite -- so a run must
refuse outright rather than proceed against anything but the disposable test database.

Reuses `is_pooler_url` / `redact_url` from `app.infrastructure.db_url` (the same functions
`migration_guard` uses) rather than re-implementing pooler detection -- see backend_plan.md
section 2 and Agent Handower/BACKEND_SUPERVISOR_HANDOVER.md section 6 for why the pooler is
refused for anything migration/DDL-adjacent.

Import-safe without a database and without SQLAlchemy installed: `urlsplit` is stdlib, and
the only optional import (`app.infrastructure.db_url`) is wrapped so this module still loads
in the pinned `c3-ews` env before the DB deps are installed -- the four live test files
already `pytest.importorskip("sqlalchemy")` / `("asyncpg")` before they would call
`assert_safe_live_target`, so that path never runs without the dependency anyway, but the
import itself must not explode the collection phase.
"""

from __future__ import annotations

import socket
import sys
from urllib.parse import urlsplit

#: The only database this project's live tests may target. Never `upadya`, never a
#: Supabase project database reached directly.
_ALLOWED_DB_NAME = "upadya_test"


class UnsafeLiveDbTarget(RuntimeError):
    """T3_LIVE_DB_URL does not point at the disposable test database. Refuse to proceed."""


class LiveDbUnreachable(RuntimeError):
    """T3_LIVE_DB_URL names a valid, safe target, but nothing answers on host:port.

    Work order B4.1: the local Docker DB publishes its port only through an opt-in
    docker-compose override (`docker/compose.c3-test-db.yaml`); a plain `docker compose up`
    run by the student-app team does not publish it. That is a reason unrelated to Component
    3, so it must SKIP the live-db suite, never fail it, the way a wrong/unsafe target
    (caught by :func:`assert_safe_live_target` above) correctly does.
    """


def _redact(url: str) -> str:
    try:
        from app.infrastructure.db_url import redact_url

        return redact_url(url)
    except Exception:
        parts = urlsplit(url)
        host = parts.hostname or "?"
        port = f":{parts.port}" if parts.port else ""
        auth = "***:***@" if (parts.username or parts.password) else ""
        return f"{parts.scheme}://{auth}{host}{port}{parts.path}"


def _is_pooler(url: str) -> bool:
    try:
        from app.infrastructure.db_url import is_pooler_url

        return is_pooler_url(url)
    except Exception:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        try:
            port = parts.port
        except ValueError:
            port = None
        return port == 6543 or "pooler" in host


def assert_safe_live_target(url: str) -> None:
    """Raise :class:`UnsafeLiveDbTarget` unless ``url`` is a direct connection to
    ``upadya_test``. Always prints the REDACTED host/db (never the password) first, so a
    refusal and an approval are equally visible in test output.

    Call this once, before any live test in a module executes -- e.g. from the module's
    ``pytest.fixture(scope="module", autouse=True)`` or right after the `T3_LIVE_DB_URL`
    skip check, while the URL is still known to be set.
    """

    redacted = _redact(url)
    sys.stderr.write(f"\n[B0.1 live-db guard] T3_LIVE_DB_URL target: {redacted}\n")
    sys.stderr.flush()

    parts = urlsplit(url)
    db_name = (parts.path or "/").lstrip("/")

    if _is_pooler(url):
        raise UnsafeLiveDbTarget(
            f"T3_LIVE_DB_URL ({redacted}) resolves to the Supabase transaction pooler "
            "(port 6543 or a 'pooler' host). Live DB tests must run on a direct connection. "
            "Refusing to proceed."
        )

    if db_name != _ALLOWED_DB_NAME:
        raise UnsafeLiveDbTarget(
            f"T3_LIVE_DB_URL ({redacted}) names database {db_name!r}, not the disposable "
            f"{_ALLOWED_DB_NAME!r} test database. This project has already had a shared "
            "database wiped once by a misdirected test run. Refusing to proceed."
        )


def check_live_target_reachable(url: str, *, timeout: float = 2.0) -> None:
    """Raise :class:`LiveDbUnreachable` if nothing accepts a TCP connection at ``url``'s
    host/port. Call only AFTER :func:`assert_safe_live_target` has already approved the
    target -- this function does not repeat the name/pooler checks, it only tests whether the
    (already-approved) target is currently listening.
    """

    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 5432
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as exc:
        redacted = _redact(url)
        raise LiveDbUnreachable(
            f"T3_LIVE_DB_URL ({redacted}) is a valid, safe target, but nothing is listening "
            f"on {host}:{port} ({exc}). This is the c3-test-db docker-compose override port "
            "(README 'Live database gates' step 2) -- published only while that override "
            "file is passed to `docker compose up`. Skipping the live-db tests rather than "
            "failing the suite for a reason unrelated to Component 3."
        ) from exc


def assert_safe_and_reachable_live_target(url: str) -> None:
    """The guard every live test module should call: refuse loudly on a wrong/unsafe target
    (calls :func:`assert_safe_live_target` -- unchanged, still a hard failure), then SKIP the
    whole module (not fail it) if the target is safe but simply unreachable right now.

    Must be called at module level (not inside a test function) so the ``pytest.skip`` is
    ``allow_module_level=True``, matching how the existing ``pytestmark_live`` skip already
    behaves for a module without ``T3_LIVE_DB_URL`` set at all.
    """

    assert_safe_live_target(url)
    try:
        check_live_target_reachable(url)
    except LiveDbUnreachable as exc:
        import pytest

        pytest.skip(str(exc), allow_module_level=True)
