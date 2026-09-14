"""T3_DEMO_MODE / T3_DEMO_TEACHER_POOL settings (work order B2.3, gate 8 and 13-adjacent).

Fully self-contained -- constructs `Settings` directly from a kwargs dict rather than reading
`.env` or environment variables, so this suite is independent of whatever the developer's
shell happens to have set. No database, no network.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.infrastructure.settings import Settings

_REQUIRED_BASE_KWARGS = dict(
    APP_ENV="local",
    API_PORT=8100,
    DATABASE_URL="postgresql://user:pass@localhost:5432/placeholder",
    CORS_ALLOWED_ORIGINS="http://localhost:5173",
    SUPABASE_URL="https://example.supabase.co",
    SUPABASE_JWT_ISSUER="https://example.supabase.co/auth/v1",
    SUPABASE_JWT_AUDIENCE="authenticated",
    SUPABASE_JWKS_URL="https://example.supabase.co/auth/v1/.well-known/jwks.json",
    SUPABASE_JWKS_CACHE_TTL_SECONDS=300,
    T3_MODEL_ARTEFACT_PATH="./artefacts",
    T3_ACTIVE_MODEL_VERSION="1.0.0",
)


def _settings(**overrides) -> Settings:
    kwargs = {**_REQUIRED_BASE_KWARGS, **overrides}
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


# ==========================================================================================
# Gate 8 -- T3_DEMO_MODE=true with APP_ENV=production refuses to start.
# ==========================================================================================


def test_gate8_demo_mode_in_production_refuses_to_start() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _settings(APP_ENV="production", T3_DEMO_MODE=True)
    assert "T3_DEMO_MODE=true is refused when APP_ENV=production" in str(excinfo.value)


def test_demo_mode_in_local_is_accepted() -> None:
    settings = _settings(APP_ENV="local", T3_DEMO_MODE=True)
    assert settings.t3_demo_mode is True


def test_demo_mode_off_in_production_is_accepted() -> None:
    settings = _settings(APP_ENV="production", T3_DEMO_MODE=False)
    assert settings.t3_demo_mode is False


def test_demo_mode_defaults_false() -> None:
    settings = _settings()
    assert settings.t3_demo_mode is False
    assert settings.t3_demo_teacher_pool == []


# ==========================================================================================
# T3_DEMO_TEACHER_POOL parsing.
# ==========================================================================================


def test_demo_teacher_pool_parses_comma_separated_uuids() -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    settings = _settings(T3_DEMO_TEACHER_POOL=f"{a}, {b}")
    assert settings.t3_demo_teacher_pool == [a, b]


def test_demo_teacher_pool_rejects_non_uuid_entry() -> None:
    with pytest.raises(ValidationError):
        _settings(T3_DEMO_TEACHER_POOL="not-a-uuid")


def test_demo_teacher_pool_empty_string_is_empty_list() -> None:
    settings = _settings(T3_DEMO_TEACHER_POOL="")
    assert settings.t3_demo_teacher_pool == []
