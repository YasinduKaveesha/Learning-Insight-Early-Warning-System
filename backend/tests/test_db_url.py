"""Connection-string normalisation -- backend_plan.md section 2, "Two connection-string traps".

Table-driven over synthetic URLs. The live DATABASE_URL today is a direct port-5432 URL with
no query parameters, so neither trap fires on the current value -- these fixtures are
deliberately synthetic. The code is not unnecessary because the current URL happens to work.

No database connection is opened anywhere in this module.
"""

from __future__ import annotations

import ssl

import pytest

from app.infrastructure.db_url import (
    InvalidDatabaseUrl,
    NormalisedUrl,
    normalise_database_url,
)

_PW = "s3cr3t-p@ss"
_BASE = f"postgresql://appuser:{_PW}@db.example.supabase.co:5432/postgres"


# --------------------------------------------------------------------------------------
# Scheme handling
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("url", "expected_prefix"),
    [
        (f"postgresql://u:{_PW}@h:5432/db", "postgresql+asyncpg://"),
        (f"postgres://u:{_PW}@h:5432/db", "postgresql+asyncpg://"),
        (f"postgresql+asyncpg://u:{_PW}@h:5432/db", "postgresql+asyncpg://"),
    ],
)
def test_scheme_is_rewritten_or_passed_through(url: str, expected_prefix: str) -> None:
    result = normalise_database_url(url)
    assert result.async_url.startswith(expected_prefix)


@pytest.mark.parametrize(
    "url",
    [
        "mysql://u:p@h:3306/db",
        "sqlite:///./local.db",
        "http://example.com",
        "",
        "   ",
    ],
)
def test_non_postgres_scheme_raises(url: str) -> None:
    with pytest.raises(InvalidDatabaseUrl):
        normalise_database_url(url)


# --------------------------------------------------------------------------------------
# sslmode translation -- every value in the plan's table
# --------------------------------------------------------------------------------------
def _ssl_arg(url: str) -> object:
    return normalise_database_url(url).connect_args["ssl"]


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_sslmode_opportunistic_modes_become_ssl_false(mode: str) -> None:
    assert _ssl_arg(f"{_BASE}?sslmode={mode}") is False


def test_sslmode_require_is_an_unverified_context_not_ssl_true() -> None:
    """The specific mistake this function exists to prevent (backend_plan.md section 2).

    libpq's `require` means 'encrypt, do not verify'. `ssl=True` verifies chain AND
    hostname and fails against the Supabase pooler with CERTIFICATE_VERIFY_FAILED -- an
    error that reads like a credentials problem. If someone simplifies this later, this
    test fails loudly.
    """

    ssl_arg = _ssl_arg(f"{_BASE}?sslmode=require")

    assert ssl_arg is not True
    assert isinstance(ssl_arg, ssl.SSLContext)
    assert ssl_arg.check_hostname is False
    assert ssl_arg.verify_mode is ssl.CERT_NONE


def test_sslmode_verify_ca_verifies_chain_but_not_hostname() -> None:
    ssl_arg = _ssl_arg(f"{_BASE}?sslmode=verify-ca")

    assert isinstance(ssl_arg, ssl.SSLContext)
    assert ssl_arg.check_hostname is False
    assert ssl_arg.verify_mode is ssl.CERT_REQUIRED


def test_sslmode_verify_full_is_ssl_true() -> None:
    assert _ssl_arg(f"{_BASE}?sslmode=verify-full") is True


def test_unknown_sslmode_value_raises() -> None:
    with pytest.raises(InvalidDatabaseUrl):
        normalise_database_url(f"{_BASE}?sslmode=banana")


def test_sslmode_is_stripped_from_the_async_url() -> None:
    result = normalise_database_url(f"{_BASE}?sslmode=require")
    assert "sslmode" not in result.async_url


# --------------------------------------------------------------------------------------
# Pooler detection -- both signals
# --------------------------------------------------------------------------------------
def test_pooler_detected_by_port_6543() -> None:
    result = normalise_database_url(
        f"postgresql://u:{_PW}@db.example.supabase.co:6543/postgres"
    )
    assert result.pooler_detected is True
    assert result.connect_args["statement_cache_size"] == 0
    assert result.dialect_kwargs["prepared_statement_cache_size"] == 0


def test_pooler_detected_by_pooler_hostname() -> None:
    result = normalise_database_url(
        f"postgresql://u:{_PW}@aws-0-eu-west-2.pooler.supabase.com:5432/postgres"
    )
    assert result.pooler_detected is True
    assert result.connect_args["statement_cache_size"] == 0
    assert result.dialect_kwargs["prepared_statement_cache_size"] == 0


def test_direct_url_has_no_pooler_flag_and_no_cache_kwargs() -> None:
    result = normalise_database_url(_BASE)
    assert result.pooler_detected is False
    assert "statement_cache_size" not in result.connect_args
    assert result.dialect_kwargs == {}


# --------------------------------------------------------------------------------------
# Query-parameter handling -- strip some, keep others
# --------------------------------------------------------------------------------------
def test_only_libpq_only_params_are_stripped() -> None:
    url = (
        f"{_BASE}?sslmode=require&channel_binding=prefer&target_session_attrs=read-write"
        "&application_name=t3-api&options=-c%20statement_timeout%3D0"
    )
    result = normalise_database_url(url)

    for stripped in ("sslmode", "channel_binding", "target_session_attrs"):
        assert stripped not in result.async_url
    # non-libpq params survive untouched
    assert "application_name=t3-api" in result.async_url
    assert "options=" in result.async_url


# --------------------------------------------------------------------------------------
# Password must never leak
# --------------------------------------------------------------------------------------
def test_password_absent_from_repr_and_raised_messages() -> None:
    # repr of a successful result
    ok = normalise_database_url(f"{_BASE}?sslmode=require")
    assert _PW not in repr(ok)

    # every error path
    for bad in (
        f"mysql://u:{_PW}@h:3306/db",
        f"{_BASE}?sslmode={_PW}",  # bogus sslmode value that is the password itself
    ):
        with pytest.raises(InvalidDatabaseUrl) as excinfo:
            normalise_database_url(bad)
        assert _PW not in str(excinfo.value)


def test_password_is_still_present_in_the_async_url_itself() -> None:
    # the async_url is the real connection string -- it must keep the password; only
    # repr / logs / errors redact it.
    result = normalise_database_url(_BASE)
    assert _PW in result.async_url
    assert isinstance(result, NormalisedUrl)
