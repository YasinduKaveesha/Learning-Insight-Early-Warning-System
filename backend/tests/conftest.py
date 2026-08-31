from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure import feature_builder, model_loading

# backend/tests/conftest.py -> tests -> backend -> Learning-Insight-Early-Warning-System -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
LIEWS_ROOT = REPO_ROOT / "Learning-Insight-Early-Warning-System"
BACKEND_ROOT = LIEWS_ROOT / "backend"

RESEARCH_FEATURE_MATRIX_PATH = REPO_ROOT / "dataset" / "features" / "feature_matrix_at_t_seed20260828_n300.csv"
ENGINEERED_REFERENCE_PATH = LIEWS_ROOT / "notebooks" / "outputs" / "tables" / "24_engineered_feature_matrix.csv"
GOLDEN_PROBABILITIES_PATH = BACKEND_ROOT / "tests" / "fixtures" / "golden_predicted_probabilities.csv"
ARTEFACT_STORE_PATH = BACKEND_ROOT / "artefacts"
ACTIVE_MODEL_VERSION = "1.0.0"


@pytest.fixture(scope="session")
def loaded_model() -> model_loading.LoadedModel:
    artefact_path = model_loading.resolve_artefact_path(ARTEFACT_STORE_PATH, ACTIVE_MODEL_VERSION)
    return model_loading.load_model(artefact_path, model_version=ACTIVE_MODEL_VERSION)


@pytest.fixture(scope="session")
def research_panel():
    return feature_builder.load_research_panel(RESEARCH_FEATURE_MATRIX_PATH)


@pytest.fixture(scope="session")
def feature_matrix(research_panel):
    return feature_builder.build_feature_matrix(research_panel)
