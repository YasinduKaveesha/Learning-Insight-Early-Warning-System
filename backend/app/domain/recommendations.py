"""Recommendation response and request models (work order B7) -- `docs/10` section 6, `docs/13`.

The same ``extra="forbid"`` discipline as :mod:`app.domain.dashboard`, and `DISCLOSURE` rides on
every top-level response through `Disclosed`.

WHAT THIS MODULE DELIBERATELY DOES NOT CONTAIN
----------------------------------------------
* **A closed enum of action kinds.** D7 closed the *vocabulary* by decision, not by schema;
  `docs/13` section 5 forbids a closed enum in either tier, so that adding a kind is not a
  breaking change and an unknown kind renders through a fallback instead of failing validation.
* **Any trigger -> action mapping, or anything that creates a recommendation.** That mapping is
  open (`dev_docs/QUESTIONS_FOR_ML_TEAM_4.md`). This module describes recommendations; it cannot
  produce one.
* **An absolute mastery value.** `docs/10`'s example evidence carries `mastery_current`, but
  backend_plan.md section 6.5 and rule 3 of :mod:`app.domain.sessions` forbid serving mastery in
  any form. `FORBIDDEN_EVIDENCE_KEYS` is applied on the way OUT, whatever a future generator
  stores -- the same "the honest thing is the only available thing" choice as `GameSession`.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field, field_validator

from app.domain.dashboard import Disclosed, _Base

TeacherStatus = Literal["pending", "accepted", "dismissed", "modified"]
TargetComponent = Literal["B", "C", "both"]

#: Never served inside `trigger.evidence`, whatever is stored.
#: `population` / `dd_subtype` and latent traits: `docs/13` section 2 evidence constraints.
#: `mastery_*`: rule 3 of `app.domain.sessions` (absolute mastery is not a publishable quantity).
#: `prob_*` / `predicted_class` / `risk_*`: backend_plan.md section 8 never-serialised list.
FORBIDDEN_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "population",
        "dd_subtype",
        "latent_trait",
        "mastery_current",
        "mastery",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2plus",
        "predicted_class",
        "risk_score",
        "risk_level",
    }
)


def filter_evidence(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Drop every forbidden key, including any key that merely starts with a forbidden stem
    such as `prob_` or `mastery_current` -- a new column named `prob_class_3` must not slip
    through a list someone forgot to update."""

    if not evidence:
        return {}
    return {
        key: value
        for key, value in evidence.items()
        if key not in FORBIDDEN_EVIDENCE_KEYS
        and not key.startswith(("prob_", "risk_", "mastery_current"))
    }


class ActionOut(_Base):
    """`{kind, detail}`. `kind` is a plain string on purpose -- see the module docstring."""

    kind: str
    detail: dict[str, Any] = Field(default_factory=dict)


class TriggerOut(_Base):
    type: str
    skill: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecommendationOut(_Base):
    recommendation_id: uuid.UUID
    student_id: uuid.UUID
    issued_at_intervention_session: int
    expires_after_session: int
    target_component: TargetComponent
    trigger: TriggerOut
    proposed_action: ActionOut
    evidence_summary: str = Field(max_length=280)
    teacher_status: TeacherStatus
    teacher_modified_action: ActionOut | None = None
    #: D10 -- no write-back in v1. Served so a client can see they are null, never set here.
    b_applied_at_intervention_session: int | None = None
    c_applied_at_intervention_session: int | None = None
    #: Derived at read time from the learner's latest session in the active run. A
    #: recommendation past its `expires_after_session` is not "active" even while `pending`.
    expired: bool = False


class RecommendationListResponse(Disclosed):
    student_id: uuid.UUID
    recommendations: list[RecommendationOut]


class ModifyRequest(_Base):
    teacher_modified_action: ActionOut

    @field_validator("teacher_modified_action")
    @classmethod
    def _kind_is_not_blank(cls, action: ActionOut) -> ActionOut:
        # Open vocabulary, but not an empty one: a blank kind is not a modification a teacher
        # made, and it would be unreadable in the research log.
        if not action.kind.strip():
            raise ValueError("teacher_modified_action.kind must not be blank")
        return action
