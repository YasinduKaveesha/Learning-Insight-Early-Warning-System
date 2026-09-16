"""The rails that stand between a Component 3 migration and a dropped production schema.

Runs with no database connection -- that is the point.
"""

from __future__ import annotations

import pytest

from app.infrastructure.migration_guard import (
    assert_direct_connection,
    component3_include_object,
    is_pooler_url,
    normalise_async_url,
    redact_url,
)


class _FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeIndex:
    def __init__(self, table_name: str) -> None:
        self.table = _FakeTable(table_name)


# Representative student-app tables -- none of these are Component 3's to touch.
STUDENT_TABLES = ["b_learners", "classrooms", "app_users", "c_sessions", "alembic_version"]


@pytest.mark.parametrize("name", STUDENT_TABLES)
def test_include_object_excludes_student_tables(name: str) -> None:
    assert component3_include_object(_FakeTable(name), name, "table", True, None) is False
    # ...and on the metadata side of the diff too (reflected=False, compare_to set).
    assert component3_include_object(_FakeTable(name), name, "table", False, object()) is False


def test_include_object_admits_component3_table() -> None:
    assert component3_include_object(_FakeTable("t3_panel"), "t3_panel", "table", True, None) is True


def test_include_object_follows_table_ownership_for_indexes() -> None:
    assert (
        component3_include_object(_FakeIndex("classrooms"), "ix_classrooms_x", "index", True, None)
        is False
    )
    assert (
        component3_include_object(_FakeIndex("t3_panel"), "ix_t3_panel_x", "index", True, None)
        is True
    )


def test_include_object_excludes_unattributable_object() -> None:
    assert component3_include_object(object(), "mystery", "foreign_key", True, None) is False


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db.example.supabase.co:6543/postgres",
        "postgresql+asyncpg://u:p@host:6543/postgres",
        "postgresql://u:p@aws-0-eu-west-2.pooler.supabase.com:6543/postgres",
    ],
)
def test_transaction_pooler_urls_are_refused(url: str) -> None:
    """Port 6543 on ANY host: that is the pooler that breaks prepared statements."""

    assert is_pooler_url(url) is True
    with pytest.raises(RuntimeError, match="pooler"):
        assert_direct_connection(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db.example.supabase.co:5432/postgres",
        # The SESSION pooler (2026-09-16). One server connection per client, so prepared
        # statements work -- and it is the only IPv4 route into a Supabase project on the
        # free plan, which is what migrating to a hosted database depends on.
        "postgresql://u:p@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres",
    ],
)
def test_direct_and_session_pooler_urls_are_allowed(url: str) -> None:
    assert is_pooler_url(url) is False
    assert_direct_connection(url)  # does not raise


def test_normalise_async_url_rewrites_driver_and_strips_sslmode() -> None:
    out = normalise_async_url("postgresql://u:p@h:5432/db?sslmode=require&application_name=t3")
    assert out.startswith("postgresql+asyncpg://")
    assert "sslmode" not in out
    assert "application_name=t3" in out


def test_redact_url_hides_credentials() -> None:
    assert redact_url("postgresql+asyncpg://user:secret@h:5432/db") == "postgresql+asyncpg://***:***@h:5432/db"
    assert "secret" not in redact_url("postgresql+asyncpg://user:secret@h:5432/db")
