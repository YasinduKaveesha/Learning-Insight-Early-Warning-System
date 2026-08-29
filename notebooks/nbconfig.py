"""
Shared constants for Component 3 ML notebooks.

Nothing here touches data — paths and literal lists only. Every notebook in
this directory should `from nbconfig import *` (or import individual names)
rather than re-deriving these values.

Feature lists (MODEL_FEATURES, CLUSTER_FEATURES) are read verbatim from
dataset/features/feature_register.csv's `role` column — do not hand-edit
them without re-deriving from the register.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

NOTEBOOKS_DIR = Path(__file__).resolve().parent
REPO_DIR = NOTEBOOKS_DIR.parent
DATASET_DIR = (NOTEBOOKS_DIR / ".." / ".." / "dataset").resolve()

OUTPUTS_DIR = NOTEBOOKS_DIR / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
TABLES_DIR = OUTPUTS_DIR / "tables"
MODELS_DIR = OUTPUTS_DIR / "models"

# ---------------------------------------------------------------------------
# Data files (primary arm: h=5, n=4)
# ---------------------------------------------------------------------------

TRAINING_TABLE_PATH = DATASET_DIR / "training" / "training_table_seed20260828_n300_h5_sweepn4.csv"
FEATURE_MATRIX_PATH = DATASET_DIR / "features" / "feature_matrix_at_t_seed20260828_n300.csv"
AUDIT_LABELS_PATH = DATASET_DIR / "audit" / "t3_audit_labels_seed20260828_n300.csv"
FEATURE_MATRIX_MANIFEST_PATH = DATASET_DIR / "features" / "feature_matrix_manifest_seed20260828_n300.json"

FEATURE_REGISTER_PATH = DATASET_DIR / "features" / "feature_register.csv"
LABEL_REGISTER_PATH = DATASET_DIR / "labels_robustness" / "label_register.csv"
DATASET_CARD_PATH = DATASET_DIR / "DATASET_CARD.md"

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

RANDOM_SEED = 20260828

# ---------------------------------------------------------------------------
# Feature lists — read exactly from feature_register.csv's `role` column.
#
# NOTE: the register lists 23 `model`-role features (not 27 — see the EDA
# notebook's findings section for this discrepancy against the build brief).
# `changepoint_session` (role=report) and `error_type_profile[3]` (role=
# cluster, NOT COMPUTED) are correctly excluded.
# ---------------------------------------------------------------------------

MODEL_FEATURES = [
    "score_trend_slope",
    "score_avg_recent",
    "mastery_progression_rate",
    "number_sense_mastery",
    "weakest_skill_persistence",
    "rt_change_ratio",
    "rt_variability",
    "rt_accuracy_tradeoff",
    "game_latency_change_ratio",
    "error_recurrence_rate",
    "hint_avoidance",
    "hint_intensity",
    "guess_guard_rate",
    "engagement_consistency",
    "engagement_decline_rate",
    "frustration_mean",
    "frustration_slope",
    "difficulty_floor_hits",
    "stagnant_skill_count",
    "sessions_observed",
    "b_sessions_observed",
    "c_sessions_observed",
    "slope_censored_count",
]

# 7 ipsatised_mastery_* (one per skill) + number_sense_minus_operations
CLUSTER_FEATURES = [
    "ipsatised_mastery_counting",
    "ipsatised_mastery_number_sense",
    "ipsatised_mastery_place_value",
    "ipsatised_mastery_addition",
    "ipsatised_mastery_subtraction",
    "ipsatised_mastery_multiplication",
    "ipsatised_mastery_division",
    "number_sense_minus_operations",
]
