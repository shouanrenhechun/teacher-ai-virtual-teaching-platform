"""Mathematical expectations independent of the production matchers."""
import pytest

from app.services.virtual_student.semantic import get_semantic_evaluator
from app.services.evidence_scoring import teacher_claims
from app.services.virtual_student.evidence import StudentResponseEvidenceAnalyzer
from app.services.virtual_student.state_rules import is_strong_correct_evidence


@pytest.mark.parametrize(
    "text",
    [
        "在 y=2x+3 中，k 增大才会更陡，b 只改变上下位置。",
        "y=2x+3 和 y=3x+1 相比，后者更陡，因为后者的斜率更大。",
        "y=-2x+3 和 y=-3x+1 相比，后者更陡，因为后者斜率的绝对值更大。",
        "在 y=2x+3 中，b 变大并没有更陡，k 保持不变，b 只改变上下位置。",
    ],
)
def test_formula_literals_are_not_intercept_misconception_subjects(text):
    evidence = get_semantic_evaluator("linear_kb").analyze(text, "y=2x+3")
    assert evidence.shows_residual_misconception is False


@pytest.mark.parametrize(
    ("text", "context"),
    [
        ("在 y=2x+3 中，b 越大就越陡。", "y=2x+3"),
        ("这里的 3 越大，直线就越陡。", "y=2x+3"),
        ("3 的话，我总觉得它越大直线越陡。", "y=2x+3"),
        ("我还是觉得 +7 那条看起来更陡。", "y=4x-2 和 y=4x+7"),
    ],
)
def test_explicit_intercept_errors_are_still_detected(text, context):
    assert get_semantic_evaluator("linear_kb").analyze(text, context).shows_residual_misconception


@pytest.mark.parametrize(
    ("text", "context", "status"),
    [
        ("k 从 2 变成 3，直线更陡。", "", "correct"),
        ("k 从 -2 变成 -1，直线更陡。", "", "incorrect"),
        ("k 从 -2 变成 -1，直线更平缓。", "", "correct"),
        ("k 从 -2 变成 3，直线更陡。", "", "correct"),
        ("k 从 -2 变成 2，两条一样陡。", "", "correct"),
        ("k 从 -3/2 变成 -0.5，直线更陡。", "", "incorrect"),
        ("|k| 越大直线越陡。", "", "correct"),
        ("k 的绝对值越大直线越陡。", "", "correct"),
        ("k 越大直线越陡。", "", "insufficient_conditions"),
        ("k 增大才会更陡，b 只改变上下位置。", "y=2x+3", "correct"),
        ("k 增大才会更陡，b 只改变上下位置。", "y=-2x+3", "insufficient_conditions"),
        ("当 k<0 时，k 越大直线越陡。", "", "incorrect"),
        ("当 k>0 时，k 越大直线越陡。", "", "correct"),
        ("y=2x+3 和 y=3x+1 相比，后者更陡，因为 |k| 更大。", "", "correct"),
        ("y=-2x+3 和 y=-3x+1 相比，前者更陡。", "", "incorrect"),
        ("k 从 2 变成 3，直线更陡，k 从 -2 变成 -1，直线也更陡。", "", "incorrect"),
        ("|k| 越大直线越陡，k 越大直线越陡。", "", "insufficient_conditions"),
        ("k 从 2 变成 3，直线更陡，|k| 越大直线越平缓。", "", "incorrect"),
        ("k 从 -2 变成 -1，直线并没有更陡。", "", "correct"),
        ("k 增大可能更陡，b 只改变上下位置。", "y=2x+3", "insufficient_conditions"),
        ("k 减小直线更陡。", "y=-2x+3", "correct"),
        ("k 减小直线更平缓。", "y=2x+3", "insufficient_conditions"),
        ("当 k<0 时，|k| 越大直线越陡。", "", "correct"),
        ("有同学说 k 从 -2 变成 -1直线更陡。", "", "not_applicable"),
        ("k 从 -2 变成 -1，直线更陡吗？", "", "not_applicable"),
    ],
)
def test_steepness_claims_follow_absolute_slope(text, context, status):
    evidence = get_semantic_evaluator("linear_kb").analyze(text, context)
    assert evidence.slope_claim_status == status
    # A mistake about k is not evidence of the specific b-controls-slope error.
    assert evidence.shows_residual_misconception is False
    if status in {"incorrect", "insufficient_conditions"}:
        assert evidence.explains_reason_correctly is False
        assert evidence.knowledge_precision != "correct"


def test_wrong_k_change_is_scored_as_a_teacher_error():
    assert teacher_claims("k 从 -2 变成 -1，直线更陡。") == [False]
    assert teacher_claims("k 从 -2 变成 -1，直线更平缓。") == [True]
    assert teacher_claims("k 越大直线越陡。") == []
    assert teacher_claims("k 从 -2 变成 -1，直线更陡吗？") == []
    assert teacher_claims("有同学说 k 从 -2 变成 -1，直线更陡。") == []


def test_missing_sign_conditions_do_not_prove_mastery():
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "k 增大才会更陡，b 只改变上下位置。", teacher_text="y=-2x+3"
    )
    assert evidence.conceptual_uncertainty is True
    assert evidence.explanation_evidence_reason == "missing_slope_conditions"
    assert not is_strong_correct_evidence(evidence.to_dict())


def test_correct_repetition_preserves_content_but_not_independent_evidence():
    text = "k 决定斜率，b 只改变上下位置。"
    evidence = StudentResponseEvidenceAnalyzer().analyze(text, teacher_text=text)
    assert evidence.explanation_content_correct is True
    assert evidence.parrots_teacher is True
    assert evidence.explains_reason_correctly is False
    assert evidence.explanation_evidence_reason == "parroting_teacher"
    assert not is_strong_correct_evidence(evidence.to_dict())


def test_correct_contextual_k_explanation_is_independent_evidence():
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "k 增大才会更陡，b 只改变上下位置。", teacher_text="在 y=2x+3 中，k 和 b 有什么作用？"
    )
    assert evidence.explanation_content_correct is True
    assert evidence.explains_reason_correctly is True
    assert evidence.explanation_evidence_reason == "independent_explanation"
    assert is_strong_correct_evidence(evidence.to_dict())


def test_evidence_api_fields_preserve_new_and_legacy_traces():
    from app.schemas.cognitive import StudentResponseEvidenceRead

    text = "k 决定斜率，b 只改变上下位置。"
    evidence = StudentResponseEvidenceAnalyzer().analyze(text, teacher_text=text).to_dict()
    serialized = StudentResponseEvidenceRead.model_validate(evidence).model_dump()
    assert serialized["explanation_content_correct"] is True
    assert serialized["explanation_evidence_reason"] == "parroting_teacher"
    for field in ("explanation_content_correct", "explanation_evidence_reason", "slope_claim_status"):
        evidence.pop(field)
    legacy = StudentResponseEvidenceRead.model_validate(evidence)
    assert legacy.explanation_content_correct is None
    assert legacy.slope_claim_status == "not_applicable"
