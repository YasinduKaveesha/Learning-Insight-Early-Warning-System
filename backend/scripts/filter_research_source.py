"""Filter the research source JSONL to the students bridged in `t3_demo_learner_map`.

WHY THIS EXISTS
---------------
`t3_loader.run_load` is fail-closed on identity: if any record's `student_id` does not resolve
to a `learner_id`, it raises `LearnerResolutionError` and rolls back the entire load. That is
the correct behaviour -- a partial load that silently dropped learners would produce a dashboard
missing children with nobody noticing -- but it means the source file handed to the loader must
contain only students the bridge knows about.

The research dataset carries 300 students; the demo roster is 120. So the loader gets a filtered
copy. This is a narrowing, never a transformation: every retained line is byte-identical to the
original, and no field is rewritten. The dataset itself is read-only and is never modified.

USAGE
-----
    python scripts/filter_research_source.py --out <path>

Reads `DATABASE_URL` from `backend/.env` to discover which `STU-xxxx` ids are bridged.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
load_dotenv(_BACKEND_ROOT / ".env", override=False)

_DEFAULT_SOURCE = (
    _BACKEND_ROOT.parents[1] / "dataset" / "source" / "so2_joined_dataset_seed20260828_n300.jsonl"
)


def bridged_student_ids(database_url: str) -> set[str]:
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.db.engine import create_direct_engine

    async def _run() -> set[str]:
        engine, target = create_direct_engine(database_url)
        print(f"bridge target: {target}")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                rows = await session.execute(
                    text("SELECT research_student_id FROM t3_demo_learner_map")
                )
                return {str(r[0]) for r in rows.all()}
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is not set (expected in backend/.env).", file=sys.stderr)
        return 1
    if not args.source.exists():
        print(f"Source not found: {args.source}", file=sys.stderr)
        return 1

    keep = bridged_student_ids(database_url)
    if not keep:
        print(
            "t3_demo_learner_map is empty -- run scripts/seed_demo_tenancy.py --phase learners "
            "first, or the loader would have nothing to resolve against.",
            file=sys.stderr,
        )
        return 1

    kept = dropped = 0
    seen: set[str] = set()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.source.open("r", encoding="utf-8") as src, args.out.open(
        "w", encoding="utf-8", newline="\n"
    ) as dst:
        for line in src:
            if not line.strip():
                continue
            student_id = json.loads(line).get("student_id")
            if student_id in keep:
                dst.write(line)          # byte-identical; never rewritten
                seen.add(str(student_id))
                kept += 1
            else:
                dropped += 1

    print(f"bridged students : {len(keep)}")
    print(f"students present : {len(seen)}")
    print(f"lines kept       : {kept}")
    print(f"lines dropped    : {dropped}")
    print(f"written to       : {args.out}")

    missing = keep - seen
    if missing:
        # Loud, not a warning buried in a log: the loader would abort on these anyway, and it
        # is better to learn here which ids the dataset does not contain.
        print(
            f"\nWARNING: {len(missing)} bridged id(s) have NO rows in the source, e.g. "
            f"{sorted(missing)[:5]}. The loader will not see them, so those learners will have "
            f"no analytics.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
