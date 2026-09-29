"""Regression tests for issue #4: negated linear claims must not read as errors.

Each case pairs an affirmative statement with its negation, attribution,
question or hedge form, so a rule that simply stops detecting the error is
caught by the affirmative half of the pair.
"""
from __future__ import annotations

import pytest

from app.services.evidence_scoring import teacher_claims
from app.services.virtual_student.evidence import StudentResponseEvidenceAnalyzer
from app.services.virtual_student.propositions import assess_claims
from app.services.virtual_student.semantic import get_semantic_evaluator

# The exact sentence from the issue report.
ISSUE_SENTENCE = (
    "在 y=2x+3 中，b 变大后直线并没有更陡；k 保持不变所以斜率不变，b 只改变上下位置。"
)


def _linear(text: str, teacher_text: str = "y=2x+3"):
    return get_semantic_evaluator("linear_kb").analyze(text, teacher_text)


# --- claim stance -----------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # affirmative error: must still be caught
        ("b 越大，直线就越陡。", False),
        ("b 决定直线的斜率。", False),
        ("b 越大直线越陡。", False),
        # negated error: the teacher is correcting, not asserting
        ("b 变大后直线并没有更陡。", True),
        ("b 变大不会让直线更陡。", True),
        ("b 变大并没有使直线更陡。", True),
        ("b 不影响斜率。", True),
        # correct positive restatement
        ("b 只改变上下位置，k 决定倾斜程度。", True),
        # attribution and questions are not assertions
        ("有同学说 b 越大直线越陡，你们觉得对不对？", None),
        ("如果 b 变大，直线会更陡吗？", None),
    ],
)
def test_assess_claims_negation_aware(text: str, expected: bool | None) -> None:
    assert assess_claims(text).correct is expected


def test_issue_sentence_is_not_scored_as_a_false_teacher_claim() -> None:
    """The issue's sentence must not depress knowledge accuracy."""
    assert teacher_claims(ISSUE_SENTENCE) == [True, True]


def test_issue_sentence_stance_is_denied_not_asserted() -> None:
    assert assess_claims(ISSUE_SENTENCE).error_stance == "denied"


# --- residual misconception -------------------------------------------------

@pytest.mark.parametrize(
    ("text", "residual"),
    [
        # affirmative error still detected
        ("b 越大，直线就越陡。", True),
        ("b 决定直线的斜率。", True),
        ("我觉得 b 变大可能会更陡吧。", True),
        # negation is not residual misconception evidence
        ("b 变大后直线并没有更陡。", False),
        ("b 变大不会让直线更陡。", False),
        ("b 变大并没有使直线更陡。", False),
        (ISSUE_SENTENCE, False),
        # attribution / hypothesis is raised, not held
        ("有同学说 b 越大直线越陡，你们觉得对不对？", False),
        ("如果 b 变大，直线会更陡吗？", False),
    ],
)
def test_linear_residual_requires_an_asserted_error(text: str, residual: bool) -> None:
    assert _linear(text).shows_residual_misconception is residual


@pytest.mark.parametrize(
    "text",
    [
        ISSUE_SENTENCE,
        "b 只改变上下位置，k 决定倾斜程度。",
    ],
)
def test_correct_negated_expression_is_explained_not_residual(text: str) -> None:
    """Criterion 3: a complete correct expression must not be marked residual.

    Restricted to expressions that state both roles. A bare denial such as
    "b 变大并没有使直线更陡" correctly drops the residual flag but does not
    count as explaining the relation, so it is covered separately below.
    """
    evidence = _linear(text)
    assert evidence.shows_residual_misconception is False
    assert evidence.explains_reason_correctly is True


def test_bare_denial_drops_residual_without_claiming_explanation() -> None:
    """A denial is not misconception evidence, but is not an explanation either."""
    evidence = _linear("b 变大并没有使直线更陡。")
    assert evidence.shows_residual_misconception is False
    assert evidence.states_correct_conclusion is True


def test_intercept_number_near_steepness_is_not_evidence_on_its_own() -> None:
    """Criterion 2: the literal 3 in y=2x+3 is not misconception evidence."""
    denied = _linear("b 变大后直线并没有更陡。", "y=2x+3")
    asserted = _linear("b 变大后直线更陡。", "y=2x+3")
    assert denied.shows_residual_misconception is False
    assert asserted.shows_residual_misconception is True


# --- end-to-end student evidence -------------------------------------------

def test_student_evidence_is_correct_for_the_issue_sentence() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        ISSUE_SENTENCE, teacher_text="y=2x+3", previous_teacher_text="y=2x+3"
    )
    assert evidence.shows_residual_misconception is False
    assert evidence.explains_reason_correctly is True
    assert evidence.knowledge_precision == "correct"


def test_student_evidence_still_flags_a_real_error() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "b 越大，直线就越陡。", teacher_text="y=2x+3"
    )
    assert evidence.shows_residual_misconception is True
    assert evidence.explains_reason_correctly is False


def test_contrastive_clause_keeps_its_own_negation_scope() -> None:
    """Negation in a later clause must not erase an asserted error."""
    text = "b 变大不会让直线更陡，但我还是觉得 b 越大就越陡。"
    assert _linear(text).shows_residual_misconception is True


# --- validation framework self-description ---------------------------------

def test_validation_package_documents_that_it_is_not_independent() -> None:
    """Criterion 4: the framework must not call itself an independent oracle."""
    import validation

    docstring = validation.__doc__ or ""
    assert "not" in docstring and "independent" in docstring
    assert "regression" in docstring.lower()


def test_validation_metrics_reuse_production_rules() -> None:
    """The documented coupling is real, so the docstring cannot silently lie."""
    import validation.metrics as metrics

    assert metrics.get_semantic_evaluator is not None
    assert metrics.is_strong_correct_evidence is not None
