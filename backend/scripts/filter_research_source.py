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

STAGGERING (D30)
----------------
The research dataset gives every learner all 25 sessions, so without staggering every demo learner
shows at `t = 19` simultaneously -- the point where MODEL_CARD section 4 says the flag adds least,
and a class no real teacher would ever see.

`--stagger-seed` assigns each learner a "current session" from the supervised grid and emits only
that learner's sessions `<= t_i`. This is a NARROWING, never a rewrite: every retained line is
byte-identical, and every snapshot served is a genuine as-of-`t` forecast computed from information
`<= t` only.

**Truncating here rather than in the service layer is deliberate.** D30 requires the ENTIRE learner
view to truncate -- session history, trajectory chip, `sessions_completed`, everything -- not just
the prediction. Cutting the source means the panel stops at `t_i`, so features, predictions,
sparklines, session history and skills all stop there too, and the next endpoint someone adds
inherits it for free. A service-layer filter would have to be applied in several places and would be
forgotten.

The assignment is a **balanced permutation**: each grid point gets an equal share (the remainder
distributed by the same RNG), which reproduces the research design's own weighting exactly rather
than in expectation and cuts the variance of the headline flag rate by ~22% against iid uniform.

**The seed is declared in advance and never re-drawn.** Re-rolling until the demo looks better is
selection on the outcome. Assignment depends only on the seed and the sorted research ids -- never
on population, on predictions, or on classroom.

USAGE
-----
    python scripts/filter_research_source.py --out <path>
    python scripts/filter_research_source.py --out <path> --stagger-seed 20260914 \
        --stagger-out scripts/demo_stagger_assignment.json

Reads `DATABASE_URL` from `backend/.env` to discover which `STU-xxxx` ids are bridged.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
load_dotenv(_BACKEND_ROOT / ".env", override=False)

#: The supervised grid the model was trained on: nine snapshots per learner.
SUPERVISED_GRID = (3, 5, 7, 9, 11, 13, 15, 17, 19)

_DEFAULT_SOURCE = (
    _BACKEND_ROOT.parents[1] / "dataset" / "source" / "so2_joined_dataset_seed20260828_n300.jsonl"
)


def stagger_assignment(student_ids: list[str], seed: int) -> dict[str, int]:
    """Balanced seeded permutation of `student_ids` over `SUPERVISED_GRID`.

    Each grid point receives `len(ids) // 9` learners; the remainder goes to grid points chosen by
    the same RNG, so no grid point is systematically favoured. The result depends only on the seed
    and the SORTED id list, which makes it reproducible and independent of database ordering.
    """

    ids = sorted(student_ids)
    rng = random.Random(seed)

    base, remainder = divmod(len(ids), len(SUPERVISED_GRID))
    slots: list[int] = []
    for t in SUPERVISED_GRID:
        slots.extend([t] * base)
    slots.extend(rng.sample(list(SUPERVISED_GRID), remainder))

    rng.shuffle(slots)
    return dict(zip(ids, slots))


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
    parser.add_argument(
        "--stagger-seed",
        type=int,
        default=None,
        help="Enable D30 staggering with this seed. Omit for the un-staggered behaviour the "
        "existing tests exercise. DECLARE THE SEED IN ADVANCE AND NEVER RE-DRAW IT.",
    )
    parser.add_argument(
        "--stagger-out",
        type=Path,
        default=None,
        help="Where to write the learner -> assigned-t audit record (requires --stagger-seed).",
    )
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

    assigned: dict[str, int] = {}
    if args.stagger_seed is not None:
        assigned = stagger_assignment(sorted(keep), args.stagger_seed)
        spread = collections.Counter(assigned.values())
        print(f"stagger seed     : {args.stagger_seed}  (declared in advance, never re-drawn)")
        print("stagger spread   : " + "  ".join(f"t={t}:{spread[t]}" for t in SUPERVISED_GRID))
    elif args.stagger_out is not None:
        print("--stagger-out requires --stagger-seed.", file=sys.stderr)
        return 1

    kept = dropped = truncated = 0
    seen: set[str] = set()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.source.open("r", encoding="utf-8") as src, args.out.open(
        "w", encoding="utf-8", newline="\n"
    ) as dst:
        for line in src:
            if not line.strip():
                continue
            record = json.loads(line)
            student_id = record.get("student_id")
            if student_id not in keep:
                dropped += 1
                continue
            cutoff = assigned.get(str(student_id))
            if cutoff is not None and int(record.get("intervention_session_number", 0)) > cutoff:
                truncated += 1
                continue
            dst.write(line)              # byte-identical; never rewritten
            seen.add(str(student_id))
            kept += 1

    print(f"bridged students : {len(keep)}")
    print(f"students present : {len(seen)}")
    print(f"lines kept       : {kept}")
    print(f"lines dropped    : {dropped}   (learners outside the demo roster)")
    if assigned:
        print(f"lines truncated  : {truncated}   (sessions after each learner's assigned t)")
    print(f"written to       : {args.out}")

    if assigned and args.stagger_out:
        args.stagger_out.parent.mkdir(parents=True, exist_ok=True)
        args.stagger_out.write_text(
            json.dumps(
                {
                    "seed": args.stagger_seed,
                    "rule": "balanced seeded permutation over SUPERVISED_GRID; never re-drawn",
                    "grid": list(SUPERVISED_GRID),
                    "assignment": {k: assigned[k] for k in sorted(assigned)},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"assignment record: {args.stagger_out}")

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
