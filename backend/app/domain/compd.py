"""CompD's teacher side, served by Component 3 (owner direction 2026-10-21: "the teachers
dashboard should be independent even with compD that is a must").

compD's teacher screens re-homed in the dashboard. The field names are compD's own
(`compD/server/app/schemas.py:11-38,206-245`), so the dashboard ports compD's screens without a
second vocabulary -- including `correct_answer`, which this API has no reason to rename.

WHAT IS DELIBERATELY ABSENT, matching the dashboard's rule that no probability, confidence, score
or model name is ever served (`backend_plan.md` section 8): a profile here carries the four levels,
the recommendation text and five activity statistics. The confidence value and the model version
the student app stores beside each profile are never read into these shapes. compD's
`student_code` is dropped too.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Level = Literal["low", "medium", "high"]
SpeedLevel = Literal["Slow", "Moderate", "Fast"]
#: The student app's four topics -- the ones its children actually play (owner Q11).
Topic = Literal["Counting", "Addition", "Subtraction", "Division"]
Difficulty = Literal["Easy", "Medium", "Hard"]

MIN_OPTIONS = 2
MAX_OPTIONS = 6
MAX_CODE_LENGTH = 32
MAX_TEXT_LENGTH = 500
MAX_ANSWER_LENGTH = 255
MAX_OPTION_LENGTH = 255
MAX_DRAFT_COUNT = 10
MAX_INSTRUCTIONS_LENGTH = 300


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- students (read-only)


class CompdProfileStats(_Strict):
    """The activity statistics a profile's teacher view shows (compD ProfileResultScreen)."""

    accuracy: float
    avg_response_time_ms: float
    retry_rate: float
    hint_rate: float
    total_questions: int


class CompdProfile(_Strict):
    session_id: uuid.UUID
    memory_level: Level
    attention_level: Level
    number_sense_level: Level
    processing_speed_level: SpeedLevel
    recommendation: str
    features: CompdProfileStats
    generated_at: dt.datetime


class CompdTopicPerformance(_Strict):
    topic: str
    total_questions: int
    accuracy: float
    avg_response_time_sec: float
    retry_rate: float
    hint_rate: float


class CompdStudentPerformance(_Strict):
    total_questions: int
    completed_sessions: int
    accuracy: float
    avg_response_time_sec: float
    avg_attempts: float
    retry_rate: float
    hint_rate: float
    last_topic: str | None
    topics: list[CompdTopicPerformance]


class CompdStudentSummary(_Strict):
    student_id: uuid.UUID
    name: str | None
    grade: str | None
    classroom_name: str | None
    total_interactions: int
    latest_profile: CompdProfile | None
    last_activity_date: dt.datetime | None
    performance: CompdStudentPerformance


class CompdDashboardStats(_Strict):
    total_students: int
    students_with_profiles: int
    total_interactions: int
    average_accuracy: float
    average_response_time_sec: float
    needs_support_count: int


class CompdDashboardResponse(_Strict):
    stats: CompdDashboardStats
    students: list[CompdStudentSummary]


class CompdStudentProfiles(_Strict):
    """compD's `/latest` and `/history` in one: `items[0]` is the latest."""

    student_id: uuid.UUID
    name: str | None
    classroom_name: str | None
    items: list[CompdProfile]


# ---------------------------------------------------------------- question bank


def with_answer(options: list[str] | None, answer: str) -> list[str] | None:
    """compD's options rule (`ManualCreateScreen.tsx:53`): the answer is appended when the
    options leave it out; then 2-6 options. `None` stays `None` -- compD allowed a question with
    no options. A ValueError becomes a 422 naming the field."""

    if options is None:
        return None
    if any(not option.strip() or len(option) > MAX_OPTION_LENGTH for option in options):
        raise ValueError(f"each option must be 1-{MAX_OPTION_LENGTH} characters and not blank")
    result = list(options)
    if answer not in result:
        result.append(answer)
    if len(result) < MIN_OPTIONS:
        raise ValueError("add at least one other option")
    if len(result) > MAX_OPTIONS:
        raise ValueError(f"a question takes at most {MAX_OPTIONS} options, including the answer")
    return result


class CompdQuestion(_Strict):
    id: uuid.UUID
    question_code: str | None
    topic: Topic
    difficulty: Difficulty
    question_text: str
    correct_answer: str
    options: list[str] | None
    created_at: dt.datetime


class CompdQuestionCreate(_Strict):
    """compD `QuestionCreate`; also one AI draft."""

    question_code: str | None = Field(default=None, min_length=1, max_length=MAX_CODE_LENGTH)
    topic: Topic
    difficulty: Difficulty
    question_text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    correct_answer: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)
    options: list[str] | None = None

    @model_validator(mode="after")
    def _options_rule(self) -> "CompdQuestionCreate":
        self.options = with_answer(self.options, self.correct_answer)
        return self


class CompdQuestionUpdate(_Strict):
    """compD `QuestionUpdate`: any non-null subset, at least one (compD: 400 on none)."""

    question_code: str | None = Field(default=None, min_length=1, max_length=MAX_CODE_LENGTH)
    topic: Topic | None = None
    difficulty: Difficulty | None = None
    question_text: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT_LENGTH)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=MAX_ANSWER_LENGTH)
    options: list[str] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "CompdQuestionUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("at least one field is required")
        return self


class CompdQuestionList(_Strict):
    items: list[CompdQuestion]


class CompdMessage(_Strict):
    message: str
    id: uuid.UUID


class CompdDraftRequest(_Strict):
    topic: Topic
    difficulty: Difficulty
    count: int = Field(ge=1, le=MAX_DRAFT_COUNT)
    instructions: str | None = Field(default=None, max_length=MAX_INSTRUCTIONS_LENGTH)


class CompdDrafts(_Strict):
    """Drafts only -- NOT saved; a teacher saves each through `POST /questions`."""

    drafts: list[CompdQuestionCreate]
