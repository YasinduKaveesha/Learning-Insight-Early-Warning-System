"""The explanation layer (work order B5.2) -- backend_plan.md section 6.4.

Turns one scored snapshot into at most three contributing signals and one plain-language
sentence of at most 280 characters, precomputed at write time (explanations are stable for a
fixed (model, snapshot) pair, so there is no reason to recompute them per request).

WHY THERE IS NO ``shap`` DEPENDENCY
-----------------------------------
The primary artefact is a ``Pipeline(impute -> scale -> clf)`` whose ``clf`` is a multinomial
``LogisticRegression``. For a linear model the SHAP value of feature ``j`` for class ``k`` is
exactly::

    phi[k][j] = coef[k][j] * (x[j] - E[x][j])

and the pipeline's ``StandardScaler`` has already centred the data, so ``E[z] = 0`` and the
expression collapses to ``coef[k][j] * z[j]`` on the scaled vector. That is not an
approximation of what ``shap.LinearExplainer`` would return -- it is the same number, computed
from the artefact's own coefficients, which is also why it cannot drift away from the model it
explains. Adding the library would buy nothing and pin a large dependency tree into serving,
where D18 already fixes the environment.

THE FOUR MANDATORY FILTERS (backend_plan.md section 6.4, from notebook_findings/06 section 3)
--------------------------------------------------------------------------------------------
1. ``sessions_observed`` and ``is_first_snapshot`` are removed from the explanation vocabulary
   ENTIRELY. "This reflects a longer observation history for this learner" was emitted 142
   times in the research build, 54 of them on elevated rows. A teacher cannot act on how long
   a child has been observed, and it exposes the calendar dependence the whole pipeline works
   to contain. `_EXCLUDED_FROM_VOCABULARY` extends this to the interaction term that embeds
   ``t`` and to the missingness indicators -- see the comment there.
2. **Never emit a protective sentence on a flagged learner.** 49.2% of elevated rows in the
   research build carried one; "skill mastery is progressing at a healthy pace" printed beside
   a watch flag is an incoherent product and reads as the system contradicting itself. Here a
   flagged learner's candidates are filtered to contributions that push TOWARD the predicted
   elevated class, and if none survive the neutral fallback is used instead.
3. **No raw feature names.** `DISPLAY_NAMES` is the single server-side mapping, so the wording
   cannot drift between callers.
4. **Every signal is framed as contributing, never causal.** Top-10 coefficient overlap across
   sensitivity arms is only 2/10-6/10 -- which features look important depends on an unresolved
   threshold decision, so the sentence must not promise that these ARE the reasons.

Also, and not negotiable: no model names, no probabilities, no jargon in the sentence, and
nothing here may read as a diagnosis. The system flags learners for teacher review.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from app.infrastructure.model_loading import LoadedModel

MAX_EXPLANATION_CHARS = 280

TOP_N = 3

# Filter 1, widened with its reasoning stated. Anything in here is invisible to the
# explanation vocabulary -- it can still drive the model, it just may never be shown to a
# teacher as a signal.
_EXCLUDED_FROM_VOCABULARY = frozenset(
    {
        # Filter 1, literally.
        "sessions_observed",
        "is_first_snapshot",
        # Same argument as filter 1: this is stagnant_skill_count multiplied by the session
        # index, so surfacing it would put calendar dependence in front of a teacher wearing
        # a different name.
        "stagnant_x_t",
        # Missingness indicators and the censoring counter. These describe the completeness
        # of our OWN telemetry, not anything about the child. "Game telemetry was missing"
        # is an engineering fact; a teacher can do nothing with it, and presenting it beside
        # a watch flag invites it to be read as a finding about the learner.
        "slope_censored_count",
        "frustration_mean_missing",
        "rt_variability_missing",
        "difficulty_floor_hits_missing",
        "c_telemetry_missing",
    }
)

# Filter 3: the ONE server-side mapping from feature name to teacher-facing wording. Plain
# language, no jargon, no raw feature names, and deliberately phrased as observations rather
# than judgements. Derived variants share their base wording with a time qualifier, because a
# teacher does not need to know the difference between a lag, a delta and a rolling mean --
# only that the signal concerns a change or a recent pattern.
_BASE_DISPLAY_NAMES: dict[str, str] = {
    "score_trend_slope": "the direction of recent practice scores",
    "score_avg_recent": "recent practice accuracy",
    "mastery_progression_rate": "the pace at which skills are being consolidated",
    "number_sense_mastery": "number sense",
    "weakest_skill_persistence": "how long the weakest skill has stayed weak",
    "rt_change_ratio": "how answer times are shifting",
    "rt_variability": "how much answer times vary",
    "rt_accuracy_tradeoff": "the balance between speed and accuracy",
    "game_latency_change_ratio": "the pace of game tasks",
    "error_recurrence_rate": "how often the same kind of error returns",
    "hint_avoidance": "how often hints are left unused",
    "hint_intensity": "how heavily hints are relied on",
    "engagement_decline_rate": "the direction of engagement during activities",
    "frustration_mean": "the overall level of frustration during activities",
    "frustration_slope": "the direction of frustration during activities",
    "difficulty_floor_hits": "how often tasks drop to the easiest level",
    "stagnant_skill_count": "the number of skills not currently moving",
    "zero_accuracy_window": "a recent stretch with no correct answers",
    "engagement_x_frustration": "engagement and frustration appearing together",
    "hint_intensity_x_accuracy": "hint use alongside accuracy",
}

_SUFFIX_QUALIFIERS: list[tuple[str, str]] = [
    ("_rollmean_prior", "{name}, averaged over earlier sessions"),
    ("_delta1", "the change since the previous session in {name}"),
    ("_lag1", "{name} in the previous session"),
]


def _display_name_for(feature: str) -> str | None:
    """Filter 3. Returns None for anything with no teacher-facing wording, which is treated
    as "not sayable" and dropped from the candidates rather than falling back to the raw
    name."""

    base = _BASE_DISPLAY_NAMES.get(feature)
    if base is not None:
        return base

    for suffix, template in _SUFFIX_QUALIFIERS:
        if feature.endswith(suffix):
            stem = _BASE_DISPLAY_NAMES.get(feature[: -len(suffix)])
            if stem is not None:
                return template.format(name=stem)
            return None

    return None


#: The model's 58 columns, in artefact order. Held here so the vocabulary can be built
#: WITHOUT a loaded model and still contain only real features -- an earlier revision
#: generated every base x suffix combination and produced 80 display names for a 58-column
#: model, i.e. wording for features that do not exist. `test_the_vocabulary_contains_only_
#: real_model_features` pins this list against the artefact itself, so the two cannot drift.
MODEL_FEATURES: tuple[str, ...] = (
    "score_trend_slope", "score_avg_recent", "mastery_progression_rate",
    "number_sense_mastery", "weakest_skill_persistence", "rt_change_ratio",
    "rt_variability", "rt_accuracy_tradeoff", "game_latency_change_ratio",
    "error_recurrence_rate", "hint_avoidance", "hint_intensity",
    "engagement_decline_rate", "frustration_mean", "frustration_slope",
    "difficulty_floor_hits", "stagnant_skill_count", "sessions_observed",
    "slope_censored_count", "frustration_mean_missing", "rt_variability_missing",
    "zero_accuracy_window", "difficulty_floor_hits_missing", "c_telemetry_missing",
    "is_first_snapshot", "score_trend_slope_lag1", "score_avg_recent_lag1",
    "mastery_progression_rate_lag1", "number_sense_mastery_lag1",
    "weakest_skill_persistence_lag1", "rt_accuracy_tradeoff_lag1",
    "error_recurrence_rate_lag1", "engagement_decline_rate_lag1", "frustration_mean_lag1",
    "stagnant_skill_count_lag1", "score_trend_slope_delta1", "score_avg_recent_delta1",
    "mastery_progression_rate_delta1", "number_sense_mastery_delta1",
    "weakest_skill_persistence_delta1", "rt_accuracy_tradeoff_delta1",
    "error_recurrence_rate_delta1", "engagement_decline_rate_delta1",
    "frustration_mean_delta1", "stagnant_skill_count_delta1",
    "score_trend_slope_rollmean_prior", "score_avg_recent_rollmean_prior",
    "mastery_progression_rate_rollmean_prior", "number_sense_mastery_rollmean_prior",
    "weakest_skill_persistence_rollmean_prior", "rt_accuracy_tradeoff_rollmean_prior",
    "error_recurrence_rate_rollmean_prior", "engagement_decline_rate_rollmean_prior",
    "frustration_mean_rollmean_prior", "stagnant_skill_count_rollmean_prior",
    "engagement_x_frustration", "hint_intensity_x_accuracy", "stagnant_x_t",
)


def _build_display_names() -> dict[str, str]:
    """Built once at import over `MODEL_FEATURES`, NOT from a loaded model -- so the
    vocabulary is a fixed, inspectable property of this module, `top_signals` can never run
    against a half-populated mapping, and it can only ever contain features the model
    actually has.
    """

    names: dict[str, str] = {}
    for feature in MODEL_FEATURES:
        if feature in _EXCLUDED_FROM_VOCABULARY:
            continue
        wording = _display_name_for(feature)
        if wording is not None:
            names[feature] = wording
    return names


DISPLAY_NAMES: dict[str, str] = _build_display_names()


# Filter 4 wording, and the safety rule: contributing, never causal; never a diagnosis.
_LEAD_IN = "Flagged for teacher review."
_NEUTRAL_FALLBACK = (
    "Flagged for teacher review. The contributing signals for this snapshot are not clear "
    "enough to summarise. Worth a look at recent practice."
)


def contributions_for(
    model: LoadedModel, features: dict[str, Any], predicted_class: int
) -> list[tuple[str, float]]:
    """Exact per-feature SHAP contributions toward `predicted_class`, as
    ``coef[k][j] * z[j]``. See the module docstring for why this needs no library.

    Returns ``(feature_name, contribution)`` for every one of the 58 features, unfiltered and
    unsorted -- filtering is the caller's job so the filters stay visible in one place.
    """

    pipeline = model.pipeline
    order = list(model.feature_order)
    frame = pd.DataFrame([features])[order]

    scaled = pipeline.named_steps["scale"].transform(
        pipeline.named_steps["impute"].transform(frame)
    )
    coefficients = pipeline.named_steps["clf"].coef_[predicted_class]

    return [
        (feature, float(coefficients[index] * scaled[0][index]))
        for index, feature in enumerate(order)
    ]


def top_signals(
    model: LoadedModel,
    features: dict[str, Any],
    *,
    predicted_class: int,
    watch_flag: bool,
) -> list[dict[str, Any]]:
    """The at-most-three signals that may be shown, after all four filters.

    On a flagged learner only contributions pushing TOWARD the predicted class survive
    (filter 2) -- a protective signal is never presented beside a watch flag. On an unflagged
    learner the strongest contributions in either direction are eligible, since there is no
    flag for them to contradict.
    """

    candidates = [
        (feature, value)
        for feature, value in contributions_for(model, features, predicted_class)
        if feature not in _EXCLUDED_FROM_VOCABULARY  # filter 1
        and feature in DISPLAY_NAMES  # filter 3
        and (value > 0 if watch_flag else value != 0)  # filter 2
    ]

    candidates.sort(key=lambda pair: (-abs(pair[1]), pair[0]))

    signals: list[dict[str, Any]] = []
    used_wording: set[str] = set()
    for feature, value in candidates:
        wording = DISPLAY_NAMES[feature]
        # Two different features can reduce to the same phrase (a lag and its delta of the
        # same base, say). Naming it twice in one sentence reads as a bug to a teacher, so
        # the weaker duplicate is dropped and the next distinct signal takes its place.
        if wording in used_wording:
            continue
        used_wording.add(wording)
        signals.append(
            {
                "feature": feature,
                "display_name": wording,
                "contribution": round(value, 6),
                "direction": "toward_review" if value > 0 else "away_from_review",
            }
        )
        if len(signals) == TOP_N:
            break

    return signals


def compose_sentence(signals: Sequence[dict[str, Any]]) -> str:
    """One sentence, at most 280 characters, contributing-not-causal (filter 4), no raw
    feature names (filter 3), no model name, no probability, no jargon.

    An empty `signals` means every candidate was filtered out -- on a flagged learner that is
    filter 2 having removed a protective top driver, which is exactly the case the neutral
    fallback exists for.
    """

    if not signals:
        return _NEUTRAL_FALLBACK

    names = [signal["display_name"] for signal in signals]
    if len(names) == 1:
        listed = names[0]
    else:
        listed = ", ".join(names[:-1]) + f" and {names[-1]}"

    sentence = (
        f"{_LEAD_IN} Signals contributing to this include {listed}. "
        "These are patterns in recent activity, not a diagnosis."
    )

    if len(sentence) > MAX_EXPLANATION_CHARS:
        # Drop the least important signal and recompose rather than truncating mid-word:
        # a cut-off sentence about a child is worse than a shorter complete one.
        return compose_sentence(signals[:-1])

    return sentence


def explain_snapshot(
    model: LoadedModel,
    features: dict[str, Any],
    *,
    predicted_class: int | None,
    watch_flag: bool,
) -> tuple[str | None, list[dict[str, Any]] | None]:
    """Returns ``(risk_explanation, shap_top3)`` for one snapshot.

    A learner below the warm-up floor has no ``predicted_class`` and therefore gets no
    explanation -- absence of a judgement and a benign judgement must stay different things
    (trap 7 of the decision layer). An unflagged learner gets its signals stored but no
    sentence: there is no claim to explain, and a fluent paragraph about a learner nobody
    flagged invites exactly the over-reading the safety rules exist to prevent.
    """

    if predicted_class is None:
        return None, None

    signals = top_signals(
        model, features, predicted_class=predicted_class, watch_flag=watch_flag
    )

    sentence = compose_sentence(signals) if watch_flag else None

    return sentence, (signals or None)
