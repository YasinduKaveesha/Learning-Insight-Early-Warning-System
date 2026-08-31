"""The database side of class-key allocation: an INSERT that turns a unique-constraint
violation into `ClassKeyCollision` so `generate_and_insert_class_key` can retry.

`app.application.class_key` owns the generation alphabet and the bounded retry loop and
imports no database driver. This module is the thin adapter that binds that loop to
`t3_classroom_keys`. There is intentionally **no update method** -- the key is never rotated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.class_key import (
    DEFAULT_MAX_ATTEMPTS,
    ClassKeyCollision,
    generate_and_insert_class_key,
    generate_class_key,
)
from app.infrastructure.db.models import ClassroomKey

_UNIQUE_VIOLATION_SQLSTATE = "23505"
_CLASS_KEY_CONSTRAINT = "uq_t3_classroom_keys_class_key"


def _is_class_key_collision(exc: IntegrityError) -> bool:
    """True only for a unique violation on `t3_classroom_keys.class_key`.

    A unique violation on the primary key (`classroom_id` already has a key) is a caller
    error, not something to retry -- let it propagate.
    """

    orig = getattr(exc, "orig", None)
    # asyncpg raises UniqueViolationError with .sqlstate == '23505'; SQLAlchemy also exposes
    # a normalised .code on the wrapper.
    sqlstate = getattr(orig, "sqlstate", None) or getattr(exc, "code", None) or ""
    if str(sqlstate) != _UNIQUE_VIOLATION_SQLSTATE:
        return False
    return _CLASS_KEY_CONSTRAINT in str(orig)


class ClassroomKeyRepository:
    """Insert-only access to `t3_classroom_keys`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_key(
        self,
        classroom_id: uuid.UUID,
        *,
        source_class: str,
        source_system: str,
        parameter_source_status: str,
        pipeline_run_id: uuid.UUID,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> str:
        """Allocate and persist the permanent key for `classroom_id`, returning it.

        Generate -> insert -> on a `class_key` unique violation, regenerate and retry, up to
        `max_attempts`, then raise `ClassKeyAllocationError`. Never pre-checks for existence.
        """

        provenance = {
            "source_class": source_class,
            "source_system": source_system,
            "parameter_source_status": parameter_source_status,
            "pipeline_run_id": pipeline_run_id,
        }

        async def _insert(candidate: str) -> None:
            savepoint = await self._session.begin_nested()
            try:
                await self._session.execute(
                    insert(ClassroomKey).values(
                        classroom_id=classroom_id, class_key=candidate, **provenance
                    )
                )
            except IntegrityError as exc:
                await savepoint.rollback()
                if _is_class_key_collision(exc):
                    raise ClassKeyCollision(candidate) from exc
                raise
            else:
                await savepoint.commit()

        return await generate_and_insert_class_key(
            _insert, generate=generate_class_key, max_attempts=max_attempts
        )
