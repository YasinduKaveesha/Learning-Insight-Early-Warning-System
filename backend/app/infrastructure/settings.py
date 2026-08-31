"""Environment-backed settings for the Component 3 backend.

Fails fast at import/startup time (via `get_settings()`) rather than on first request --
see backend_plan.md section 2.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator
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
