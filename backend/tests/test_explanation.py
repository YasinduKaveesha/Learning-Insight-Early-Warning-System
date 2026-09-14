"""The explanation layer (B5.2) -- backend_plan.md section 6.4's four mandatory filters.

The two tests worth reading are `test_filter2_*` and `test_filter1_*`: both guard failures
that a passing suite would otherwise hide, because a wrong explanation is fluent, plausible
English rather than an exception.
"""

from __future__ import annotations

import pytest

from app.application import explanation
from app.infrastructure import feature_builder


@pytest.fixture(scope="module")
def model(loaded_model):
    return loaded_model


@pytest.fixture(scope="module")
def a_feature_row(model, feature_matrix):
    """One real 58-column row -- `STU-0001` at `t=3`, the golden-vector snapshot, built from
    the committed 10-learner fixture so this suite runs on a clean clone."""

    return feature_builder.feature_row_for(
        feature_matrix, tuple(model.feature_order), student_id="STU-0001", t=3
    )


# --- filter 1: the calendar vocabulary is gone entirely ---------------------------------


def test_filter1_sessions_observed_and_is_first_snapshot_are_not_sayable():
    """'This reflects a longer observation history' was emitted 142 times in the research
    build, 54 of them on elevated rows. A teacher cannot act on it and it surfaces the
    calendar dependence the pipeline works to contain."""

    for banned in ("sessions_observed", "is_first_snapshot"):
        assert banned in explanation._EXCLUDED_FROM_VOCABULARY
        assert banned not in explanation.DISPLAY_NAMES


def test_filter1_extends_to_the_interaction_term_and_missingness_indicators():
    for banned in (
        "stagnant_x_t",
        "slope_censored_count",
        "c_telemetry_missing",
        "frustration_mean_missing",
    ):
        assert banned not in explanation.DISPLAY_NAMES


def test_filter1_excluded_features_never_reach_top_signals(model, a_feature_row):
    signals = explanation.top_signals(
        model, a_feature_row, predicted_class=1, watch_flag=True
    )
    names = {signal["feature"] for signal in signals}
    assert not (names & explanation._EXCLUDED_FROM_VOCABULARY)


# --- filter 2: never a protective sentence on a flagged learner -------------------------


def test_filter2_a_flagged_learner_never_gets_a_protective_signal(model, a_feature_row):
    """49.2% of elevated rows in the research build carried one. 'Skill mastery is
    progressing at a healthy pace' beside a watch flag is an incoherent product."""

    signals = explanation.top_signals(
        model, a_feature_row, predicted_class=1, watch_flag=True
    )
    assert all(signal["contribution"] > 0 for signal in signals)
    assert all(signal["direction"] == "toward_review" for signal in signals)


def test_filter2_falls_back_to_neutral_when_every_candidate_is_protective():
    """The case the fallback exists for: filter 2 removes every candidate, so there is
    nothing left to say. It must say that, not say something reassuring."""

    assert explanation.compose_sentence([]) == explanation._NEUTRAL_FALLBACK
    assert "healthy" not in explanation._NEUTRAL_FALLBACK.lower()
    assert "good" not in explanation._NEUTRAL_FALLBACK.lower()


def test_filter2_an_unflagged_learner_gets_no_sentence_at_all(model, a_feature_row):
    sentence, signals = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=0, watch_flag=False
    )
    assert sentence is None
    assert signals is not None  # stored for later inspection, just never narrated


# --- filter 3: no raw feature names -----------------------------------------------------


def test_filter3_no_raw_feature_name_appears_in_any_sentence(model, a_feature_row):
    sentence, _ = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=2, watch_flag=True
    )
    assert sentence is not None
    for feature in model.feature_order:
        assert feature not in sentence


def test_the_vocabulary_contains_only_real_model_features(model):
    """Pins `MODEL_FEATURES` against the artefact. An earlier revision generated every
    base x suffix combination and produced 80 display names for a 58-column model -- wording
    for features that do not exist. Harmless in output, but it meant the mapping could not be
    trusted as a description of what the model can say."""

    assert explanation.MODEL_FEATURES == tuple(model.feature_order)
    assert set(explanation.DISPLAY_NAMES) <= set(model.feature_order)


def test_no_two_signals_in_one_sentence_share_the_same_wording(model, a_feature_row):
    """A lag and its delta can reduce to the same phrase; naming it twice reads as a bug."""

    for predicted_class in (0, 1, 2):
        for flag in (True, False):
            signals = explanation.top_signals(
                model, a_feature_row, predicted_class=predicted_class, watch_flag=flag
            )
            wordings = [signal["display_name"] for signal in signals]
            assert len(wordings) == len(set(wordings))


