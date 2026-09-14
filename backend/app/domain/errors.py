"""Domain-level error types for the model-loading and feature-contract boundary.

These are raised by infrastructure code (model loading, feature building) and translated
to HTTP responses by the API layer -- 503 for `ModelLoadError`, 422 (listing the offending
names) for `FeatureContractViolation`. See backend_plan.md section 8 "Errors".
"""

from __future__ import annotations


class ModelLoadError(RuntimeError):
    """The model artefact could not be loaded or failed verification.

    Never caught to fall back to a heuristic or a default class -- backend_plan.md section 5.3.
    """


class FeatureContractViolation(ValueError):
    """The constructed feature row does not exactly match `model.feature_names_in_`.

    Lists the offending names rather than silently dropping or defaulting a column
    -- backend_plan.md section 5.2 rule 1 and section 8 "Errors".
    """

    def __init__(self, *, missing: frozenset[str], extra: frozenset[str]) -> None:
        self.missing = missing
        self.extra = extra
        super().__init__(
            f"feature contract violation: missing={sorted(missing)} extra={sorted(extra)}"
        )


class AuthenticationError(RuntimeError):
    """A bearer token is missing, malformed, unverifiable, expired, or otherwise invalid.

    Raised by `app/infrastructure/auth.py`. Maps to HTTP 401 -- see backend_plan.md section 8
    "Auth" / "Errors". Never carries the raw token or any claim value in its message.
    """


class PrincipalNotAuthorizedError(RuntimeError):
    """A verified token's subject does not resolve to an authorized teacher.

    Raised by `app.application.principal_resolution.resolve_principal` (work order B2.3).
    Maps to HTTP 403. Covers every "missing row" case: no REAL `app_users` row, a
    `profile_type` other than `TEACHER`, no REAL `teacher_profiles` row, and an anonymous
    token presented while `T3_DEMO_MODE` is off. A missing row is ALWAYS this error, NEVER an
    insert -- Component 3 does not provision `app_users` or `teacher_profiles` rows; that is
    the student app's exclusive job (Agent Handower/BACKEND_SUPERVISOR_HANDOVER.md section
    8.4; rule 3-F1-adjacent "never write to a student-app table").
    """


class DemoPoolExhaustedError(RuntimeError):
    """No unclaimed `T3_DEMO_TEACHER_POOL` slot is left for a new anonymous subject.

    Raised by `app.application.principal_resolution.resolve_principal` (work order B2.3).
    Maps to HTTP 409 with the machine-readable error code below -- the same code whether the
    pool is unset/empty or genuinely exhausted, so the frontend has one branch to handle.
    """

    error_code = "demo_pool_exhausted"
