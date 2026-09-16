"""`/health/live` and `/health/ready` -- backend_plan.md section 1 / build order step 1.

`/health/ready` now runs two checks: the model artefact (loaded + sha256 verified) and a
real `SELECT 1` against the shared database. Three things are gated here:

* **Gate 3** -- against a real database the endpoint answers 200 and `checks["database"]`
  is present. Needs `T3_LIVE_DB_URL`; skips cleanly without it.
* **Gate 4** -- pointed at a dead port the endpoint answers **503** with
  `detail.stage == "database"`, and the password appears nowhere in the body, the headers,
  or the log records the request emitted. This one needs no database at all, by design:
  the whole point is that nothing is listening.
* The probe must not fail open. `check_database_reachable` re-raises; only the route
  catches, and only to answer 503.

`T3_LIVE_DB_URL` is used read-only here (one `SELECT 1`), but it is still routed through
the B0.1 target guard so this file can never be pointed somewhere it should not be.
"""

from __future__ import annotations

import logging
import os

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ACTIVE_MODEL_VERSION, ARTEFACT_STORE_PATH

#: A password that exists nowhere else in the repo, so "is it in the output?" is an exact
#: string search rather than a judgement call.
_DEAD_PASSWORD = "gate4-unique-p%40ssw0rd"

#: Port 1 is reserved (tcpmux) and nothing listens on it, so the connection is refused
#: immediately rather than hanging until a timeout.
_DEAD_URL = f"postgresql://gate4user:{_DEAD_PASSWORD}@127.0.0.1:1/nosuchdb"

_LIVE_URL = os.environ.get("T3_LIVE_DB_URL")

if _LIVE_URL:
    from tests._live_db_target_guard import assert_safe_and_reachable_live_target

    assert_safe_and_reachable_live_target(_LIVE_URL)


def _make_client(monkeypatch, database_url: str) -> TestClient:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PORT", "8100")
    monkeypatch.setenv("DATABASE_URL", database_url)
    # SET, not deleted. Settings also read `.env`, and a variable absent from the process
    # environment falls back to the file -- so `delenv` left a real `DATABASE_URL_POOLED` in
    # force, the API connected through it, and the "dead database" probe answered ready.
    # That stayed invisible until `.env` first carried a pooled URL (2026-09-16). The API
    # prefers the pooled URL, so it must name the same target as `DATABASE_URL` here.
    monkeypatch.setenv("DATABASE_URL_POOLED", database_url)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://example.supabase.co/auth/v1")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setenv("SUPABASE_JWKS_URL", "https://example.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setenv("SUPABASE_JWKS_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("T3_MODEL_ARTEFACT_PATH", str(ARTEFACT_STORE_PATH))
    monkeypatch.setenv("T3_ACTIVE_MODEL_VERSION", ACTIVE_MODEL_VERSION)

    from app.infrastructure.settings import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def dead_db_client(monkeypatch) -> TestClient:
    """An app whose DATABASE_URL points at a closed port. Gate 4."""

    from app.infrastructure.settings import get_settings

    with _make_client(monkeypatch, _DEAD_URL) as test_client:
        yield test_client

    get_settings.cache_clear()


@pytest.fixture()
def live_db_client(monkeypatch) -> TestClient:
    """An app wired to the real local Postgres. Gate 3."""

    from app.infrastructure.settings import get_settings

    with _make_client(monkeypatch, _LIVE_URL) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_liveness(dead_db_client: TestClient) -> None:
    """Liveness must NOT depend on the database -- it answers with the DB dead."""

    response = dead_db_client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


# --------------------------------------------------------------------------------------
# Gate 4: the database probe fails CLOSED, and leaks nothing.
# --------------------------------------------------------------------------------------
def test_readiness_is_503_with_stage_database_when_the_db_is_unreachable(
    dead_db_client: TestClient, caplog
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = dead_db_client.get("/health/ready")

    assert response.status_code == 503, (
        "the readiness probe failed OPEN -- it swallowed the connection error and "
        "reported ready against a database that is not there"
    )
    body = response.json()
    assert body["detail"]["stage"] == "database"
    assert body["detail"]["error"]  # a reason, not an empty string

    # The password must not survive anywhere the operator or a log shipper can see it.
    print("\n[gate 4] /health/ready ->", response.status_code, response.text)

    assert _DEAD_PASSWORD not in response.text
    assert _DEAD_PASSWORD not in str(dict(response.headers))
    for record in caplog.records:
        assert _DEAD_PASSWORD not in record.getMessage()
        assert _DEAD_PASSWORD not in str(getattr(record, "error", ""))


def test_readiness_never_reports_ready_while_the_db_is_down(dead_db_client) -> None:
    """The artefact loads fine here, so a fail-open probe would answer 200 `ready`."""

    body = dead_db_client.get("/health/ready").json()
    assert body.get("status") != "ready"
    assert "checks" not in body


def test_check_database_reachable_raises_rather_than_returning(dead_db_client) -> None:
    """The probe helper itself must re-raise; only the route may catch."""

    import asyncio

    from app.infrastructure.db import engine as db_engine

    with pytest.raises(Exception) as excinfo:
        asyncio.run(db_engine.check_database_reachable())
    assert not isinstance(excinfo.value, AssertionError)


# --------------------------------------------------------------------------------------
# Gate 3: against the real database, 200 with a `database` check.
# --------------------------------------------------------------------------------------
@pytest.mark.skipif(
    not _LIVE_URL,
    reason="set T3_LIVE_DB_URL to a direct (5432) Postgres URL to run the readiness DB gate",
)
def test_readiness_is_200_with_a_database_check_against_a_real_db(
    live_db_client: TestClient,
) -> None:
    response = live_db_client.get("/health/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["model_version"] == ACTIVE_MODEL_VERSION
    assert body["checks"]["model_artefact"] == "loaded_and_verified"
    assert body["checks"]["database"] == "select_1_ok"
    print("\n[gate 3] /health/ready ->", response.status_code, response.text)
