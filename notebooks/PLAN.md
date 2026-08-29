# Notebook Plan — Component 3 ML Layer

Owner: ML supervisor. Implementers work one notebook at a time from the prompts in §5.

---

## 1. The two targets

Everything in this plan serves two targets, in this order:

**Target A — `future_stagnant_count` (the modelling target).**
*"Looking at what we know about this learner up to session `t`, how many skills are likely to
stagnate during the next 5 sessions?"*
Values 0/1/2/3. Present and populated on all 2,700 rows. This is what a model can actually be
trained on today.

**Target B — teacher-facing `risk_level` (the final product target).**
*"How much attention should the teacher give this learner?"*
Low / Moderate / High. This is what ships on the dashboard — the thing the whole component exists
to produce.

**They are connected, and the connection is the open problem.** Doc 07 §4 defines B as two threshold
cuts on A. Those cuts are `CALIBRATION_PENDING` and the `risk_level` column is empty on all 2,700
rows. So the route to the product target is: model A honestly → produce the calibration evidence →
the owner sets the cuts → B follows deterministically from A.

We build toward B the whole way. We do not invent the cuts.

---

## 2. Treat the dataset as unknown

The dataset arrives with an excellent `DATASET_CARD.md` and feature/label registers. **Read them, but
do not let them substitute for looking at the data.** The instruction is to work it as an unknown
dataset: full EDA, real preprocessing, feature engineering, dimensionality reduction where it earns
its place. The card tells us what the builder intended; the EDA tells us what is actually there, and
those are different questions.

Two things the card does *not* remove the need for:

- The features were computed by a builder making documented interpretation calls (the feature
  register is full of `BUILDER INTERPRETATION:` notes). Those choices are visible in the
  distributions, and we should see them for ourselves.
- Engineered features are permitted and wanted — but **doc 08 rule 3-F8 (transitive leakage) means
  every feature we add must be re-audited.** A feature built entirely from permitted fields can still
  reconstruct `population`. That is why the leakage audit sits *after* feature engineering.

---

## 3. Facts established before planning

Read from the registers and manifests, verified against the files:

- **2,700 supervised rows, 300 learners, 9 rows each.** Primary arm `h=5, n=4`.
- `split` already materialised, grouped by `student_id`, 210 train / 90 test learners.
- Target A distribution: `0:1213, 1:1326, 2:156, 3:5`.
- Target B (`risk_level`) empty on every row; `risk_level_status = CALIBRATION_PENDING` everywhere.
- `evidence_status = sufficient_evidence` on all 2,700 rows (ineligible snapshots were never emitted).
- **`error_type_profile[3]` NOT COMPUTED** — doc 06 names the three buckets but never defines which of
  the 8 `error_class_dist` keys map into which, so the builder refused to invent it. The GMM shape set
  is therefore **8 features**, not 11.
- `changepoint_session` NOT COMPUTED (optional, no threshold defined).
- Population labels quarantined in `dataset/audit/t3_audit_labels_*.csv`. **Audit and
  evaluation-stratification only. Never a feature.**

---

## 4. Notebook sequence

Strictly ordered. NB03 is a gate; nothing downstream runs on a failed audit.

| # | Notebook | Purpose | Serves |
|---|---|---|---|
| 01 | `01_eda.ipynb` | Full exploratory analysis of an unknown dataset. Structure, distributions, missingness, relationships, target behaviour, panel/temporal structure. | both |
| 02 | `02_preprocessing_and_feature_engineering.ipynb` | Null strategy, scaling, encoding, engineered features (including cross-`t` lags), PCA as diagnostic and as an optional arm. | both |
| 03 | `03_leakage_audit_sf038.ipynb` | **GATE.** SF-038 on the original *and* engineered feature sets. Stagnation sign check. LS-analogues. | both |
| 04 | `04_profile_clustering_gmm.ipynb` | `k` sweep, GMM on shape features, soft memberships + entropy, ARI vs population. | both |
| 05 | `05_target_a_stagnation_modelling.ipynb` | **Target A.** Grouped-split modelling of `future_stagnant_count`. LogReg primary, DT/RF benchmarks, per-cluster metrics, calibration, SHAP, early-detection curve. | A |
| 06 | `06_target_b_risk_level.ipynb` | **Target B.** From A's predictions to the teacher-facing risk level: calibration evidence, cut candidates, the dashboard-shaped output. | B |
| 07 | `07_sensitivity_and_robustness.ipynb` | `n` sweep, `h` sweep, cross-arm stability. | both |

