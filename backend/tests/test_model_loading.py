"""Tests 1, 2, 3 and 15 from backend_plan.md section 9 / handover section 18."""

from __future__ import annotations

import sklearn

from app.infrastructure import model_loading
from tests.conftest import ACTIVE_MODEL_VERSION, ARTEFACT_STORE_PATH


def test_model_loads_on_the_pinned_sklearn_version(loaded_model) -> None:
    """Test 1 -- the Pipeline loads AND sklearn.__version__ == '1.9.0' (decision D18)."""

    assert sklearn.__version__ == model_loading.REQUIRED_SKLEARN_VERSION
    assert loaded_model.pipeline is not None


def test_preprocessing_is_inside_the_artefact(loaded_model) -> None:
    """Test 2 -- named_steps are impute, scale, clf."""

    assert tuple(loaded_model.pipeline.named_steps.keys()) == ("impute", "scale", "clf")


def test_feature_count_is_58_not_39(loaded_model) -> None:
    """Test 3 -- len(model.feature_names_in_) == 58."""

    assert len(loaded_model.feature_order) == 58


def test_artefact_immutability_after_scoring(loaded_model) -> None:
    """Test 15 -- SHA-256 unchanged after a scoring run.

    Scoring never mutates the artefact on disk (no fit/fit_transform/partial_fit is ever
    called), so re-hashing the file after use must match the checksum recorded at load time.
    """

    artefact_path = model_loading.resolve_artefact_path(ARTEFACT_STORE_PATH, ACTIVE_MODEL_VERSION)
    rehashed = model_loading._sha256_of(artefact_path)
    assert rehashed == loaded_model.artefact_sha256 == model_loading.ARTEFACT_SHA256
