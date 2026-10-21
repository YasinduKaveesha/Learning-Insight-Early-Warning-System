"""compD's teacher-side arithmetic, ported so the dashboard needs nothing from the student app's
backend (owner direction 2026-10-21).

Three sources, each ported as it stands, standard library only:

* the activity aggregates -- compD `server/app/services/features.py`, as the student app ports it
  (`Upadya/Dev/backend/app/application/d_features.py::compute_features`), restricted to the five
  values compD's teacher screens read;
* the per-learner, per-topic and dashboard maths, and the needs-support rule -- compD
  `server/app/routers/teacher.py:112-222`, rounding included;
* the recommendation text -- compD `services/recommendation.py`, English only, as the student app
  ports it (`d_recommendation.py`). The dashboard always reads in English, so the Sinhala strings
  are not copied. The student app does not store this text; it is built on read, and here too.

Nothing here computes a level. The four levels are the student app's stored profile, read as
they are.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

from app.domain.compd import (
    CompdDashboardStats,
    CompdProfile,
    CompdStudentPerformance,
    CompdStudentSummary,
    CompdTopicPerformance,
)

MS_PER_SECOND = 1000


@dataclass(frozen=True)
class Answer:
    """One `d_interactions` row: the fields compD's teacher maths reads, under the student app's
    names (`response_matched`, `assist_used`, owner decision D-011 A4)."""

    session_id: object
    topic: str
    response_time_sec: float
    attempts: int
    response_matched: bool
    assist_used: bool


@dataclass(frozen=True)
class Aggregates:
    total_questions: int
    accuracy: float
    avg_response_time_ms: float
    avg_attempts: float
    retry_rate: float
    hint_rate: float


def aggregate(answers: Sequence[Answer]) -> Aggregates:
    """compD `compute_features`, the five values the teacher screens use. Never called empty."""

    total = len(answers)
    return Aggregates(
        total_questions=total,
        accuracy=sum(1 for a in answers if a.response_matched) / total,
        avg_response_time_ms=float(mean(a.response_time_sec * MS_PER_SECOND for a in answers)),
        avg_attempts=float(mean(a.attempts for a in answers)),
        retry_rate=sum(1 for a in answers if a.attempts > 1) / total,
        hint_rate=sum(1 for a in answers if a.assist_used) / total,
    )


def topic_performance(answers: Sequence[Answer]) -> list[CompdTopicPerformance]:
    """compD `teacher.py:112-131`: grouped in first-seen order, then most questions first (a
    stable sort, so equal counts keep first-seen order)."""

    grouped: dict[str, list[Answer]] = defaultdict(list)
    for answer in answers:
        grouped[answer.topic].append(answer)
    result = []
    for topic, topic_answers in grouped.items():
        agg = aggregate(topic_answers)
        result.append(
            CompdTopicPerformance(
                topic=topic,
                total_questions=agg.total_questions,
                accuracy=round(agg.accuracy, 2),
                avg_response_time_sec=round(agg.avg_response_time_ms / MS_PER_SECOND, 1),
                retry_rate=round(agg.retry_rate, 2),
                hint_rate=round(agg.hint_rate, 2),
            )
        )
    result.sort(key=lambda item: item.total_questions, reverse=True)
    return result


def performance(answers: Sequence[Answer]) -> CompdStudentPerformance:
    """compD `teacher.py:134-149`. `answers` must be in `(created_at_utc, question_id)` order:
    `last_topic` is the last one's topic -- "a topic from the latest run", stable across reads."""

    if not answers:
        # compD `StudentPerformance()`'s defaults.
        return CompdStudentPerformance(
            total_questions=0, completed_sessions=0, accuracy=0.0, avg_response_time_sec=0.0,
            avg_attempts=1.0, retry_rate=0.0, hint_rate=0.0, last_topic=None, topics=[],
        )
    agg = aggregate(answers)
    return CompdStudentPerformance(
        total_questions=agg.total_questions,
        completed_sessions=len({a.session_id for a in answers}),
        accuracy=round(agg.accuracy, 2),
        avg_response_time_sec=round(agg.avg_response_time_ms / MS_PER_SECOND, 1),
        avg_attempts=round(agg.avg_attempts, 2),
        retry_rate=round(agg.retry_rate, 2),
        hint_rate=round(agg.hint_rate, 2),
        last_topic=answers[-1].topic,
        topics=topic_performance(answers),
    )


def has_low_profile(profile: CompdProfile | None) -> bool:
    """compD `teacher.py:152-160`."""

    if profile is None:
        return False
    return (
        profile.memory_level == "low"
        or profile.attention_level == "low"
        or profile.number_sense_level == "low"
        or profile.processing_speed_level == "Slow"
    )


