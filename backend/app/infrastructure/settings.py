"""Environment-backed settings for the Component 3 backend.

Fails fast at import/startup time (via `get_settings()`) rather than on first request --
see backend_plan.md section 2.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Operational settings. No scientific or learner-policy defaults live here."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(validation_alias="APP_ENV")
    api_port: int = Field(validation_alias="API_PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # Two URLs by design (backend_plan.md section 2): migrations and the loader run on the
    # direct connection (port 5432); the API runs on the transaction pooler (port 6543).
    database_url: str = Field(validation_alias="DATABASE_URL")
    database_url_pooled: str | None = Field(
        default=None, validation_alias="DATABASE_URL_POOLED"
    )
    # NoDecode: pydantic-settings otherwise JSON-decodes complex-typed fields from the raw env
    # string before any field_validator runs, which would reject a plain comma-separated list.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        validation_alias="CORS_ALLOWED_ORIGINS"
    )

    supabase_url: AnyHttpUrl = Field(validation_alias="SUPABASE_URL")
    supabase_jwt_issuer: str = Field(validation_alias="SUPABASE_JWT_ISSUER")
    supabase_jwt_audience: str = Field(validation_alias="SUPABASE_JWT_AUDIENCE")
    supabase_jwks_url: AnyHttpUrl = Field(validation_alias="SUPABASE_JWKS_URL")
    supabase_jwks_cache_ttl_seconds: int = Field(validation_alias="SUPABASE_JWKS_CACHE_TTL_SECONDS")

    t3_model_artefact_path: str = Field(validation_alias="T3_MODEL_ARTEFACT_PATH")
    t3_active_model_version: str = Field(validation_alias="T3_ACTIVE_MODEL_VERSION")

    # Demo-mode identity (work order B2.3). Both default to "off" / empty so a deployment
    # that never sets either env var behaves exactly like today. See the fail-fast rule
    # below: T3_DEMO_MODE=true is refused outright when APP_ENV=production.
    t3_demo_mode: bool = Field(default=False, validation_alias="T3_DEMO_MODE")

    # 2026-09-16: load the active run's predictions and panel into `run_cache` in the
    # background as the API starts, so the first teacher does not pay for it. Off by default:
    # a process that starts with no database (every TestClient) must not reach for one.
    t3_cache_warm_on_startup: bool = Field(
        default=False, validation_alias="T3_CACHE_WARM_ON_STARTUP"
    )
    t3_demo_teacher_pool: Annotated[list[str], NoDecode] = Field(
        default="", validation_alias="T3_DEMO_TEACHER_POOL"
    )

    # CompD's "Generate with AI" (owner direction 2026-10-21: the dashboard serves compD
    # itself). Optional: unset, the drafts route answers 503 and every other CompD route
    # works. Never logged or returned.
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if not origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must not be empty")
            if "*" in origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must never be '*'")
            return origins
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("t3_demo_teacher_pool", mode="before")
    @classmethod
    def _split_demo_teacher_pool(cls, value: object) -> object:
        if isinstance(value, str):
            ids = [entry.strip() for entry in value.split(",") if entry.strip()]
            for entry in ids:
                try:
                    uuid.UUID(entry)
                except ValueError as exc:
                    raise ValueError(
                        f"T3_DEMO_TEACHER_POOL entry {entry!r} is not a valid UUID"
                    ) from exc
            return ids
        return value

    @model_validator(mode="after")
    def _demo_mode_never_in_production(self) -> "Settings":
        """Fail app startup entirely -- not a warning -- if demo mode could ever run in
        production (B2.3 hard rule). `get_settings()` is the fail-fast boundary this raises
        through; `app/main.py` calls it before the app object is even constructed."""

        if self.t3_demo_mode and self.app_env == "production":
            raise ValueError(
                "T3_DEMO_MODE=true is refused when APP_ENV=production. Demo mode maps an "
                "anonymous Supabase subject onto a real teacher's data and must be "
                "impossible to accidentally leave on in production."
            )
        return self

    @property
    def api_database_url(self) -> str:
        """The URL the API engine should use: the pooled one, or the direct one with a
        logged notice when `DATABASE_URL_POOLED` is unset. No engine is wired here."""

        if self.database_url_pooled:
            return self.database_url_pooled
        logging.getLogger(__name__).info(
            "DATABASE_URL_POOLED is unset; the API will use the direct DATABASE_URL "
            "(no transaction pooler). Set DATABASE_URL_POOLED (port 6543) in production."
        )
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process. Raises `pydantic.ValidationError` if a required
    variable is missing or invalid -- this is the fail-fast boundary."""

    return Settings()  # type: ignore[call-arg]
