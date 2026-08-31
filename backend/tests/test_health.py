"""`/health/live` and `/health/ready` -- backend_plan.md section 1 / build order step 1.

`/health/ready` reports model-artefact status only for this work order; a real teacher token
and a database check arrive with later work orders.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ACTIVE_MODEL_VERSION, ARTEFACT_STORE_PATH


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PORT", "8100")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/placeholder")
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

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_reports_loaded_and_verified_artefact(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["model_version"] == ACTIVE_MODEL_VERSION
    assert body["checks"]["model_artefact"] == "loaded_and_verified"