def needs_support(student: CompdStudentSummary) -> bool:
    """compD `teacher.py:208-213`: a low level or Slow speed, or >= 5 questions under 60% (the
    ROUNDED accuracy, as compD compared it)."""

    return has_low_profile(student.latest_profile) or (
        student.performance.total_questions >= 5 and student.performance.accuracy < 0.6
    )


def dashboard_stats(students: Sequence[CompdStudentSummary]) -> CompdDashboardStats:
    """compD `teacher.py:195-222`: averages weighted by question count, over the per-learner
    values compD had already rounded."""

    with_activity = [s for s in students if s.performance.total_questions > 0]
    total_questions = sum(s.performance.total_questions for s in students)
    total_time = sum(s.performance.avg_response_time_sec * s.performance.total_questions for s in students)
    avg_accuracy = (
        sum(s.performance.accuracy * s.performance.total_questions for s in students) / total_questions
        if total_questions
        else 0.0
    )
    avg_response = total_time / total_questions if total_questions else 0.0
    return CompdDashboardStats(
        total_students=len(students),
        students_with_profiles=sum(1 for s in students if s.latest_profile is not None),
        total_interactions=sum(s.total_interactions for s in students),
        average_accuracy=round(avg_accuracy, 2) if with_activity else 0.0,
        average_response_time_sec=round(avg_response, 1) if with_activity else 0.0,
        needs_support_count=sum(1 for s in students if needs_support(s)),
    )


# ---------------------------------------------------------------- the recommendation text (English)

ACCURACY_LOW_BELOW = 0.5
ACCURACY_MODERATE_BELOW = 0.75
RESPONSE_TIME_HIGH_ABOVE_MS = 8000
RESPONSE_TIME_MODERATE_ABOVE_MS = 5000

_TIPS = {
    ("memory_level", "low"): "Memory support: Provide repeated practice with step-by-step guidance. Use visual aids and break problems into smaller steps.",
    ("memory_level", "medium"): "Memory support: Continue practice with moderate repetition. Introduce memory games to strengthen recall.",
    ("attention_level", "low"): "Attention support: Use shorter activities with more visual cues. Reduce distractions and provide frequent breaks.",
    ("attention_level", "medium"): "Attention support: Maintain engaging activities with moderate length. Use interactive elements to keep focus.",
    ("number_sense_level", "low"): "Number sense support: Focus on counting, number comparison, and number recognition activities. Use concrete objects and visual representations.",
    ("number_sense_level", "medium"): "Number sense support: Continue with number comparison and basic arithmetic practice. Gradually increase difficulty.",
    ("processing_speed_level", "Slow"): "Processing speed support: Avoid time-limited questions. Allow more thinking time and use untimed practice sessions.",
    ("processing_speed_level", "Moderate"): "Processing speed support: Gradually introduce gentle time targets. Encourage confident answering without rushing.",
}
_NO_TIPS_NEEDED = "Great performance! Continue with current activities and gradually increase the challenge level to maintain growth."
_AREA_LABEL = {
    "memory_level": "memory",
    "attention_level": "attention",
    "number_sense_level": "number sense",
    "processing_speed_level": "processing speed",
}
_NEEDS_SUPPORT_AT = {
    "memory_level": "low",
    "attention_level": "low",
    "number_sense_level": "low",
    "processing_speed_level": "Slow",
}
_DIMENSION_ORDER = ("memory_level", "attention_level", "number_sense_level", "processing_speed_level")


def recommendation(levels: dict[str, str], accuracy: float, avg_response_time_ms: float) -> str:
    """compD's insight paragraph, a blank line, then the tips -- exactly compD's
    `f"{insight_text}\\n\\n{rec_text}"`."""

    parts = []
    if accuracy < ACCURACY_LOW_BELOW:
        parts.append("The student answered less than half of the questions correctly.")
    elif accuracy < ACCURACY_MODERATE_BELOW:
        parts.append("The student showed moderate accuracy in answering questions.")
    else:
        parts.append("The student demonstrated good accuracy overall.")
    if avg_response_time_ms > RESPONSE_TIME_HIGH_ABOVE_MS:
        parts.append("Response times were higher than expected, suggesting the student may need more thinking time.")
    elif avg_response_time_ms > RESPONSE_TIME_MODERATE_ABOVE_MS:
        parts.append("Response times were moderate.")
    areas = [_AREA_LABEL[d] for d in _DIMENSION_ORDER if levels[d] == _NEEDS_SUPPORT_AT[d]]
    parts.append(
        f"Areas that may need additional support: {', '.join(areas)}."
        if areas
        else "No major areas of concern were identified."
    )
    tips = [_TIPS[(d, levels[d])] for d in _DIMENSION_ORDER if (d, levels[d]) in _TIPS]
    return f"{' '.join(parts)}\n\n{' '.join(tips) if tips else _NO_TIPS_NEEDED}"