def test_qualified_display_names_compose_into_real_english():
    """The base names must be noun phrases. An earlier revision phrased them as "a change
    in ..." and the delta template then produced "the change since the previous session in a
    change in engagement during activities"."""

    for wording in explanation.DISPLAY_NAMES.values():
        assert "in a change in" not in wording
        assert "change since the previous session in the change" not in wording


def test_filter3_every_display_name_is_plain_language():
    for feature, wording in explanation.DISPLAY_NAMES.items():
        assert "_" not in wording, f"{feature} display name looks like a raw name"
        assert wording == wording.lower() or wording[0].isupper()


# --- filter 4: contributing, never causal; and the safety rules -------------------------


def test_filter4_the_sentence_is_contributing_not_causal(model, a_feature_row):
    sentence, _ = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=1, watch_flag=True
    )
    assert sentence is not None
    assert "contributing" in sentence.lower()
    for causal in ("because", "caused by", "due to", "the reason"):
        assert causal not in sentence.lower()


def test_the_sentence_never_diagnoses(model, a_feature_row):
    """Rule 1 of the project: the system flags learners for teacher review. It does not
    diagnose, detect, identify or screen."""

    sentence, _ = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=2, watch_flag=True
    )
    assert sentence is not None
    lowered = sentence.lower()
    for banned in ("dyscalculia", "diagnos", "disorder", "screen", "detect", "identifies"):
        if banned == "diagnos":
            assert "not a diagnosis" in lowered  # the only permitted use
            continue
        assert banned not in lowered


def test_the_sentence_carries_no_model_name_or_probability(model, a_feature_row):
    sentence, _ = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=1, watch_flag=True
    )
    assert sentence is not None
    lowered = sentence.lower()
    for banned in ("logreg", "logistic", "random forest", "model", "shap", "class", "%"):
        assert banned not in lowered
    assert not any(character.isdigit() for character in sentence)


def test_the_sentence_is_within_280_characters(model, a_feature_row):
    for predicted_class in (1, 2):
        sentence, _ = explanation.explain_snapshot(
            model, a_feature_row, predicted_class=predicted_class, watch_flag=True
        )
        assert sentence is not None
        assert len(sentence) <= explanation.MAX_EXPLANATION_CHARS


def test_compose_sentence_drops_a_signal_rather_than_truncating_mid_word():
    long_signals = [
        {"display_name": "x" * 120, "feature": f"f{i}", "contribution": 1.0}
        for i in range(3)
    ]
    sentence = explanation.compose_sentence(long_signals)
    assert len(sentence) <= explanation.MAX_EXPLANATION_CHARS
    assert not sentence.endswith("...")
    assert sentence.endswith(".")


# --- the contributions themselves -------------------------------------------------------


def test_contributions_are_exact_shap_for_a_linear_model(model, a_feature_row):
    """phi[k][j] = coef[k][j] * z[j] on the centred vector, and the per-class contributions
    plus the intercept must reconstruct the decision function exactly. If this holds, the
    numbers are identical to shap.LinearExplainer's -- which is why there is no dependency."""

    import numpy as np
    import pandas as pd

    contributions = explanation.contributions_for(model, a_feature_row, predicted_class=1)
    total = sum(value for _feature, value in contributions)

    pipeline = model.pipeline
    frame = pd.DataFrame([a_feature_row])[list(model.feature_order)]
    scaled = pipeline.named_steps["scale"].transform(
        pipeline.named_steps["impute"].transform(frame)
    )
    expected = float(pipeline.named_steps["clf"].decision_function(scaled)[0][1])
    intercept = float(pipeline.named_steps["clf"].intercept_[1])

    assert total + intercept == pytest.approx(expected, abs=1e-9)


def test_contributions_cover_all_58_features(model, a_feature_row):
    contributions = explanation.contributions_for(model, a_feature_row, predicted_class=0)
    assert len(contributions) == 58
    assert [name for name, _ in contributions] == list(model.feature_order)


def test_top_signals_returns_at_most_three_ordered_by_absolute_contribution(
    model, a_feature_row
):
    signals = explanation.top_signals(
        model, a_feature_row, predicted_class=1, watch_flag=False
    )
    assert len(signals) <= explanation.TOP_N
    magnitudes = [abs(signal["contribution"]) for signal in signals]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_a_below_floor_snapshot_gets_no_explanation_at_all(model, a_feature_row):
    """Absence of a judgement and a benign judgement must stay different things."""

    sentence, signals = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=None, watch_flag=False
    )
    assert sentence is None
    assert signals is None


def test_explanations_are_deterministic_for_a_fixed_model_and_snapshot(
    model, a_feature_row
):
    first = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=1, watch_flag=True
    )
    second = explanation.explain_snapshot(
        model, a_feature_row, predicted_class=1, watch_flag=True
    )
    assert first == second
