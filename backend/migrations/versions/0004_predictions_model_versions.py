"""predictions and model_versions (work order B3.4)

Creates exactly two tables plus one seed row:

* ``t3_predictions``     -- the model output, one row per
  ``(student_id, t, model_version, pipeline_run_id)`` (plan section 4.5). Five constraints,
  transcribed from the plan, NOT from ``docs/04`` section 4:

    - ``ck_t3_predictions_evidence``    -- the five evidence_status values
    - ``ck_t3_predictions_trajectory``  -- the four-value vocabulary, both trajectory columns
    - ``ck_t3_predictions_watch_flag``  -- ``watch_flag = (COALESCE(predicted_class, -1) >= 1
      AND sessions_completed >= 3)``. The ``COALESCE`` is load-bearing: ``predicted_class``
      is nullable and a bare ``predicted_class >= 1`` evaluates to NULL for warm-up-floor
      learners, which PostgreSQL PASSES -- leaving ``watch_flag`` unconstrained exactly where
      it matters most. ``docs/04`` line 277 has the bare form; it is wrong.
    - ``ck_t3_predictions_no_high``     -- ``risk_level IS NULL OR IN ('Low','Moderate')``;
      the schema-level guarantee that no code path can emit a High tier.
    - ``ck_t3_predictions_source_class`` -- the reduced-provenance enumeration.

  There is deliberately NO
  ``CHECK ((risk_level IS NULL) = (evidence_status <> 'sufficient_evidence'))`` -- it is
  unsatisfiable against real data (``docs/04`` carries a "do not reinstate" callout).
  ``risk_level_status`` (default ``CALIBRATION_PENDING``) carries that meaning instead.

* ``t3_model_versions`` -- the model card, one row per deployed artefact (plan section 4.7).
  Seeded here with the single ``1.0.0`` row from
  ``notebooks/outputs/models/model_card.json`` / ``dev_docs/MODEL_CARD.md``.

This is SCHEMA ONLY. The decision layer (B5) computes ``watch_flag``, ``rank_within_t``,
the trajectory values and the explanation; nothing here does.

Revision ID: 0004_predictions_model_versions
Revises: 0003_panel_and_features
Create Date: 2026-08-31

(Revision id is 31 chars -- t3_alembic_version.version_num is varchar(32).)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_predictions_model_versions"
down_revision: Union[str, Sequence[str], None] = "0003_panel_and_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The provenance root does not exist yet as a row (t3_pipeline_runs is populated by the
# loader in B4). The model card predates any pipeline run, so its NOT NULL pipeline_run_id
# (reduced-provenance set, no FK -- same choice as t3_classroom_keys) uses the nil UUID.
_NIL_UUID = "00000000-0000-0000-0000-000000000000"

# Verbatim from notebooks/outputs/models/model_card.json (reviewed by the ML supervisor).
_SEED_HEADLINE_METRICS = {
    "test_set_rows": 810,
    "macro_f1": 0.424,
    "balanced_accuracy": 0.477,
    "f2_any_stagnation": 0.689,
    "per_class": {
        "class_0": {"precision": 0.553, "recall": 0.550, "f1": 0.551, "support": 333},
        "class_1": {"precision": 0.634, "recall": 0.451, "f1": 0.527, "support": 426},
        "class_2plus": {"precision": 0.125, "recall": 0.431, "f1": 0.194, "support": 51},
    },
    "baselines": {
        "majority_class": {"macro_f1": 0.230, "balanced_accuracy": 0.333},
        "stratified_dummy": {"macro_f1": 0.338, "balanced_accuracy": 0.338},
        "t_only_logreg": {"macro_f1": 0.323, "balanced_accuracy": 0.423},
    },
    "benchmarks_not_deployed": {
        "random_forest": {"macro_f1": 0.426, "balanced_accuracy": 0.479},
        "decision_tree": {"macro_f1": 0.368, "balanced_accuracy": 0.381},
    },
}

_SEED_LIMITATIONS = [
    "Synthetic data throughout. All results come from generated learners; no real child's "
    "data is involved.",
    "Effective n is 300 learners, not 2700 rows. Rare-class results rest on tens of positive "
    "rows.",
    "The 2+ class is rare (6.0% at the primary arm, 0.000 prevalence at t=3) and has 12.5% "
    "precision -- roughly eight false alarms per true positive.",
    "No validated High tier exists. Tested across 5 n-arms x 3 h-arms x 2 gating rules; "
    "learner-clustered bootstrap CIs on (precision - prevalence) contain zero in every "
    "non-degenerate arm.",
    "A top-k% rank cut produces a DD inversion (DD lift 0.75-0.99 in every arm), flagging DD "
    "learners below their own base rate. The unfairness is created by the ranking rule, not "
    "the model. This is why no ranked tier ships.",
    "Calibration was tested and rejected. Outputs are ranking scores, not probabilities.",
    "Rank stability decays to ~0 within 6 sessions and is anti-correlated across the study. "
    "Ranking is current-snapshot triage, never a persistent designation.",
    "Feature importance is unstable across label sensitivity arms (top-10 coefficient "
    "overlap 2/10-6/10), which limits what the explanation layer may claim.",
    "The signal decays with time. By t~13 lift is ~1.0 and the model adds essentially "
    "nothing over flagging everyone.",
    "A binary 'needs attention' classifier is worse than trivial on the recall-weighted "
    "metric: flagging everyone scores F2 0.877 against the model's 0.689.",
    "dd_subtype is the constant 'none' across all 300 learners, so within-DD subtype "
    "auditing was impossible.",
    "Clustering is exploratory. k=2 was adopted but no k=2 artefact was saved; the model on "
    "disk is the superseded k=4. Do not use it.",
    "risk_level was never calibrated upstream and is NULL on all 2700 training rows.",
    "Live deployment is blocked: Components B and C do not currently produce the session "
    "number this model is indexed on.",
    "The producing environment (c3-ews) no longer exists. Nothing can be re-executed, "
    "refitted or re-audited until it is restored from environment.yml. The artefact requires "
    "scikit-learn 1.9.0.",
    "SCOPE: this model covers Component 3's stagnation/watch path ONLY.",
    "The reproducibility record is inconsistent: NB01 outputs under MKL BLAS, NB02 onward "
    "under OpenBLAS. Differences are ~1e-15 and change no conclusion.",
    "The model cannot express '3'. future_stagnant_count == 3 had 5 rows in 2700 and was "
    "merged into 2+. The top class is 'two or more', not a count.",
    "The margin over the calendar is 0.101: t-only baseline macro-F1 0.323 vs the model's "
    "0.424.",
    "DATA QUALITY (Component C): c_engagement_score is missing for 49.9% of sessions despite "
    "c_present = 1.000, and engagement_components.time_in_target_band_component is absent "
    "from the payload entirely.",
]


def upgrade() -> None:
    op.create_table(
        "t3_model_versions",
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("artefact_filename", sa.String(length=255), nullable=False),
        sa.Column("artefact_sha256", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column("training_dataset", sa.String(length=255), nullable=False),
        sa.Column("training_seed", sa.Integer(), nullable=False),
        sa.Column("sklearn_version", sa.String(length=16), nullable=False),
        sa.Column("headline_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "deployed_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Reduced provenance -- full six-column set (pipeline_run_id plain uuid, no FK).
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_class", sa.String(length=16), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("parameter_source_status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_model_versions_source_class"),
        ),
        sa.PrimaryKeyConstraint("model_version", name=op.f("pk_t3_model_versions")),
    )
    op.create_table(
        "t3_predictions",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("t", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("evidence_status", sa.String(length=32), nullable=False),
        sa.Column("sessions_completed", sa.Integer(), nullable=False),
        # Server-only. NEVER serialised to any client.
        sa.Column("prob_class_0", sa.REAL(), nullable=True),
        sa.Column("prob_class_1", sa.REAL(), nullable=True),
        sa.Column("prob_class_2plus", sa.REAL(), nullable=True),
        sa.Column("predicted_class", sa.SmallInteger(), nullable=True),
        # The teacher-facing signal (computed by B5).
        sa.Column("watch_flag", sa.Boolean(), nullable=False),
        sa.Column("rank_within_t", sa.Integer(), nullable=True),
        sa.Column("rank_percentile_within_t", sa.REAL(), nullable=True),
        # Descriptive. engagement_trajectory is STORED, NEVER SERVED (D17).
        sa.Column("practice_trajectory", sa.String(length=16), nullable=False),
        sa.Column("engagement_trajectory", sa.String(length=16), nullable=False),
        # Explanation.
        sa.Column("risk_explanation", sa.String(length=280), nullable=True),
        sa.Column("shap_top3", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Pending -- kept nullable and unpopulated.
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column(
            "risk_level_status",
            sa.String(length=32),
            server_default="CALIBRATION_PENDING",
            nullable=False,
        ),
        # Prediction-specific provenance.
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column("artefact_sha256", sa.String(length=64), nullable=False),
        sa.Column("inference_timestamp", sa.DateTime(timezone=True), nullable=False),
        # Reduced provenance -- pipeline_run_id (PK + FK) is the sixth column.
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_class", sa.String(length=16), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("parameter_source_status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "evidence_status IN ('sufficient_evidence', 'insufficient_exposure', "
            "'insufficient_future_evidence', 'censored_by_observation_end', "
            "'administratively_missing')",
            name=op.f("ck_t3_predictions_evidence"),
        ),
        sa.CheckConstraint(
            "practice_trajectory IN ('improving', 'stable', 'needs_attention', 'unknown') "
            "AND engagement_trajectory IN ('improving', 'stable', 'needs_attention', "
            "'unknown')",
            name=op.f("ck_t3_predictions_trajectory"),
        ),
        sa.CheckConstraint(
            "watch_flag = (COALESCE(predicted_class, -1) >= 1 AND sessions_completed >= 3)",
            name=op.f("ck_t3_predictions_watch_flag"),
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('Low', 'Moderate')",
            name=op.f("ck_t3_predictions_no_high"),
        ),
        sa.CheckConstraint(
            "source_class IN ('REAL', 'SYNTHETIC', 'IMPORTED', 'TEST')",
            name=op.f("ck_t3_predictions_source_class"),
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["t3_pipeline_runs.pipeline_run_id"],
            name="fk_t3_predictions_pipeline_run_id_t3_pipeline_runs",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["b_learners.learner_id"],
            name="fk_t3_predictions_student_id_b_learners",
        ),
        sa.PrimaryKeyConstraint(
            "student_id", "t", "model_version", "pipeline_run_id",
            name=op.f("pk_t3_predictions"),
        ),
    )
    op.create_index(
        "ix_t3_predictions_latest",
        "t3_predictions",
        ["student_id", sa.literal_column("t DESC")],
        unique=False,
    )

    # ---- Seed row: the one deployed artefact (model_card.json). ----------------------------
    model_versions = sa.table(
        "t3_model_versions",
        sa.column("model_version", sa.String),
        sa.column("model_name", sa.String),
        sa.column("artefact_filename", sa.String),
        sa.column("artefact_sha256", sa.String),
        sa.column("feature_version", sa.String),
        sa.column("training_dataset", sa.String),
        sa.column("training_seed", sa.Integer),
        sa.column("sklearn_version", sa.String),
        sa.column("headline_metrics", postgresql.JSONB),
        sa.column("limitations", postgresql.JSONB),
        sa.column("pipeline_run_id", postgresql.UUID),
        sa.column("source_class", sa.String),
        sa.column("source_system", sa.String),
        sa.column("parameter_source_status", sa.String),
    )
    op.bulk_insert(
        model_versions,
        [
            {
                "model_version": "1.0.0",
                "model_name": "component3_target_a_logreg",
                "artefact_filename": "nb05_primary_logreg_armA.joblib",
                "artefact_sha256": (
                    "019f000be16f533630b6e5d3215bf86597745a725cb13c5b989d03f45769db15"
                ),
                "feature_version": "1.0.0",
                "training_dataset": "training_table_seed20260828_n300_h5_sweepn4.csv",
                "training_seed": 20260828,
                "sklearn_version": "1.9.0",
                "headline_metrics": _SEED_HEADLINE_METRICS,
                "limitations": _SEED_LIMITATIONS,
                "pipeline_run_id": _NIL_UUID,
                "source_class": "SYNTHETIC",
                "source_system": "t3_model_card",
                "parameter_source_status": "TEST_FIXTURE_ONLY",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_t3_predictions_latest", table_name="t3_predictions")
    op.drop_table("t3_predictions")
    op.drop_table("t3_model_versions")
