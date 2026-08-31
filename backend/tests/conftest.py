from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.infrastructure import feature_builder, model_loading

# backend/tests/conftest.py -> tests -> backend -> Learning-Insight-Early-Warning-System (git root)
LIEWS_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = LIEWS_ROOT / "backend"
FIXTURES_DIR = BACKEND_ROOT / "tests" / "fixtures"

# `dataset/` sits ABOVE the git root (Learning-Insight-Early-Warning-System/) and is untracked
# -- see the "Data" section of the root .gitignore. A clean clone of this repo never has it, so
# the default research-panel source is the committed 90-row fixture below, not the real dataset.
# Set T3_RESEARCH_PANEL_PATH to point at the full out-of-repo dataset for a local full-coverage
# run (e.g. .../dataset/features/feature_matrix_at_t_seed20260828_n300.csv).
MIN_RESEARCH_PANEL_PATH = FIXTURES_DIR / "research_panel_min.csv"
FULL_RESEARCH_PANEL_ENV = "T3_RESEARCH_PANEL_PATH"

GOLDEN_PROBABILITIES_PATH = FIXTURES_DIR / "golden_predicted_probabilities.csv"
ARTEFACT_STORE_PATH = BACKEND_ROOT / "artefacts"
ACTIVE_MODEL_VERSION = "1.0.0"

FULL_RESEARCH_PANEL_PATH = os.environ.get(FULL_RESEARCH_PANEL_ENV)


@pytest.fixture(scope="session")
def loaded_model() -> model_loading.LoadedModel:
    artefact_path = model_loading.resolve_artefact_path(ARTEFACT_STORE_PATH, ACTIVE_MODEL_VERSION)
    return model_loading.load_model(artefact_path, model_version=ACTIVE_MODEL_VERSION)


@pytest.fixture(scope="session")
def research_panel():
    """The committed 10-learner fixture -- always available on a clean clone."""

    return feature_builder.load_research_panel(MIN_RESEARCH_PANEL_PATH)


@pytest.fixture(scope="session")
def feature_matrix(research_panel):
    return feature_builder.build_feature_matrix(research_panel)


@pytest.fixture(scope="session")
def full_research_panel():
    """The full out-of-repo research panel. Only usable when T3_RESEARCH_PANEL_PATH is set --
    callers must skip (via the `full_research_panel_available` marker condition) rather than
    call this unconditionally."""

    return feature_builder.load_research_panel(FULL_RESEARCH_PANEL_PATH)


@pytest.fixture(scope="session")
def full_feature_matrix(full_research_panel):
    return feature_builder.build_feature_matrix(full_research_panel)
