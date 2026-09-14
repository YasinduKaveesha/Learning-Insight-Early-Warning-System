"""Check every stored class key against the student app's live invite (D49). READ ONLY.

WHAT IT ANSWERS
---------------
For each REAL classroom: is the code a teacher can read in the dashboard the same code a child
can redeem? It proves that by hashing the stored key exactly as the student application does
(``sha256`` of the ungrouped, upper-cased form) and comparing against `classroom_invites`.

This was the defect D49 fixed. Before it, Component 3 minted its own six-character key while the
student app hashed a different string, so the code a teacher read aloud resolved to nothing --
false on all six demo classrooms.

WHY THIS SCRIPT ONLY READS
--------------------------
Its predecessor (`backfill_class_keys.py`, run once on 2026-09-14) also wrote, and both writes
were wrong to keep:

* ``UPDATE classroom_invites SET expires_at_utc = NULL`` -- a direct write to a table the
  student application owns. D3/D10: Component 3 is read-only toward their tables, and reaching
  past their API also skipped their own `updated_at_utc` bookkeeping.
* ``ON CONFLICT (classroom_id) DO UPDATE SET class_key`` -- an overwrite path for a key D1 calls
  permanent. It was defensible exactly once, because the old keys had never been redeemable by
  anybody, but leaving the statement in the tree leaves a rotation anyone could run.

**The repair it performed is done and is not needed again**: every classroom created from now on
receives its code at creation (`httpClient.createClass` -> `POST /classes/{id}/key`), verified
against the live invite before it is stored.

IF THIS SCRIPT REPORTS A MISMATCH, the fix is NOT a direct write. Ask the student app team to
revoke that classroom's invite and issue a fresh non-expiring one, then store the new plaintext
through `POST /api/v1/t3/classes/{id}/key`. Only they can mint a code, because only they hold the
hash a child is checked against.

USAGE
-----
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.verify_class_keys

Exit code 0 when every classroom's key is redeemable; 1 when any is not.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def normalise(raw: str) -> str:
    """The student app's normalisation, character for character: separators out, upper-case."""

    return re.sub(r"[\s-]+", "", raw).upper()


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is required.")

    engine = create_async_engine(database_url, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    redeemable = missing = broken = 0

    async with maker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT c.name, k.class_key, i.token_hash, i.expires_at_utc, i.revoked_at_utc "
                    "FROM classrooms c "
                    "LEFT JOIN t3_classroom_keys k ON k.classroom_id = c.classroom_id "
                    "LEFT JOIN classroom_invites i ON i.classroom_id = c.classroom_id "
                    "  AND i.revoked_at_utc IS NULL "
                    "WHERE c.source_class = 'REAL' "
                    "ORDER BY c.name"
                )
            )
        ).all()

        for name, key, token_hash, expires_at, revoked_at in rows:
            if key is None:
                print(f"  {name}: NO KEY STORED -- the class screen shows no code")
                missing += 1
                continue
            digest = hashlib.sha256(normalise(key).encode()).hexdigest()
            if token_hash is None:
                print(f"  {name}: {key} -- NO LIVE INVITE; this code cannot be redeemed")
                broken += 1
            elif digest != token_hash:
                print(f"  {name}: {key} -- DOES NOT MATCH the live invite; unredeemable")
                broken += 1
            elif expires_at is not None:
                # Not unredeemable today, but it will stop working, while the dashboard keeps
                # showing it -- which is the same failure arriving later (D49).
                print(f"  {name}: {key} -- redeemable, but EXPIRES {expires_at:%Y-%m-%d %H:%M} UTC")
                broken += 1
            else:
                print(f"  {name}: {key} -- redeemable, never expires")
                redeemable += 1

    await engine.dispose()
    print(f"\n{redeemable} redeemable, {broken} broken, {missing} with no key.")
    return 0 if (broken or missing) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