### Shared conventions

- Kernel **`Python (c3-ews)`**. `RANDOM_SEED = 20260828` (the dataset's own seed). Seed everything.
- **Group by `student_id`** for every split and CV fold. Materialised `split` for the headline,
  `StratifiedGroupKFold` for CV. Rows are strongly autocorrelated — effective n ≈ 300, not 2,700.
- All preprocessing inside a `Pipeline`, fitted on train folds only. Nothing fitted on the full data.
- Figures → `outputs/figures/`, tables → `outputs/tables/`, models → `outputs/models/`.
- Every notebook ends with a **Findings** markdown cell: what was measured, what passed, what failed,
  what decision it raises. That cell is what the supervisor reads to decide the next step.
- Never impute `risk_level` or `trajectory_indicators`. Never use `population` as a feature.
- A metric that looks too good is a leakage suspicion, not a success.

### Open path question (owner decision)

`dataset/` sits **outside** the repo (`../../dataset` from `notebooks/`). Works locally, breaks on
clone. Options: keep and document, copy in, or submodule/DVC. Interim: the path lives in one place,
`notebooks/nbconfig.py`, so switching is a one-line change.

---

## 5. Prompts

Hand these to the implementer one at a time. Do not run ahead of the supervisor's review.

### NB01 — Exploratory data analysis

```
Build notebooks/01_eda.ipynb in the Learning-Insight-Early-Warning-System repo.
Kernel: Python (c3-ews). Seed 20260828.

First create notebooks/nbconfig.py holding ONLY path constants and the seed — DATASET_DIR
(../../dataset), the dataset file paths, OUTPUTS dirs, RANDOM_SEED, and the feature-role lists
(MODEL_FEATURES, CLUSTER_FEATURES). Every later notebook imports from it. No logic in that file.

Treat this as an UNKNOWN dataset. Read dataset/DATASET_CARD.md and the feature/label registers for
context, but explore the data on its own terms and verify rather than assume. Where what you find
disagrees with the card, say so — that is a finding.

STRUCTURE
1. Load the training table (h=5, n=4 arm), feature matrix, manifests, and the quarantined audit
   labels. Report shapes, dtypes, memory.
2. The panel: 300 learners x 9 snapshots at t in {3,5,...,19}. Verify rows per learner, t grid,
   and that every row satisfies t+5 <= 25. Assert.
3. Split integrity: 210/90 learners, zero student_id overlap. Assert.
4. Confirm 'population' and 'dd_subtype' appear NOWHERE in the feature matrix or training table.
   Assert.

MISSINGNESS
5. Null rate per feature, overall and per t. Heatmap (features x t). Doc 06 s5: a feature null for
   most learners at t=3 is honest, not broken — slope features need w=4 observations. Interpret
   the pattern against that; identify which nulls are structural warm-up vs which are something
   else. Flag any feature null at a rate that would make it unusable.
6. Missingness correlation: do features go null together? Is nullness itself patterned by learner?

DISTRIBUTIONS
7. describe() plus a histogram/KDE grid for every model-role feature. Note skew, bounds, spikes at
   0 or 1, and anything that looks like a degenerate or near-constant column.
8. Outliers: IQR and z-score counts per feature. Do NOT remove anything — this is a census. Ratio
   features (rt_change_ratio, game_latency_change_ratio, rt_accuracy_tradeoff) are division-based
   and may have heavy tails; inspect them specifically.
9. hint_avoidance / hint_intensity: doc 06 explains these are split because hint usage is
   non-monotonic (U-shaped). Look at the joint distribution and confirm the split behaves as the
   doc describes.

RELATIONSHIPS
10. Correlation heatmap (Spearman and Pearson) of model-role features. List |r| > 0.9 pairs
    explicitly as multicollinearity candidates for NB02.
11. Feature vs Target A: for each model-role feature, its relationship to future_stagnant_count —
    boxplots by count, and a mutual-information ranking. Which features carry signal at all?
12. Variance inflation factor for the model-role set.

TARGET
13. Target A distribution: counts and proportions, overall and by t. Plot. Note the imbalance
    (only 161/2700 rows have count >= 2, only 5 have count 3) and what that means for modelling —
    class 3 is almost certainly not learnable separately.
14. Target A by learner: does the same learner sit at the same count across their 9 snapshots?
    Quantify within-learner target autocorrelation. This is the single most important thing to
    know before splitting.
15. Confirm Target B (risk_level) and trajectory_indicators are entirely null and that
    risk_level_status is CALIBRATION_PENDING everywhere. Do NOT fill them. State plainly that the
    product target does not yet exist and NB06 is where we build toward it.
16. evidence_status value counts. Confirm all rows are sufficient_evidence and explain what that
    means — ineligible snapshots were never emitted, so this table carries no censoring.

TEMPORAL / PANEL
17. Trajectories: plot feature and target trajectories over t for a sample of learners. Do the
    panels look like the longitudinal structure the docs describe?
18. Does anything drift systematically with t (feature means, null rates, target rate)? A model
    trained across all t must cope with that.

End with a Findings cell: what this dataset actually looks like, which features are usable, which
are degenerate or too-null, the multicollinearity set, the signal ranking, the target's imbalance
and autocorrelation, and any disagreement with the card. Recommend what NB02 should do.
Do NOT model. Do NOT preprocess. Use population labels ONLY for the absence check in step 4.
```

### NB02 — Preprocessing and feature engineering

```
Build notebooks/02_preprocessing_and_feature_engineering.ipynb. Kernel Python (c3-ews).
Seed 20260828. Read NB01's Findings cell first and act on its recommendations.
Read docs/06 s5 (null handling) and docs/08 (leakage) before writing code.

Everything here must be a Pipeline-compatible transformer fitted on TRAIN ONLY. Nothing fitted on
the full dataset. Nothing that reads a session later than t.

NULL STRATEGY (open decision 3-Q6 — you are producing a justified proposal, not closing it)
1. Per feature, choose and JUSTIFY a treatment. Doc 06 s5 constraints are binding:
     - NEVER impute a null slope to 0.0 — zero means 'flat', a strong claim in a system whose
       target is flatness. This is the doc's explicit leakage warning.
     - A null is not a zero. No carry-forward across sessions.
     - hint_intensity is null BY DEFINITION when the rate is 0; hint_avoidance carries that case.
   Preferred approach: explicit missingness indicator columns + a defensible imputation for the
   value, so the model can learn from the fact of absence rather than a fabricated value.
2. Compare at least two strategies empirically later in NB05; here, build both and state the
   default. Report the null-indicator columns you add.

SCALING / TRANSFORMS
3. Standardise inside the Pipeline. For the heavy-tailed ratio features NB01 flagged, evaluate
   log1p or quantile transforms and show before/after distributions.
4. Handle the multicollinearity NB01 identified — drop, combine, or keep with a note. Justify.

FEATURE ENGINEERING
5. Engineer new features and justify each one against the docs. Permitted and encouraged:
     - Cross-t LAG features within a learner: value at the previous snapshot, and the delta
       between snapshots. These are SAFE — an earlier snapshot is still <= t — and they add the
       trajectory-of-the-trajectory information the panel exists to carry. Verify the shift is
       backward-only and never crosses a student_id boundary. This is the highest-value addition.
     - Interactions the docs motivate: engagement x frustration, hint_intensity x accuracy,
       stagnant_skill_count x sessions_observed.
     - Ratios/composites within a single component's pipeline.
   FORBIDDEN, restate in markdown and enforce:
     - Any merge of Component B item response time with Component C game latency (3-F9 / D2).
       There is no mean_response_time and there must not be one.
     - Anything from a session later than t (3-F2).
     - Component C's gameplay_mastery_estimate standing in for B's mastery (3-F3).
     - population / dd_subtype in any form (3-F1).
6. For every engineered feature, record: name, formula, source fields, and the doc rule that
   permits it. Write this to outputs/tables/engineered_feature_register.csv in the same spirit as
   the dataset's own feature_register.csv.

DIMENSIONALITY REDUCTION
7. PCA on the model-role feature set. Report the scree plot, cumulative explained variance, and
   the component loadings. Interpret what the leading components represent.
8. State the trade-off explicitly in markdown: doc 07 makes Logistic Regression primary BECAUSE it
   is interpretable by design, and doc 05 requires SHAP explanations reduced to a plain-language
   sentence for the teacher. PCA components are not explainable to a teacher. So:
     - PCA is used here as a DIAGNOSTIC (structure, multicollinearity, severity dominance).
     - It may be carried into NB05 as a clearly-labelled BENCHMARK arm only.
     - It must NOT become the primary model's feature space unless the owner accepts losing the
       explanation layer. Flag that as a decision, do not take it.
9. Also report PCA on the 8 clustering shape features specifically — NB04 needs the loadings to
   confirm no single severity-bearing feature dominates component 1 (doc 08 CL-3).

OUTPUT
10. Persist the fitted preprocessing pipeline to outputs/models/ and the engineered feature matrix
    to outputs/tables/. Keep student_id, t and split alongside.

End with a Findings cell: the null strategy and its justification, every engineered feature and
its warrant, what PCA revealed about the structure, and an explicit handover note that NB03 MUST
re-run the leakage audit on the engineered set before anything is modelled (doc 08, rule 3-F8).
```

### NB03 — Leakage audit (SF-038) — GATE

```
Build notebooks/03_leakage_audit_sf038.ipynb. Kernel Python (c3-ews). Seed 20260828.
Read docs/08_LEAKAGE_AND_SAFETY_RULES.md IN FULL first — this notebook implements it.

This is a build-blocking gate. It runs AFTER feature engineering because doc 08 rule 3-F8 requires
re-auditing after EVERY feature change: a feature built entirely from permitted fields can still
reconstruct population. Reproduce SF-038 independently rather than quoting the shipped
sf038_report json, then compare your numbers to it.

1. Join features to dataset/audit/t3_audit_labels_*.csv on student_id. State in markdown that
   these labels are quarantined, audit-only, and never features.
2. SF-038 on the ORIGINAL feature set: DecisionTreeClassifier(max_depth=4) predicting population,
   student_id-GROUPED train/test split, repeated over many random splits. Report ALL of:
   balanced accuracy (the gate — worst-case and mean), raw accuracy, majority-class baseline,
   macro-F1, one-vs-rest ROC-AUC, confusion matrix.
   GATE: worst-case balanced accuracy < 0.70. Assert. Shipped report says 0.3487 — say whether you
   reproduce it.
3. SF-038 on the ENGINEERED feature set from NB02. Same protocol, same gate. If any engineered
   feature pushes balanced accuracy up, identify WHICH and drop it. This is the whole point of
   running the audit here.
4. Explain in markdown WHY balanced accuracy is the gate and not raw accuracy (~70% of learners
   are TD, so a TD-always classifier scores ~70% raw having learned nothing).
5. Positive control: inject a synthetic population-encoding feature, confirm balanced accuracy
   goes to ~1.0 and the gate FAILS. This proves the detector fires. Report it.
6. Per-feature leakage ranking: how much population signal does each feature carry alone, for both
   original and engineered sets. slope_censored_count is called out in doc 06 s4 as a specific
   leakage channel (censoring is not missing-at-random) — report it explicitly whatever it shows.
7. Stagnation sign check (doc 06 s3, BUILD-BLOCKING): mean stagnant_skill_count for DD vs TD.
   DD MUST exceed TD. The previous build had this inverted and was measuring success. Assert, and
   plot the distributions.
8. LS-5 / LS-6 / LS-7 cannot be run as written — they are defined on risk_level, which is null.
   Do NOT invent thresholds to run them. Run their honest analogue on future_stagnant_count:
   fraction of DD learners at count 0 (LS-5 analogue), fraction of TD learners at count >= 1
   (LS-6 analogue), and the full population x count crosstab with a zero-cell check (LS-7
   analogue). Label these clearly as ANALOGUES and note the real gates stay blocked until NB06's
   calibration closes.

End with a Findings cell stating PASS or FAIL on each gate, for both feature sets. If any gate
fails, say so loudly, name the offending features, and STOP — nothing downstream may proceed on a
failed audit.
```

### NB04 — Profile clustering

```
Build notebooks/04_profile_clustering_gmm.ipynb. Kernel Python (c3-ews). Seed 20260828.
Read docs/05 s6 and docs/08 s5 first. Do not start until NB03 has PASSED.

Fit difficulty-profile clusters on SHAPE, not severity.

1. Fitting set is exactly 8 features: ipsatised_mastery_{counting, number_sense, place_value,
   addition, subtraction, multiplication, division} and number_sense_minus_operations.
   error_type_profile[3] is specified in doc 05 s6 but was NOT COMPUTED by the builder (the
   8-key -> 3-bucket mapping is undefined in every doc) — record this as a documented deviation in
   markdown, do not invent it.
   Explain what ipsatisation does and why it makes these shape and not level.
2. Standardise inside a Pipeline. Decide and state whether you cluster per (student, t) row or per
   learner — if per row, note the autocorrelation caveat and keep it consistent downstream.
3. k sweep over k = 2..10: BIC, AIC, silhouette, Davies-Bouldin. Plot all four curves. k is NOT
   fixed in advance — let the sweep choose and justify from the curves. The prior build used k=4;
   do not anchor on that.
4. Refit GaussianMixture(covariance_type='full', n_init=10) at the chosen k. Keep hard labels AND
   soft probabilities AND cluster_entropy.
5. GATE: ARI(cluster, population) < 0.30. Assert. Report the cluster x population crosstab whether
   it passes or fails. State plainly (doc 08 CL-5) that a clean clustering which maps onto
   population is a FAILURE, not a finding.
6. PCA loadings on the shape set (reuse NB02 s9): confirm no single severity-bearing feature
   dominates component 1 (CL-3).
7. Visualise: PCA and t-SNE scatter coloured by cluster; normalised centroid bar chart; heatmap of
   cluster feature profiles.
8. K-Means benchmark at the same k. Report both and compare (CL-6: if the soft memberships are
   never consumed downstream there is no defensible reason to prefer GMM — flag that NB05 must use
   them).
9. Interpret each cluster from its centroid AFTER fitting. Neutral names cluster_1..k are the
   shipped identifier. Descriptive behavioural names may be proposed as a SUGGESTION in markdown
   only. NEVER 'magnitude', 'operations' or 'mixed' — those are the generator's latent categories
   and using them would claim a recovered subtype the system was never given.
10. Persist {gmm, scaler, profile_map} together with joblib. Save per-row cluster + soft probs +
    entropy to outputs/tables/.

End with a Findings cell: chosen k and why, the four curves' verdict, the ARI result, what each
cluster appears to represent, and how stable assignments are across t for the same learner.
```

### NB05 — Target A: stagnation modelling

```
Build notebooks/05_target_a_stagnation_modelling.ipynb. Kernel Python (c3-ews). Seed 20260828.
Read docs/05 s8 and docs/07 first. Requires NB03 PASSED and NB04 complete.

TARGET A: future_stagnant_count — "how many skills are likely to stagnate in the next 5 sessions?"
This is the honest modelling target. Target B (teacher-facing risk_level) is built on top of it in
NB06; do NOT attempt risk_level here and do NOT invent its cuts.

Model Target A BOTH ways and report both:
  (a) binary: future_stagnant_count >= 1 — 'will stall on something'. Roughly 55/45.
  (b) multiclass: 0 / 1 / 2+ — collapse 3 into 2+, only 5 rows have count 3. Justify the collapse.

1. Features: the NB02 engineered matrix, minus anything NB03 flagged as leaking. Doc 05 s8: under
   a forward-window design there is NO disjoint feature pool — the separation is temporal — so all
   features at t are permitted. Explicitly EXCLUDE population and cluster dummies (doc 05 s8: the
   cluster is reported alongside the prediction and used to STRATIFY evaluation, never to make it).
2. Split: materialised grouped `split` column for the headline. Assert no student_id overlap. CV
   via StratifiedGroupKFold(n_splits=5) grouped on student_id. Every model in a Pipeline with its
   own preprocessing so nothing leaks across a fold.
3. Models: LogisticRegression PRIMARY, DecisionTree and RandomForest as benchmarks. Explain in
   markdown that LogReg is primary as a POSITION not a compromise (doc 07: for a consequential
   decision about a child, interpretable-by-design beats post-hoc explanation of an opaque model);
   the ensembles exist so the cost of that choice is measured, not assumed to be zero.
   RandomizedSearchCV scored on macro-F1.
4. Optional clearly-labelled BENCHMARK arm: the PCA feature space from NB02. Report it as a
   benchmark only and restate that it cannot be primary without losing the explanation layer.
5. Class imbalance: compare class_weight='balanced' against SMOTE-ENN (inside the pipeline, fitted
   on train folds only). Report which you chose and WHY.
6. Metrics per model: confusion matrix, precision/recall/F1/F2, macro-F1, balanced accuracy, ROC
   (one-vs-rest for multiclass), PR curve. ALWAYS alongside the majority-class baseline.
   F2 matters most — missing a stalling child costs more than a false alarm a teacher can dismiss.
7. PER-CLUSTER evaluation — REQUIRED (doc 05 s8). Precision, recall, F2 within each NB04 cluster,
   using the soft memberships as well as hard labels. Global metrics are documented in the
   early-warning literature to conceal subgroup disparities; per-profile reporting is one of this
   component's contributions.
8. Calibration curve + Brier score for the primary model. NB06 depends on these probabilities
   being trustworthy, so this is not optional.
9. SHAP on the primary model: global importance, and per-learner top-3 reduced to a plain-language
   sentence (doc 07's risk_explanation). Show 3 worked examples in teacher-readable English.
10. EARLY-DETECTION CURVE: flag rate and precision as a function of t. Doc 05 calls this 'the
    artefact the whole panel structure exists to produce' — give it real attention. How early could
    the system have raised each learner?
11. Ablation across feature groups (accuracy/progress, B timing, C timing, errors, help-seeking,
    engagement, stagnation, structural, engineered). Which groups carry the signal?

Persist models to outputs/models/, per-row predicted probabilities to outputs/tables/ — NB06
consumes those.

On the numbers: honest forecasting is HARDER than the prior build's rule reproduction. Present
modest metrics as integrity, not failure. A very high AUC is evidence of a bug — investigate, do
not celebrate. Cite NO metric from the previous build, not even as a baseline.

End with a Findings cell: headline metrics vs baseline, which model won and whether the LogReg
interpretability cost is acceptable, per-cluster disparities, what the early-detection curve says
about how early the system is useful, and what SHAP says drives the flag.
```

### NB06 — Target B: teacher-facing risk level

```
Build notebooks/06_target_b_risk_level.ipynb. Kernel Python (c3-ews). Seed 20260828.
Requires NB05 complete. Read docs/07 s3-s4, docs/08 s6, docs/12 before writing code.

TARGET B: the teacher-facing risk level — "how much attention should the teacher give this
learner?" Low / Moderate / High. This is the final product target and the reason the component
exists. It is currently CALIBRATION_PENDING with an empty column.

THE RULE FOR THIS NOTEBOOK: produce everything needed to ship Target B EXCEPT the threshold
choice, which is the owner's. Build the machinery, generate the evidence, leave the cuts as a
parameter. Do not write a chosen threshold into any persisted artefact.

1. Restate the chain in markdown: features at t -> predicted future_stagnant_count (NB05) ->
   two threshold cuts -> Low/Moderate/High. Doc 07 s4 gives the shape:
     risk_level = High     when future_stagnant_count >= [CUT_HIGH]
                = Moderate when future_stagnant_count >= [CUT_MOD]
                = Low      otherwise
   Note that doc 07 also permits the High/Moderate cut to order additionally on future-window
   frustration_mean and engagement_decline_rate as a severity ranking — those are legitimate LABEL
   inputs over the future window and PROHIBITED as same-t predictors. Explore that as an option.
2. CALIBRATION EVIDENCE TABLE — the core deliverable. For every candidate cut pair on
   future_stagnant_count, show the resulting Low/Moderate/High distribution and check it against
   doc 08 s6's stated expectations:
     - overall High proportion approx 8-15%
     - >= 5% of TD learners at Moderate or High (LS-6)
     - >= 10% of DD learners at Low (LS-5)
     - no zero cell in the population x risk crosstab (LS-7)
   Present as: cut pair -> distribution -> which expectations met/missed. Do NOT pick one.
3. REPORT THE TENSION HONESTLY: only 161/2700 rows (6.0%) have count >= 2 and only 5 have count 3.
   So a High band cut at >= 2 yields ~6%, BELOW doc 08's 8-15% expectation, and a cut at >= 1
   yields ~55%, far above it. The label as currently parameterised may not be able to satisfy the
   doc's expectation at all. That is a genuine finding and an owner decision — it may mean the
   expectation, the label definition, or the n parameter needs revisiting. State it plainly.
4. Threshold-on-probability alternative: instead of cutting the predicted COUNT, cut the model's
   predicted PROBABILITY from NB05. Show the same evidence table for probability cuts. This
   usually gives finer control over the High-band rate. Present both routes; recommend neither.
5. Implement risk_level as a PARAMETERISED function (cuts passed in, not hardcoded) so the owner's
   eventual decision is a one-line change. Demonstrate it end-to-end with cuts clearly labelled
   ILLUSTRATIVE_ONLY and never persisted as final.
6. The other three output layers must travel with it (doc 07's four layers):
     - evidence_status: already sufficient_evidence on all rows here; show where a real deployment
       would emit insufficient_exposure and why a learner below warm-up gets NO risk level rather
       than a default of Low.
     - trajectory_indicators: UNRESOLVED — no derivation rules exist in any doc, no 3-Q number
       assigned. Emit empty with status RULES_UNDEFINED. Do NOT invent rules.
     - teacher_facing_output: the fixed string 'flags learners for teacher review'.
7. Build the DASHBOARD-SHAPED OUTPUT: one row per learner at their latest t, carrying risk_level
   (illustrative), risk_score, evidence_status, gmm_profile + cluster_entropy, and the SHAP-derived
   plain-language risk_explanation sentence from NB05. This is what doc 11/12 render. Show it as a
   table for ~20 learners so the supervisor can see what the teacher would see.
8. Restate the safety rules in markdown as they apply to this surface: never presented as a
   diagnosis; the phrase is 'flags learners for teacher review'; no risk score reaches a child or
   parent (3-F6); high cluster_entropy raises 'needs teacher judgement'; nothing is applied without
   a teacher decision (3-F5).

End with a Findings cell: the calibration evidence table, the 8-15% tension, which route
(count-cut vs probability-cut) you recommend the owner consider and why, and an explicit statement
that the threshold decision remains OPEN and belongs to the owner. Nothing in this notebook closes
3-Q1.
```

### NB07 — Sensitivity and robustness

```
Build notebooks/07_sensitivity_and_robustness.ipynb. Kernel Python (c3-ews). Seed 20260828.
Requires NB05 and NB06 complete.

1. n sweep. Re-run NB05's primary model across the n arms 3, 4, 6, 8 from dataset/labels_sweep/.
   EXCLUDE n=2 from the primary comparison — 81.7% positive rate, near-degenerate, a majority-class
   predictor scores 81.7% without learning anything — but show it separately, labelled
   sensitivity-only, to demonstrate exactly why it is excluded. Never compare a raw-accuracy figure
   from n=2 against another arm. Report how metrics and the positive rate move with n.
   ROBUSTNESS ONLY, never model selection.
2. h sweep. Same across h=3 and h=7 from dataset/labels_robustness/ against the h=5 primary.
   Robustness only — these are never additional production labels.
3. Stability: does the same learner get flagged across arms? Cohen's kappa between arms, and a
   learner-level agreement matrix. If the flag is unstable across n, that weakens any claim built
   on a single arm — report it either way.
4. Re-run the NB06 calibration evidence table under each n arm. Does the doc 08 s6 8-15% High
   expectation become reachable at a different n? That is directly relevant to open decision 3-Q1
   and may be the most useful thing in this notebook.
5. Seed stability: re-run the primary model across several seeds and report the spread. A result
   that moves materially with the seed is not a result.

End with a Findings cell: how stable the model and the flag are across arms and seeds, whether any
n arm makes the doc's risk distribution expectation reachable, and what all of it says about
open decision 3-Q1. Recommend, do not decide.
```

---

## 6. Decisions this plan surfaces for the owner

| # | Decision | Where the evidence comes from |
|---|---|---|
| 1 | `risk_level` cuts — Target B's thresholds (3-Q1 / CALIBRATION_PENDING) | NB06 evidence table, NB07 across arms |
| 2 | Whether the doc 08 §6 "8–15% High" expectation is reachable from this label at all | NB06 §3, NB07 §4 |
| 3 | Count-cut vs probability-cut route to Target B | NB06 §4 |
| 4 | Whether PCA components may replace interpretable features (costs the SHAP explanation layer) | NB02 §8 |
| 5 | Whether `error_type_profile[3]`'s bucket mapping gets defined, restoring 3 clustering features | NB04 §1 |
| 6 | `trajectory_indicators` derivation rules — no `3-Q` number assigned yet | out of scope; needs a doc decision |
| 7 | Warm-up floor (3-Q3 / 3-Q7) | NB01 null profile |
| 8 | Per-feature missing-session treatment (3-Q6) | NB02 §1 proposal |
| 9 | Dataset-outside-repo path strategy | §4 above |
