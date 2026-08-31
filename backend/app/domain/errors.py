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
