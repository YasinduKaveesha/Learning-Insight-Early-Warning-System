"""Loads the primary model artefact from the versioned artefact store and scores feature rows.

See backend_plan.md section 5.3 and dev_docs/ML_BACKEND_HANDOVER_SPEC.md section 8/22.

Hard rules enforced here:
  - Never load `nb02_preprocessing_pipeline.joblib` -- it is a 19-feature research artefact.
  - Never call `fit`, `fit_transform` or `partial_fit`.
  - Verify SHA-256 before trusting the artefact; refuse to serve on mismatch.
  - Assert `sklearn.__version__ == '1.9.0'` explicitly (D18) -- the artefact loads under other
    versions with only a warning, and silently altered numerics is exactly that failure mode.
  - Column order for scoring comes from `pipeline.feature_names_in_`, read at load time --
    never hardcoded.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.pipeline import Pipeline

from app.domain.errors import FeatureContractViolation, ModelLoadError

REQUIRED_SKLEARN_VERSION = "1.9.0"
REQUIRED_PIPELINE_STEPS = ("impute", "scale", "clf")
REQUIRED_FEATURE_COUNT = 58

ARTEFACT_FILENAME = "nb05_primary_logreg_armA.joblib"
ARTEFACT_SHA256 = "019f000be16f533630b6e5d3215bf86597745a725cb13c5b989d03f45769db15"


@dataclass(frozen=True)
class LoadedModel:
    pipeline: Pipeline
    feature_order: tuple[str, ...]
    artefact_sha256: str
    model_version: str
    artefact_path: Path


@dataclass
class ModelState:
    """Holds the outcome of the startup load attempt for `/health/ready` to report.

    Exactly one of `model` / `error` is set. A load failure never crashes the process --
    it surfaces as 503 on `/health/ready` and on any scoring call, per backend_plan.md
    section 5.3: "If the artefact fails to load: 503. Never fall back to a heuristic."
    """

    model: LoadedModel | None = None
    error: Exception | None = None


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artefact_path(artefact_store: str | Path, model_version: str) -> Path:
    """`artefact_store` is the versioned store root (backend_plan.md section 5.3);
    the active artefact lives at `<artefact_store>/<model_version>/<ARTEFACT_FILENAME>`."""

    return Path(artefact_store) / model_version / ARTEFACT_FILENAME


def load_model(
    artefact_path: Path,
    *,
    model_version: str,
    expected_sha256: str = ARTEFACT_SHA256,
) -> LoadedModel:
    """Load, verify and return the primary model. Raises `ModelLoadError` on any failure --
    callers must return 503 and never fall back to a heuristic or a default class."""

    if not artefact_path.is_file():
        raise ModelLoadError(f"model artefact not found at {artefact_path}")

    actual_sha256 = _sha256_of(artefact_path)
    if actual_sha256 != expected_sha256:
        raise ModelLoadError(
            f"artefact checksum mismatch for {artefact_path}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    if sklearn.__version__ != REQUIRED_SKLEARN_VERSION:
        raise ModelLoadError(
            f"serving environment has scikit-learn {sklearn.__version__}, "
            f"required {REQUIRED_SKLEARN_VERSION} (decision D18) -- refusing to serve, "
            "the artefact loads under other versions with only a warning while silently "
            "altering numerics"
        )

    try:
        pipeline = joblib.load(artefact_path)
    except Exception as exc:  # noqa: BLE001 -- any load failure is a 503, not a crash
        raise ModelLoadError(f"failed to load artefact at {artefact_path}: {exc}") from exc

    steps = tuple(pipeline.named_steps.keys())
    if steps != REQUIRED_PIPELINE_STEPS:
        raise ModelLoadError(
            f"unexpected pipeline steps {steps}, expected {REQUIRED_PIPELINE_STEPS}"
        )

    feature_order = tuple(pipeline.feature_names_in_)
    if len(feature_order) != REQUIRED_FEATURE_COUNT:
        raise ModelLoadError(
            f"expected {REQUIRED_FEATURE_COUNT} model features, found {len(feature_order)}"
        )

    return LoadedModel(
        pipeline=pipeline,
        feature_order=feature_order,
        artefact_sha256=actual_sha256,
        model_version=model_version,
        artefact_path=artefact_path,
    )


def score_snapshot(model: LoadedModel, feature_row: dict[str, object]) -> dict[str, float | int]:
    """Score one (student_id, t) snapshot. Raises `FeatureContractViolation` -- listing the
    offending names -- if `feature_row` does not exactly match `model.feature_order`."""

    given = set(feature_row.keys())
    expected = set(model.feature_order)
    missing = frozenset(expected - given)
    extra = frozenset(given - expected)
    if missing or extra:
        raise FeatureContractViolation(missing=missing, extra=extra)

    frame = pd.DataFrame([feature_row])[list(model.feature_order)]
    proba = model.pipeline.predict_proba(frame)[0]
    return {
        "prob_class_0": float(proba[0]),
        "prob_class_1": float(proba[1]),
        "prob_class_2plus": float(proba[2]),
        "predicted_class": int(proba.argmax()),
    }
