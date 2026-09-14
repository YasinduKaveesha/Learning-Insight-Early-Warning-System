"""The D35 rule, pinned clause by clause (`dev_docs/ANSWERS_TO_APP_TEAM_4.md`).

`evaluate` is pure, so every clause of the ruling has a test that fails if that clause is dropped
or its threshold drifts. The database side (issuing rules, idempotency) is exercised live in
`tests/test_recommendation_generator_live.py`.
"""

from __future__ import annotations

import pytest

from app.application import recommendation_generator as gen
from app.domain.recommendations import filter_evidence

SUB = "subtraction"


def _stuck(**overrides):
    """One skill that meets all three clauses with margin, for a flagged learner at session 19."""

    args = dict(
        session=19,
        watch_flag=True,
        mastery={SUB: 0.5},
        slopes={SUB: 0.001},
        opportunities={SUB: 12},
    )
    args.update(overrides)
    return gen.evaluate(**args)


def test_the_basic_case_issues_practice_on_the_stagnant_skill():
    c = _stuck()
    assert c is not None
    assert c.skill == SUB
    assert c.session == 19
    assert c.expires_after_session == 24


def test_the_thresholds_are_the_governed_docs06_definition():
    """Not EPSILON_PRACTICE (0.05). D38: that epsilon belongs to accuracy rate only."""

    assert gen.STAGNATION_SLOPE_EPSILON == 0.005
    assert gen.STAGNATION_MASTERY_THETA == 0.8
    assert gen.STAGNATION_MIN_OPPORTUNITIES == 4
    assert gen.STAGNATION_WINDOW == 4
    source = open(gen.__file__, encoding="utf-8").read().split('"""', 2)[2]
    assert "EPSILON_PRACTICE" not in source


@pytest.mark.parametrize(
    "overrides",
    [
        {"slopes": {SUB: 0.005}},  # clause 1 is strict: < 0.005
        {"slopes": {SUB: 0.03}},  # ordinary growth -- what condition A wrongly caught
        {"mastery": {SUB: 0.8}},  # clause 2 is strict: < 0.8
        {"opportunities": {SUB: 3}},  # clause 3: >= 4
    ],
)
def test_each_clause_is_required(overrides):
    assert _stuck(**overrides) is None


def test_boundary_values_just_inside_each_clause_fire():
    assert _stuck(slopes={SUB: 0.00499}, mastery={SUB: 0.79999}, opportunities={SUB: 4}) is not None


def test_a_falling_skill_is_stagnant():
    """Condition B could never fire under the old epsilon. Under docs/06 a negative slope meets
    clause 1 like any other slope below 0.005."""

    assert _stuck(slopes={SUB: -0.02}) is not None


@pytest.mark.parametrize("missing", ["mastery", "slopes", "opportunities"])
def test_a_missing_value_is_never_evidence_of_stagnation(missing):
    assert _stuck(**{missing: {}}) is None
    assert _stuck(**{missing: None}) is None


def test_the_watch_flag_is_required():
    """Q2: outside the flag, current stagnation predicts nothing (0.87 [0.00, 1.97])."""

    assert _stuck(watch_flag=False) is None


def test_skill_tiebreak_most_evidence_then_lowest_slope_then_alphabetical():
    both = dict(mastery={"addition": 0.5, SUB: 0.5})
    # most opportunities wins
    assert _stuck(**both, slopes={"addition": 0.0, SUB: 0.0}, opportunities={"addition": 6, SUB: 9}).skill == SUB
    # equal opportunities: lowest slope wins
    assert _stuck(**both, slopes={"addition": -0.01, SUB: 0.001}, opportunities={"addition": 8, SUB: 8}).skill == "addition"
    # full tie: alphabetical key, never curricular order
    assert _stuck(**both, slopes={"addition": 0.0, SUB: 0.0}, opportunities={"addition": 8, SUB: 8}).skill == "addition"


def test_an_excluded_skill_is_passed_over_and_the_next_one_chosen():
    """Q3 rule 3: a dismissed skill is not re-issued before its expiry -- but another stagnant
    skill still may be."""

    kwargs = dict(
        mastery={"addition": 0.5, SUB: 0.5},
        slopes={"addition": 0.0, SUB: 0.0},
        opportunities={"addition": 6, SUB: 9},
    )
    assert _stuck(**kwargs, excluded_skills=frozenset({SUB})).skill == "addition"
    assert _stuck(**kwargs, excluded_skills=frozenset({SUB, "addition"})) is None


def test_expiry_is_issue_plus_five_capped_at_session_25():
    assert _stuck(session=3).expires_after_session == 8
    assert _stuck(session=22).expires_after_session == 25


