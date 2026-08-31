"""Permanent class-key generation and the collision-driven insert retry (D1).

`docs/04` section 3.1 and `plan/backend_plan.md` section 4.2.

The key is shown once at class creation and retrievable forever, so it is **generated once
and never rotated** -- this module deliberately exposes no update path for `class_key`.

Two rules that are not style preferences:

* **Never check-then-insert.** Two teachers creating classes in the same instant both see a
  key as free. The `UNIQUE` constraint on `t3_classroom_keys.class_key` is the only arbiter;
  a collision comes back as `ClassKeyCollision` and the response is to regenerate and retry,
  bounded to a small number of attempts, then raise `ClassKeyAllocationError`.
* **The alphabet excludes `0`/`O` and `1`/`I`** -- a teacher reads this key aloud to a room --
  leaving 32 symbols, and a key of six identical characters is rejected as well.

This module imports nothing beyond the standard library: the SQLAlchemy insert lives in
`app.infrastructure` and calls `generate_and_insert_class_key` with a thin insert callable.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable

#: 32 symbols: digits 2-9 and A-Z with the visually ambiguous 0/O and 1/I removed.
CLASS_KEY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

CLASS_KEY_LENGTH = 6

#: The database CHECK is deliberately broader than this (it permits 0/O/1/I at rest -- that
#: exclusion is a generation rule, not a storage rule). Keep them in step for what we emit.
CLASS_KEY_RE = re.compile(r"^[0-9A-Z]{6}$")

#: Bounded retry budget. Collision probability is ~n / 32**6 ~= n / 1.07e9 per attempt, so
#: this is only ever exhausted by a stuck generator, which is exactly what the typed error
#: is for.
DEFAULT_MAX_ATTEMPTS = 10


class ClassKeyError(RuntimeError):
    """Base class for class-key allocation failures."""


class ClassKeyCollision(ClassKeyError):
    """The generated key already exists -- the `UNIQUE` constraint rejected the insert.

    Raised by the insert callable, caught inside `generate_and_insert_class_key`, and never
    propagated: it means "regenerate and try again", not "give up".
    """


class ClassKeyAllocationError(ClassKeyError):
    """Could not allocate a unique key within the retry budget.

    Surfaced to the caller (and, later, to the API as a 5xx) rather than looping forever or
    returning a duplicate.
    """


def _is_six_identical(key: str) -> bool:
    return len(set(key)) == 1


def generate_class_key() -> str:
    """Return a fresh six-character key drawn from `CLASS_KEY_ALPHABET`.

    Rejects and redraws a key of six identical characters ("hard to read aloud", section
    3.1). Uses `secrets` rather than `random` -- the key is a shared secret for joining a
    class.
    """

    while True:
        key = "".join(secrets.choice(CLASS_KEY_ALPHABET) for _ in range(CLASS_KEY_LENGTH))
        if not _is_six_identical(key):
            return key


async def generate_and_insert_class_key(
    insert_row: Callable[[str], Awaitable[None]],
    *,
    generate: Callable[[], str] = generate_class_key,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> str:
    """Generate a key, insert it, and on a `ClassKeyCollision` regenerate and retry.

    `insert_row(candidate)` performs the actual `INSERT` and must raise `ClassKeyCollision`
    -- and nothing else -- when the `class_key` unique constraint fires. Any other exception
    propagates unchanged (a bad `classroom_id`, a lost connection: not our problem to retry).

    Returns the key that was successfully inserted. Raises `ClassKeyAllocationError` after
    `max_attempts` collisions without ever inserting a duplicate or looping unbounded.
    """

    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    for _ in range(max_attempts):
        candidate = generate()
        try:
            await insert_row(candidate)
        except ClassKeyCollision:
            continue
        return candidate

    raise ClassKeyAllocationError(
        f"could not allocate a unique class key after {max_attempts} attempts"
    )
