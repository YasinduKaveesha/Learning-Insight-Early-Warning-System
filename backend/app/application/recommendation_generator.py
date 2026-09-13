"""The ONE recommendation v1 generates (decision D35; `dev_docs/ANSWERS_TO_APP_TEAM_4.md`).

THE RULE, VERBATIM FROM THE ML TEAM'S RULING
--------------------------------------------
At the learner's CURRENT session `s`, for skill `k`, `docs/06` section 3 stagnation holds:

    b_mastery_slope_w4[k] < 0.005  AND  b_mastery[k] < 0.8  AND  b_opportunities_w4[k] >= 4

and the learner is watch-flagged at `s` -> `practice {skill: k}`, `trigger.type = stagnation`,
`target_component = B`, `expires_after_session = min(s + 5, 25)`.

Every threshold is the governed stagnation definition the model's LABEL is built on -- none is
new. Condition "A" from `QUESTIONS_FOR_ML_TEAM_4` (the accuracy epsilon applied to a mastery
slope) was rejected; do not reintroduce `EPSILON_PRACTICE` here (D38).

THE SECOND RULE -- A PRODUCT DECISION THAT OVERRIDES PART OF D36 (D41)
---------------------------------------------------------------------
The ML lead decided on 2026-09-14 that EVERY watch-flagged learner receives a suggestion. A
flagged learner for whom the D35 rule finds no stagnant skill receives `monitor_progress {}`,
`trigger.type = watch_flag`, `target_component = both` (D37 provenance: the watch flag is raised
from Component B and C evidence together), the same expiry.

The ML team had ruled against exactly this (D36): it restates the watch flag, and teachers accept
it easily, so it can inflate the acceptance rate `docs/13` section 6 makes a research outcome. The
mitigation built in here is that it carries its OWN `trigger.type`, copied into every decision-log
row, so acceptance can -- and must -- be reported separately for `stagnation` and `watch_flag`.
It has NOT had the D16 subgroup check the ML team requires for every trigger (their Q6); that is
recorded as outstanding in D41.

WHAT IS NEVER GENERATED
-----------------------
`review` (no prerequisite ordering exists) and `try_again` (fails D16 for DD learners). A teacher
may still choose either through *modify*.

WHAT NEVER LEAVES THIS MODULE
-----------------------------
The mastery VALUE. It is read to evaluate clause 2 and recorded only as
`below_mastery_threshold: true`. `b_mastery` is `TEST_FIXTURE_ONLY` with identical BKT parameters
across all seven skills, and `parameter_source_status` travels inside the evidence so no later
reader mistakes fixture-derived evidence for calibrated evidence.

`evaluate` is pure (no database), so the rule can be tested exactly. `run_generator` applies the
issuing rules from the ruling's Q3 and writes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Panel, Prediction, Recommendation

# --- docs/06 section 3, primary arm (n = 4 under 3-Q1). Reused, not new. ------------------
STAGNATION_SLOPE_EPSILON = 0.005
STAGNATION_MASTERY_THETA = 0.8
STAGNATION_MIN_OPPORTUNITIES = 4
STAGNATION_WINDOW = 4

#: Q7: expiry is the label's forecast horizon (h = 5), capped at the last intervention session.
EXPIRY_SESSIONS = 5
LAST_INTERVENTION_SESSION = 25

TRIGGER_TYPE = "stagnation"
ACTION_KIND = "practice"
#: D37: provenance, not routing -- the component whose evidence raised it.
TARGET_COMPONENT = "B"

#: D41 -- the watch-list fallback. A distinct trigger type so its decisions are never pooled
#: with the stagnation trigger's in the research log.
WATCH_TRIGGER_TYPE = "watch_flag"
WATCH_ACTION_KIND = "monitor_progress"
WATCH_TARGET_COMPONENT = "both"

SOURCE_CLASS = "SYNTHETIC"
SOURCE_SYSTEM = "recommendation_generator"
PARAMETER_SOURCE_STATUS = "TEST_FIXTURE_ONLY"

ACTIVE_STATUSES = ("pending", "accepted", "modified")

#: Display names for the summary. Lower-case because they sit mid-sentence.
SKILL_SUMMARY_NAME: Mapping[str, str] = {
    "counting": "counting",
    "number_sense": "number sense",
    "place_value": "place value",
    "addition": "addition",
    "subtraction": "subtraction",
    "multiplication": "multiplication",
    "division": "division",
}


@dataclass(frozen=True)
class Candidate:
    skill: str | None
    session: int
    expires_after_session: int
    evidence: dict[str, Any]
    evidence_summary: str
    kind: str = ACTION_KIND
    trigger_type: str = TRIGGER_TYPE
    target_component: str = TARGET_COMPONENT
    opportunities: int | None = None
    slope: float | None = None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def stagnant_skills(
    mastery: Mapping[str, Any] | None,
    slopes: Mapping[str, Any] | None,
    opportunities: Mapping[str, Any] | None,
) -> list[tuple[str, int, float]]:
    """Every skill meeting all three `docs/06` clauses, as `(skill, opportunities, slope)`.

    A missing value on any clause means the clause is NOT met -- absence is never evidence of
    stagnation.
    """

    out = []
    for skill in sorted(set(opportunities or {})):
        opp = _number((opportunities or {}).get(skill))
        slope = _number((slopes or {}).get(skill))
        level = _number((mastery or {}).get(skill))
        if opp is None or slope is None or level is None:
            continue
        if (
            slope < STAGNATION_SLOPE_EPSILON
            and level < STAGNATION_MASTERY_THETA
            and opp >= STAGNATION_MIN_OPPORTUNITIES
        ):
            out.append((skill, int(opp), slope))
    return out


def evidence_summary(skill: str, session: int, opportunities: int) -> str:
    """The ML team's template (ANSWERS_TO_APP_TEAM_4 section 3), anchored to the ISSUE session so
    the statement stays true as the suggestion ages (Q7). No number but the session range and
    the practice count; no slope, mastery, model or probability."""

    first = max(1, session - (STAGNATION_WINDOW - 1))
    name = SKILL_SUMMARY_NAME.get(skill, skill.replace("_", " "))
    return (
        f"In sessions {first}–{session}, {opportunities} practice questions on {name} "
        f"have not yet shown steady progress. Suggestion: more practice on {name}."
    )


def evaluate(
    *,
    session: int,
    watch_flag: bool,
    mastery: Mapping[str, Any] | None,
    slopes: Mapping[str, Any] | None,
    opportunities: Mapping[str, Any] | None,
    excluded_skills: frozenset[str] = frozenset(),
) -> Candidate | None:
    """The D35 rule for one learner at their current session. Pure.

    `excluded_skills` carries Q3 rule 3 -- skills with a dismissed suggestion that has not yet
    expired -- so the caller decides WHICH skills are barred and this function stays pure.
    """

    if not watch_flag:
        return None  # Q2: outside the flag, stagnation predicts nothing (0.87 [0.00, 1.97])

    eligible = [s for s in stagnant_skills(mastery, slopes, opportunities) if s[0] not in excluded_skills]
    if not eligible:
        return None

    # Q3 rule 1: most evidence, then lowest slope, then alphabetical key. Alphabetical, NOT
    # curricular: a curricular order would read as a prerequisite claim Q4 rules has no basis.
    skill, opp, slope = sorted(eligible, key=lambda s: (-s[1], s[2], s[0]))[0]

    return Candidate(
        skill=skill,
        session=session,
        opportunities=opp,
        slope=slope,
        expires_after_session=min(session + EXPIRY_SESSIONS, LAST_INTERVENTION_SESSION),
        evidence={
            "definition": "docs06_s3",
            "window_first_session": max(1, session - (STAGNATION_WINDOW - 1)),
            "window_last_session": session,
            "opportunities_w4": opp,
            # Stored for audit, as docs/13 permits. A slope, not a mastery VALUE, so the domain
            # layer's evidence filter lets it through; the client never renders evidence numbers.
            "mastery_slope_w4": slope,
            "below_mastery_threshold": True,
            "watch_flag": True,
            "parameter_source_status": PARAMETER_SOURCE_STATUS,
        },
        evidence_summary=evidence_summary(skill, session, opp),
    )


def watch_list_summary(session: int) -> str:
    """Summary for the D41 fallback. States what is true -- the learner is on the watch list and
    no single skill stands out -- and names no cause, no number but the session, no model."""

    return (
        f"On the watch list at session {session}, and no single skill stands out in recent "
        "practice. Suggestion: keep monitoring progress over the next few sessions."
    )


def evaluate_watch_list(
    *,
    session: int,
    watch_flag: bool,
    barred: bool = False,
) -> Candidate | None:
    """D41: a watch-flagged learner with no D35 suggestion gets `monitor_progress`. Pure.

    Call it ONLY after `evaluate` returned None. `barred` carries Q3 rule 3 for this trigger: a
    dismissed watch-list suggestion that has not yet expired is not re-issued.
    """

    if not watch_flag or barred:
        return None
    return Candidate(
        skill=None,
        session=session,
        expires_after_session=min(session + EXPIRY_SESSIONS, LAST_INTERVENTION_SESSION),
        evidence={
            "definition": "watch_flag_d14",
            "session": session,
            "watch_flag": True,
            "stagnant_skill_found": False,
            "parameter_source_status": PARAMETER_SOURCE_STATUS,
        },
        evidence_summary=watch_list_summary(session),
        kind=WATCH_ACTION_KIND,
        trigger_type=WATCH_TRIGGER_TYPE,
        target_component=WATCH_TARGET_COMPONENT,
    )


# --- the pipeline step ----------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratorResult:
    learners: int
    issued: int
    skipped_active: int
    skipped_not_eligible: int


async def run_generator(
    session: AsyncSession,
    *,
    pipeline_run_id: uuid.UUID,
    dry_run: bool = False,
) -> GeneratorResult:
    """Issue D35 recommendations for one pipeline run, at each learner's CURRENT session only.

    Never backfills: a suggestion issued at a past session would already have expired before a
    teacher saw it, and would pollute the decision log.

    Q3 rule 2 -- skip a learner who holds ANY `B` recommendation in an active status. This is
    checked here rather than left to `uq_t3_reco_active`, per the ruling, so a re-run is a no-op
    instead of an exception.

    OPEN CONFLICT WITH Q3 RULE 4 ("after expiry, the learner is eligible again"). The schema has
    no `expired` status, and `uq_t3_reco_active` covers pending/accepted/modified REGARDLESS of
    expiry. An expired-but-still-pending suggestion therefore blocks a new one at the database
    level, so this step skips such a learner rather than violating the index. Honouring rule 4
    needs a decision -- an expiry status transition, or an index that excludes expired rows --
    and is not invented here. In the D30 demo no learner's session advances, so nothing expires
    and the conflict cannot arise.
    """

    latest_panel = {
        row.student_id: row
        for row in (
            await session.execute(
                select(
                    Panel.student_id,
                    Panel.intervention_session_number,
                    Panel.b_mastery,
                    Panel.b_mastery_slope_w4,
                    Panel.b_opportunities_w4,
                )
                .where(Panel.pipeline_run_id == pipeline_run_id)
                .order_by(Panel.student_id, Panel.intervention_session_number.desc())
                .distinct(Panel.student_id)
            )
        ).all()
    }
    # `.t` is shadowed on sqlalchemy.Row (see data_access._as_records), so select it by label.
    flags = {
        (row.student_id, row.snapshot_t): row.watch_flag
        for row in (
            await session.execute(
                select(
                    Prediction.student_id,
                    Prediction.t.label("snapshot_t"),
                    Prediction.watch_flag,
                ).where(Prediction.pipeline_run_id == pipeline_run_id)
            )
        ).all()
    }
    existing = (
        await session.execute(
            select(
                Recommendation.student_id,
                Recommendation.teacher_status,
                Recommendation.expires_after_session,
                Recommendation.proposed_action,
            ).where(
                # Every target: D41 allows one suggestion per learner, B or both.
                Recommendation.student_id.in_(list(latest_panel)),
            )
        )
    ).all() if latest_panel else []

    issued = skipped_active = skipped_not_eligible = 0
    now = dt.datetime.now(dt.timezone.utc)

    for student_id, panel in latest_panel.items():
        s = panel.intervention_session_number
        mine = [r for r in existing if r.student_id == student_id]

        # One suggestion per learner at a time, whichever trigger raised it.
        if any(r.teacher_status in ACTIVE_STATUSES for r in mine):
            skipped_active += 1
            continue

        unexpired_dismissals = [
            r for r in mine if r.teacher_status == "dismissed" and r.expires_after_session >= s
        ]
        # Q3 rule 3: a dismissed skill is not re-issued before that suggestion's expiry.
        barred = frozenset(
            (r.proposed_action or {}).get("detail", {}).get("skill")
            for r in unexpired_dismissals
        ) - {None}
        watch_flag = bool(flags.get((student_id, s), False))

        candidate = evaluate(
            session=s,
            watch_flag=watch_flag,
            mastery=panel.b_mastery,
            slopes=panel.b_mastery_slope_w4,
            opportunities=panel.b_opportunities_w4,
            excluded_skills=barred,
        ) or evaluate_watch_list(
            session=s,
            watch_flag=watch_flag,
            barred=any(
                (r.proposed_action or {}).get("kind") == WATCH_ACTION_KIND
                for r in unexpired_dismissals
            ),
        )
        if candidate is None:
            skipped_not_eligible += 1
            continue

        issued += 1
        if dry_run:
            continue
        session.add(
            Recommendation(
                recommendation_id=uuid.uuid4(),
                student_id=student_id,
                issued_at_intervention_session=candidate.session,
                expires_after_session=candidate.expires_after_session,
                target_component=candidate.target_component,
                trigger={
                    "type": candidate.trigger_type,
                    "skill": candidate.skill,
                    "evidence": candidate.evidence,
                },
                proposed_action={
                    "kind": candidate.kind,
                    "detail": {"skill": candidate.skill} if candidate.skill else {},
                },
                evidence_summary=candidate.evidence_summary,
                teacher_status="pending",
                created_at_utc=now,
                updated_at_utc=now,
                source_class=SOURCE_CLASS,
                source_system=SOURCE_SYSTEM,
                parameter_source_status=PARAMETER_SOURCE_STATUS,
                pipeline_run_id=pipeline_run_id,
            )
        )

    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    return GeneratorResult(
        learners=len(latest_panel),
        issued=issued,
        skipped_active=skipped_active,
        skipped_not_eligible=skipped_not_eligible,
    )


async def _amain() -> None:  # pragma: no cover - operational entrypoint
    """``python -m app.application.recommendation_generator [--dry-run]``.

    Reads ``DATABASE_URL`` and ``T3_PIPELINE_RUN_ID``. Direct connection, like the other pipeline
    steps. Run AFTER ``decision_layer``: it reads that run's watch flags.
    """

    import os
    import sys

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.db.engine import create_direct_engine

    dry_run = "--dry-run" in sys.argv[1:]
    engine, target = create_direct_engine(os.environ["DATABASE_URL"])
    print(f"recommendation_generator target: {target}{' (dry run)' if dry_run else ''}")
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            result = await run_generator(
                session,
                pipeline_run_id=uuid.UUID(os.environ["T3_PIPELINE_RUN_ID"]),
                dry_run=dry_run,
            )
    finally:
        await engine.dispose()
    print(
        f"learners={result.learners} issued={result.issued} "
        f"skipped_active={result.skipped_active} skipped_not_eligible={result.skipped_not_eligible}"
    )


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(_amain())
