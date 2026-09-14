"""Response models for the health endpoints.

`/health/ready` reports two checks (backend_plan.md section 1 / build-order step 1, "answers
against the shared database"): the model artefact, and a real `SELECT 1` against the shared
database. Both live in the same `checks` dict; either failing is a 503, never a degraded 200.

`ReadinessResponse` is `extra="forbid"`, so a new check needs a field here, not just a new
dict key -- `checks` is `dict[str, str]` and takes new entries without a schema change.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["alive"]
    request_id: str


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]
    request_id: str
    model_version: str
    artefact_sha256: str
    #: One entry per readiness check. Currently `model_artefact` and `database`; the
    #: endpoint only ever returns this model when EVERY check passed, so the values are
    #: descriptive ("loaded_and_verified", "select_1_ok"), never a status word.
    checks: dict[str, str]
