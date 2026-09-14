"""The database side of the class key: a single INSERT into `t3_classroom_keys`.

Component 3 does **not** generate join codes. The student application mints them, because only
it holds the `classroom_invites.token_hash` a learner's code is checked against; Component 3
keeps the plaintext so a teacher can re-read it (D49). Until then this module carried a
generator and a collision-retry loop for a key of its own -- a code that matched no invite and
could not be redeemed by any child.

There is intentionally **no update method**. The key is never rotated (D1), because children
write it down.
"""

from __future__ import annotations

import uuid

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ClassroomKey


class ClassroomKeyRepository:
    """Insert-only access to `t3_classroom_keys`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_key(
        self,
        classroom_id: uuid.UUID,
        class_key: str,
        *,
        source_class: str,
        source_system: str,
        parameter_source_status: str,
        pipeline_run_id: uuid.UUID,
    ) -> str:
        """Persist the student application's join code for `classroom_id`, returning it (D49).

        No generation and no retry: the code is not ours to choose, so a unique violation here
        is not a collision to regenerate around. It means this exact code is already stored
        against a different classroom -- which the student app's own `UNIQUE (token_hash)`
        should already have prevented -- and it propagates rather than being papered over.

        The caller verifies the code against the live invite hash before calling
        (`class_key_service.ensure_class_key`); this layer performs no validation of its own.
        """

        await self._session.execute(
            insert(ClassroomKey).values(
                classroom_id=classroom_id,
                class_key=class_key,
                source_class=source_class,
                source_system=source_system,
                parameter_source_status=parameter_source_status,
                pipeline_run_id=pipeline_run_id,
            )
        )
        return class_key
