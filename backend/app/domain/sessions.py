"""Session-history, skill-progress and class-report response models (work order B6.2).

Extends :mod:`app.domain.dashboard`; the same never-serialised rules and the same
``extra="forbid"`` discipline apply, and `DISCLOSURE` is re-exported through `Disclosed`.

THE THREE RULES THIS MODULE EXISTS TO ENFORCE
---------------------------------------------
1. **Component B and Component C are SEPARATE FIELD GROUPS. They are never merged.** Not
   averaged, not summed, not folded into a single "accuracy" or "response time". They measure
   different activities under different conditions, and a single blended number is not a
   quantity that exists -- it is an artefact of the blending. The test contract lists
   *"any B and C accuracy or timing value is merged into one field"* as a hard failure, which
   is why `PracticeSession` and `GameSession` are two models rather than one flat row.

2. **A technical fault is never rendered as disengagement.** ``c_engagement_score`` can be
   low because a child disengaged or because the telemetry broke, and those demand opposite
   responses from a teacher. `GameSession.data_quality` carries that distinction explicitly,
   and when quality is not ``ok`` the engagement and frustration figures are suppressed to
   ``None`` rather than shown with a caveat a UI might drop. Making the honest thing the only
   available thing is the point -- see `dashboard_service._game_session`.

3. **Absolute mastery values are never served** (backend_plan.md section 3 / 6.5).
   `b_skill_certification_results` is a private table whose values are documented as
   ``TEST_FIXTURE_ONLY`` and "never exposed through any public DTO", and live BKT applies
   identical parameters to all seven skills with ``theta_b = 0.8`` -- so the number is not a
   publishable quantity. `SkillProgress` therefore carries a DIRECTION and a PRACTICE COUNT,
   and no ``p_l``/``skill_estimate``/mastery value in any form. A skill with fewer than four
   observations has no slope and sends ``null``, never ``0.0`` -- "we cannot tell yet" and
   "flat" are different claims.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from app.domain.dashboard import Disclosed, TrajectoryState, _Base

#: Rule 3. Fewer than this many observations means no slope may be reported.
MIN_OBSERVATIONS_FOR_SLOPE = 4

#: Rule 2. Anything other than `ok` means the Component C figures are not trustworthy and
#: must not be presented as a statement about the learner.
DataQuality = Literal["ok", "technical_issue", "incomplete_telemetry"]


class PracticeSession(_Base):
    """Component B only. See rule 1 -- never merged with `GameSession`."""

    accuracy_rate: float | None = None
    total_questions: int | None = None
    correct_responses: int | None = None
    hint_requests: int | None = None
    median_item_response_time_sec: float | None = None


class GameSession(_Base):
    """Component C only. See rule 1.

    `engagement_score` and `frustration_index` are suppressed to ``None`` whenever
    `data_quality` is not ``ok`` (rule 2). The composite components are carried alongside the
    composites because a frustration index of 0.6 driven by an error run means something
    different to a teacher than the same 0.6 driven by inactivity burden.
    """

    accuracy_rate: float | None = None
    task_completion_rate: float | None = None
    median_task_latency_sec: float | None = None
    engagement_score: float | None = None
    engagement_components: dict[str, float] | None = None
    frustration_index: float | None = None
    frustration_components: dict[str, float] | None = None
    learner_state: str | None = None
    current_difficulty_level: int | None = None
    difficulty_trend: str | None = None
    data_quality: DataQuality = "ok"


class SessionRecord(_Base):
    """One intervention session. `practice` and `games` are deliberately two nested objects
    rather than a flat row -- the shape itself is what stops them being merged downstream."""

    session_number: int
    session_date: dt.date | None = None
    practice_present: bool
    games_present: bool
    practice: PracticeSession | None = None
    games: GameSession | None = None


class SessionHistoryResponse(Disclosed):
    student_id: uuid.UUID
    display_name: str
    sessions: list[SessionRecord]


class SkillProgress(_Base):
    """Rule 3: direction and practice count. No mastery value, in any form.

    `relative_level` is permitted for bar positioning only, and the client never labels it
    with a number (backend_plan.md section 6.5). It is a rank position among this learner's
    own skills, not a mastery estimate.
    """

    skill: str
    direction: TrajectoryState
    practice_count: int
    relative_level: int | None = None


class SkillProgressResponse(Disclosed):
    student_id: uuid.UUID
    display_name: str
    skills: list[SkillProgress]


class EarlyWarningPoint(_Base):
    """One point on the early-warning curve: at session `t`, how many of the class had a
    prediction and how many carried a watch flag.

    `flag_rate` is reported per `t` and NEVER pooled across `t` -- 2+ prevalence rises from
    0.000 at t=3 to 0.144 at t=19, so a single pooled rate is dominated by whichever `t` the
    class happens to be clustered at and says nothing a teacher can act on.
    """

    t: int
    learners_with_prediction: int
    watch_flagged: int
    flag_rate: float


class ClassTrendPoint(_Base):
    t: int
    improving: int
    stable: int
    needs_attention: int
    unknown: int


class ClassReportResponse(Disclosed):
    classroom_id: uuid.UUID
    learner_count: int
    early_warning_curve: list[EarlyWarningPoint]
    practice_trajectory_trend: list[ClassTrendPoint]
