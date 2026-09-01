"""Teacher-dashboard response models (work order B6.1) -- backend_plan.md section 8.

Every model sets ``extra="forbid"``. That is not style: it is the second half of the
never-serialised guarantee. The first half is that
:mod:`app.application.data_access` selects only the columns it intends to return, so the
forbidden values are never even loaded; ``extra="forbid"`` means that if a future caller
hands a response model a dict that DOES carry one, construction raises instead of quietly
passing it through to the client.

FIELDS THAT MUST NEVER BE SERIALISED (backend_plan.md section 8)
---------------------------------------------------------------
``prob_class_0``, ``prob_class_1``, ``prob_class_2plus``, ``predicted_class``,
``engagement_trajectory`` (D17), ``population``, ``dd_subtype``, raw feature values, any
cluster or PCA field, ``risk_score``, and ``risk_level = "High"``.

``engagement_trajectory`` is the one to watch. It is COMPUTED and STORED on every
``t3_predictions`` row and must never leave the server: DD learners were flagged by it at
0.76 of their own base rate (an inversion), and it is ``unknown`` for 56-86% of learners
because ``c_engagement_score`` is missing from 49.9% of sessions. It would under-surface the
group the product exists to serve *while looking informative*. `tests/test_dashboard_api.py`
asserts its absence from every response body, which is the test carried forward from B5.1's
gate 9 -- until this module existed there were no response models to assert against.

THE TWO RULES THAT OVERRIDE EVERYTHING
--------------------------------------
1. The system FLAGS learners for teacher review. It does not diagnose, detect, identify or
   screen. No field name or literal here may imply otherwise -- hence ``watch_flag`` and
   ``needs_attention``, never "risk", "at-risk", "screened" or "detected".
2. ``DISCLOSURE`` is returned by the API on every response rather than hard-coded in the
   client, so the required wording cannot drift between screens.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Rule 2. Returned on every response body in this module. One definition, server-side.
DISCLOSURE = "Literature-informed synthetic data — not clinical evidence."

EvidenceStatus = Literal[
    "sufficient_evidence",
    "insufficient_exposure",
    "insufficient_future_evidence",
    "censored_by_observation_end",
    "administratively_missing",
]

#: D4. Three states. `unknown` is a fourth stored value but is a legitimate display state --
#: a learner with fewer than three sessions has no slope, and saying so is correct.
TrajectoryState = Literal["improving", "stable", "needs_attention", "unknown"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Disclosed(_Base):
    """Base for every top-level response. See rule 2."""

    disclosure: str = Field(default=DISCLOSURE)


class SignalOut(_Base):
    """One SHAP top-3 entry. `display_name` only -- the raw `feature` key stays server-side
    (filter 3), so a client cannot render a model column name to a teacher."""

    display_name: str
    direction: Literal["toward_review", "away_from_review"]


class LearnerCard(_Base):
    """One learner as they appear in a list. No probabilities, no predicted class, no
    engagement trajectory."""

    student_id: uuid.UUID
    display_name: str
    t: int
    evidence_status: EvidenceStatus
    sessions_completed: int
    watch_flag: bool
    rank_within_t: int | None = None
    practice_trajectory: TrajectoryState


class ClassCard(_Base):
    classroom_id: uuid.UUID
    name: str
    learner_count: int
    watch_count: int
    getting_started_count: int


class HomeSummary(Disclosed):
    watch_count: int
    active_students: int
    class_count: int
    getting_started_count: int
    classes: list[ClassCard]


class CohortStats(_Base):
    learner_count: int
    watch_count: int
    getting_started_count: int
    improving_count: int
    needs_attention_count: int


class CohortResponse(Disclosed):
    classroom_id: uuid.UUID
    stats: CohortStats
    learners: list[LearnerCard]


class WatchListResponse(Disclosed):
    """Flagged learners only, ordered by `rank_within_t`.

    Ranking is WITHIN a single `t` and is never pooled across different `t` (D5 / the B5.1
    trap): 2+ prevalence rises from 0.000 at t=3 to 0.144 at t=19, so a pooled order would
    fill the list with late-session learners while a struggling early-session learner never
    appeared. The service sorts by `(t, rank_within_t)` for exactly this reason.
    """

    classroom_id: uuid.UUID | None = None
    learners: list[LearnerCard]


class StudentDetail(Disclosed):
    student_id: uuid.UUID
    display_name: str
    t: int
    evidence_status: EvidenceStatus
    sessions_completed: int
    watch_flag: bool
    rank_within_t: int | None = None
    practice_trajectory: TrajectoryState
    explanation: str | None = None
    signals: list[SignalOut] = Field(default_factory=list)
