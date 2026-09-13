"""Component 3's ORM layer: the declarative `Base`, its `MetaData`, and the mapped tables.

Importing this package registers every `t3_` table (and the `classrooms` shadow) on
`metadata`, which is what `migrations/env.py` hands Alembic as `target_metadata`.
"""

from __future__ import annotations

from app.infrastructure.db.base import Base, metadata
from app.infrastructure.db.models import (
    ClassroomKey,
    FeaturesAtT,
    ModelVersion,
    Panel,
    Prediction,
    PipelineRun,
    Recommendation,
    RecommendationTransition,
    b_learners,
    classrooms,
)
from app.infrastructure.db.provenance import (
    ProvenanceCoreMixin,
    ProvenanceMixin,
    source_class_check,
)

__all__ = [
    "Base",
    "ClassroomKey",
    "FeaturesAtT",
    "ModelVersion",
    "Panel",
    "Prediction",
    "PipelineRun",
    "Recommendation",
    "RecommendationTransition",
    "ProvenanceCoreMixin",
    "ProvenanceMixin",
    "b_learners",
    "classrooms",
    "metadata",
    "source_class_check",
]