def test_the_summary_matches_the_ml_template_exactly():
    assert gen.evidence_summary(SUB, 19, 12) == (
        "In sessions 16–19, 12 practice questions on subtraction have not yet shown steady "
        "progress. Suggestion: more practice on subtraction."
    )
    assert gen.evidence_summary("place_value", 3, 4).startswith("In sessions 1–3, 4 practice questions on place value")


def test_the_summary_is_within_280_characters_for_every_skill():
    longest = max(
        (gen.evidence_summary(skill, 25, 999) for skill in gen.SKILL_SUMMARY_NAME), key=len
    )
    assert len(longest) <= 280


@pytest.mark.parametrize(
    "banned",
    ["diagnos", "detect", "identif", "screen", "risk", "struggl", "weak", "deficit", "probab", "model"],
)
def test_the_summary_uses_none_of_the_banned_words(banned):
    for skill in gen.SKILL_SUMMARY_NAME:
        assert banned not in gen.evidence_summary(skill, 19, 12).lower()


def test_the_evidence_never_carries_the_mastery_value():
    c = _stuck(mastery={SUB: 0.4321})
    flat = repr(c.evidence) + c.evidence_summary
    assert "0.4321" not in flat
    assert c.evidence["below_mastery_threshold"] is True
    assert c.evidence["parameter_source_status"] == "TEST_FIXTURE_ONLY"
    # And nothing in it would be stripped on the way out -- it is already clean.
    assert filter_evidence(c.evidence) == c.evidence


def test_review_and_try_again_are_never_generated():
    """D36 as amended by D41: monitor_progress is now generated (the watch-list fallback), but
    review (no prerequisite ordering) and try_again (fails D16 for DD) still never are."""

    assert gen.ACTION_KIND == "practice"
    assert gen.TRIGGER_TYPE == "stagnation"
    assert gen.TARGET_COMPONENT == "B"
    source = open(gen.__file__, encoding="utf-8").read().split('"""', 2)[2]
    for kind in ('"review"', '"try_again"'):
        assert kind not in source


# --- D41: the watch-list fallback ---------------------------------------------------------


def test_a_flagged_learner_with_no_stagnant_skill_gets_monitor_progress():
    c = gen.evaluate_watch_list(session=13, watch_flag=True)
    assert c is not None
    assert c.kind == "monitor_progress"
    assert c.skill is None
    assert c.expires_after_session == 18


def test_the_fallback_has_its_own_trigger_type_so_decisions_are_never_pooled():
    """The one mitigation for the acceptance-rate concern the ML team raised: the decision log
    copies trigger_type, so stagnation and watch_flag acceptance are reported separately."""

    c = gen.evaluate_watch_list(session=13, watch_flag=True)
    assert c.trigger_type == "watch_flag" != gen.TRIGGER_TYPE
    assert c.target_component == "both"


def test_the_fallback_requires_the_watch_flag():
    assert gen.evaluate_watch_list(session=13, watch_flag=False) is None


def test_a_dismissed_unexpired_fallback_is_not_reissued():
    assert gen.evaluate_watch_list(session=13, watch_flag=True, barred=True) is None


def test_the_fallback_summaries_are_short_and_use_no_banned_word():
    for assessed in (0, 1):
        text = gen.watch_list_summary(25, assessed)
        assert len(text) <= 280
        for banned in ("diagnos", "detect", "identif", "screen", "risk", "struggl", "weak", "deficit", "probab", "model"):
            assert banned not in text.lower()


def test_d45_the_summary_never_claims_practice_was_examined_when_none_could_be():
    """ANSWERS_TO_APP_TEAM_5 Q3: 3.4% of cohort watch_flag cases had no skill with >= 4
    opportunities. For those, the sentence must say there was not enough practice."""

    nothing = gen.evaluate_watch_list(session=9, watch_flag=True, opportunities={"counting": 3, "addition": 0})
    assert nothing.evidence["skills_assessed"] == 0
    assert nothing.evidence_summary == (
        "Flagged for review at session 9. There has not been enough recent practice to point to a "
        "particular skill. Suggestion: keep monitoring progress over the next few sessions."
    )

    some = gen.evaluate_watch_list(session=9, watch_flag=True, opportunities={"counting": 4, "addition": 6})
    assert some.evidence["skills_assessed"] == 2
    assert some.evidence_summary == (
        "Flagged for review at session 9. Recent practice does not point to one particular skill "
        "yet. Suggestion: keep monitoring progress over the next few sessions."
    )


def test_skills_assessed_ignores_missing_and_non_numeric_values():
    assert gen.skills_assessed(None) == 0
    assert gen.skills_assessed({"a": None, "b": "7", "c": True, "d": 4}) == 1


def test_the_fallback_evidence_carries_no_mastery_value_and_passes_the_filter():
    c = gen.evaluate_watch_list(session=13, watch_flag=True)
    assert filter_evidence(c.evidence) == c.evidence
    assert "mastery" not in repr(c.evidence)
