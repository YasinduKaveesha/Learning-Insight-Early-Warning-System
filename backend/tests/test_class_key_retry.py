"""The unique constraint drives the retry (D1; plan section 4.2).

Gate 4 of work order B3.2: when insertion keeps hitting the `class_key` unique constraint,
`generate_and_insert_class_key` regenerates and retries, is bounded to N attempts, then
raises the typed `ClassKeyAllocationError` -- it never loops forever and never returns a
duplicate. There is no check-then-insert: the only signal it acts on is a raised
`ClassKeyCollision` from the insert callable.
"""

from __future__ import annotations

import asyncio

import pytest

from app.application.class_key import (
    ClassKeyAllocationError,
    ClassKeyCollision,
    generate_and_insert_class_key,
)


def _run(coro):
    return asyncio.run(coro)


def test_exhausts_bounded_attempts_then_raises_typed_error() -> None:
    attempts: list[str] = []

    async def always_collides(candidate: str) -> None:
        attempts.append(candidate)
        raise ClassKeyCollision(candidate)

    with pytest.raises(ClassKeyAllocationError) as excinfo:
        _run(generate_and_insert_class_key(always_collides, max_attempts=5))

    assert "5 attempts" in str(excinfo.value)
    assert len(attempts) == 5  # bounded -- not one more, not infinite


def test_retries_then_succeeds_and_returns_the_inserted_key() -> None:
    inserted: list[str] = []
    calls = {"n": 0}

    async def collide_twice_then_accept(candidate: str) -> None:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ClassKeyCollision(candidate)
        inserted.append(candidate)

    result = _run(generate_and_insert_class_key(collide_twice_then_accept, max_attempts=10))

    assert calls["n"] == 3
    assert inserted == [result]  # returns exactly the key that was inserted, no duplicate


def test_stub_generator_forcing_a_known_collision() -> None:
    # Mirrors "stub the generator to return an existing key": the generator is pinned to one
    # value that the store always rejects.
    seen: list[str] = []

    async def reject_existing(candidate: str) -> None:
        seen.append(candidate)
        raise ClassKeyCollision(candidate)

    with pytest.raises(ClassKeyAllocationError):
        _run(
            generate_and_insert_class_key(
                reject_existing, generate=lambda: "ABC234", max_attempts=3
            )
        )

    assert seen == ["ABC234", "ABC234", "ABC234"]


def test_non_collision_error_is_not_retried() -> None:
    calls = {"n": 0}

    async def insert_fails_hard(candidate: str) -> None:
        calls["n"] += 1
        raise RuntimeError("connection reset")

    with pytest.raises(RuntimeError, match="connection reset"):
        _run(generate_and_insert_class_key(insert_fails_hard, max_attempts=5))

    assert calls["n"] == 1  # propagated immediately, no retry


def test_max_attempts_must_be_positive() -> None:
    async def never_called(candidate: str) -> None:  # pragma: no cover
        raise AssertionError("insert should not be attempted")

    with pytest.raises(ValueError):
        _run(generate_and_insert_class_key(never_called, max_attempts=0))
