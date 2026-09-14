"""The class-key endpoint (B7 / B6.4; D1) -- offline.

The rule this suite exists for: **a class key is minted once and never changes.** A rotated key
locks out every child who wrote the old one down, so the endpoint must be idempotent, must have no
PUT/PATCH/DELETE sibling, and must refuse a classroom the caller does not own BEFORE writing
anything.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.application import class_key_service
from app.domain.dashboard import DISCLOSURE
from app.domain.principal import Principal
from tests.test_dashboard_api import CLASSROOM, TEACHER, _set_env

KEY_ROUTE = f"/api/v1/t3/classes/{CLASSROOM}/key"


@pytest.fixture
def client(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    app = create_app()

    async def _principal():
        return Principal(teacher_profile_id=TEACHER, resolution="demo")

    async def _session():
        yield None

    app.dependency_overrides[dependencies.current_principal] = _principal
    app.dependency_overrides[dependencies.db_session] = _session
    with TestClient(app) as test_client:
        yield test_client


def test_the_endpoint_returns_the_key_and_the_disclosure(client, monkeypatch):
    async def _ensure(_session, teacher, classroom, invite_token=None):
        assert (teacher, classroom) == (TEACHER, CLASSROOM)
        # Reading a key back sends no body, so the route passes no token.
        assert invite_token is None
        return "M7KP4X9D"

    monkeypatch.setattr(class_key_service, "ensure_class_key", _ensure)
    response = client.post(KEY_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert body["class_key"] == "M7KP4X9D"
    assert body["classroom_id"] == str(CLASSROOM)
    assert body["disclosure"] == DISCLOSURE


def test_a_classroom_the_teacher_does_not_own_is_403(client, monkeypatch):
    async def _ensure(*_args, **_kwargs):
        raise class_key_service.ClassroomNotVisibleError("x")

    monkeypatch.setattr(class_key_service, "ensure_class_key", _ensure)
    assert client.post(KEY_ROUTE).status_code == 403


def test_the_route_requires_a_principal(monkeypatch):
    _set_env(monkeypatch)
    from app.main import create_app

    with TestClient(create_app()) as bare:
        assert bare.post(KEY_ROUTE).status_code in (401, 403)


def test_there_is_no_rotate_or_delete_route(monkeypatch):
    """D1. A key is permanent: no PUT, PATCH or DELETE may exist on it, and GET does not mint."""

    _set_env(monkeypatch)
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    key_paths = {p: set(ops) for p, ops in paths.items() if p.endswith("/key")}
    assert key_paths == {"/api/v1/t3/classes/{classroom_id}/key": {"post"}}


def test_the_service_never_rotates_an_existing_key():
    """The ownership guard passes, a key already exists -- the repository must not be touched."""

    import asyncio

    calls = []

    async def _owns(_session, _teacher, _classroom):
        return True

    async def _existing(_session, classroom_ids):
        return {classroom_ids[0]: "AUHTZT"}

    class _Boom:
        def __init__(self, _session):
            calls.append("constructed")

        async def store_key(self, *_args, **_kwargs):  # pragma: no cover - must not run
            raise AssertionError("a second store would rotate a permanent key")

    from app.application import data_access

    monkey = pytest.MonkeyPatch()
    monkey.setattr(data_access, "teacher_owns_classroom", _owns)
    monkey.setattr(data_access, "class_keys_for_classrooms", _existing)
    monkey.setattr(class_key_service, "ClassroomKeyRepository", _Boom)
    try:
        key = asyncio.run(class_key_service.ensure_class_key(None, TEACHER, CLASSROOM))
    finally:
        monkey.undo()

    assert key == "AUHTZT"
    assert calls == []


def test_the_ownership_guard_runs_before_any_write():
    """A caller who does not own the classroom must not be able to cause a mint, nor learn
    whether a key exists."""

    import asyncio

    reads = []

    async def _owns(_session, _teacher, _classroom):
        return False

    async def _existing(_session, _classroom_ids):  # pragma: no cover - must not run
        reads.append("read")
        return {}

    from app.application import data_access

    monkey = pytest.MonkeyPatch()
    monkey.setattr(data_access, "teacher_owns_classroom", _owns)
    monkey.setattr(data_access, "class_keys_for_classrooms", _existing)
    try:
        with pytest.raises(class_key_service.ClassroomNotVisibleError):
            asyncio.run(class_key_service.ensure_class_key(None, TEACHER, uuid.uuid4()))
    finally:
        monkey.undo()

    assert reads == []


def test_the_service_has_no_update_or_delete_path():
    """Source-level guard: the only write in this module is `store_key`."""

    import re
    from pathlib import Path

    source = Path(class_key_service.__file__).read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]
    # Strip comments and docstrings first: this module's own prose says "never rotated" to
    # document the rule, and a naive search would read that as a violation of it.
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
    for banned in ("update(", "delete(", "rotate", "regenerate"):
        assert banned not in code, banned
