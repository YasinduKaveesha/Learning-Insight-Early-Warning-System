"""Mint the permanent class key (D1) for every REAL classroom a teacher owns.

WHY THIS IS A SCRIPT AND NOT A SIDE EFFECT OF A READ
----------------------------------------------------
The demo classrooms were created through the **student app's** HTTP API, which knows nothing
about `t3_classroom_keys`. So they exist with no key, and `/classes/{id}/cohort` serves
`class_key: null` -- an honest state, and the one the frontend has to render until a key is
minted.

The tempting fix is for the cohort endpoint to mint a key when it finds none. It is rejected:
a GET that writes is a side effect someone will trip over later (a preflight, a retry, a
crawler, a second browser tab racing itself), and D1 calls the key **permanent**, which argues
for creating it once, deliberately, at a moment a human chose. Class creation is that moment
for classrooms Component 3 creates (B6.4); this script is that moment for the ones that already
exist.

IDEMPOTENT. A classroom that already has a key is skipped and reported, never re-minted --
`t3_classroom_keys.classroom_id` is the primary key, and rotation has no code path anywhere
(see `app/application/class_key.py`).

    conda run -n c3-ews python scripts/mint_class_keys.py --dry-run
    conda run -n c3-ews python scripts/mint_class_keys.py

Reads `DATABASE_URL` from the backend `.env` like every other entry point. The teacher is taken
from `scripts/demo_tenancy_receipt.json` unless `--teacher-profile-id` is given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import uuid

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.application import data_access  # noqa: E402
from app.infrastructure.classroom_key_repository import ClassroomKeyRepository  # noqa: E402
from app.infrastructure.db.engine import get_sessionmaker  # noqa: E402

#: A fixed, documented placeholder, exactly as `principal_resolution`'s
#: `DEMO_BINDING_PIPELINE_RUN_ID`. `t3_classroom_keys` carries the six-column provenance set
#: because `plan/backend_plan.md` section 4 gives it to every new table -- not because a class
#: key is a pipeline output. It is never joined against `t3_pipeline_runs`. Stamping the
#: ACTIVE run here would be worse than a placeholder: it would assert that the key came out of
#: that run, and it would make the value differ between classrooms minted on different days.
CLASS_KEY_PIPELINE_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

SOURCE_CLASS = "REAL"
SOURCE_SYSTEM = "t3-mint-class-keys"
PARAMETER_SOURCE_STATUS = "OPERATOR_ASSIGNED"

_RECEIPT = _BACKEND_ROOT / "scripts" / "demo_tenancy_receipt.json"


def _teacher_from_receipt() -> uuid.UUID:
    if not _RECEIPT.exists():
        raise SystemExit(
            f"{_RECEIPT} not found -- pass --teacher-profile-id explicitly."
        )
    receipt = json.loads(_RECEIPT.read_text(encoding="utf-8"))
    return uuid.UUID(receipt["teacher_profile_id"])


async def _run(teacher_profile_id: uuid.UUID, *, dry_run: bool) -> int:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        classrooms = await data_access.classrooms_for_teacher(session, teacher_profile_id)
        if not classrooms:
            print(f"no REAL classrooms for teacher {teacher_profile_id}")
            return 1

        existing = await data_access.class_keys_for_classrooms(
            session, [c.classroom_id for c in classrooms]
        )

        minted = 0
        for room in sorted(classrooms, key=lambda c: (c.name or "", str(c.classroom_id))):
            held = existing.get(room.classroom_id)
            if held is not None:
                print(f"  {room.name or room.classroom_id}: {held}  (already minted, kept)")
                continue
            if dry_run:
                print(f"  {room.name or room.classroom_id}: would mint")
                minted += 1
                continue
            repository = ClassroomKeyRepository(session)
            key = await repository.create_key(
                room.classroom_id,
                source_class=SOURCE_CLASS,
                source_system=SOURCE_SYSTEM,
                parameter_source_status=PARAMETER_SOURCE_STATUS,
                pipeline_run_id=CLASS_KEY_PIPELINE_RUN_ID,
            )
            print(f"  {room.name or room.classroom_id}: {key}  (minted)")
            minted += 1

        if dry_run:
            await session.rollback()
            print(f"\ndry run -- {minted} classroom(s) would be minted, nothing written")
        else:
            await session.commit()
            print(f"\n{minted} classroom(s) minted, {len(existing)} already held a key")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-profile-id", type=uuid.UUID, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    teacher = args.teacher_profile_id or _teacher_from_receipt()
    print(f"teacher_profile_id {teacher}")
    return asyncio.run(_run(teacher, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
