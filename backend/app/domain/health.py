"""Response models for the health endpoints.

`/health/ready` reports model-artefact status only for this work order (build-order step 1) --
no database check yet; that arrives with the DB work order. See backend_plan.md section 1.
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
    checks: dict[str, str]
