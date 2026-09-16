"""The class-wide student overview (2026-09-16).

One response carrying, for every learner in a class, exactly what the student screen already
fetches in three separate calls -- `StudentDetail`, `SkillProgressResponse` and the active
`RecommendationListResponse`. Nothing new is served: each part is the same model, built by the
same code, so a learner opened from this payload and a learner opened on their own cannot differ.

It exists so the dashboard can load a class's student pages in ONE request and open any of them
instantly, instead of paying several round trips to a hosted database per learner.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.domain.dashboard import Disclosed, StudentDetail
from app.domain.recommendations import RecommendationListResponse
from app.domain.sessions import SkillProgressResponse


class StudentOverviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: StudentDetail
    skills: SkillProgressResponse
    recommendations: RecommendationListResponse


class ClassStudentOverviewsResponse(Disclosed):
    classroom_id: uuid.UUID
    students: list[StudentOverviewOut]
