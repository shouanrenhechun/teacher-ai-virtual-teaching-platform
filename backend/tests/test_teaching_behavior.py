import logging

from app.services.llm.base import LLMClient, LLMContext
from app.services.teaching_behavior import TeachingBehaviorAnalyzer
from app.schemas.teaching_behavior import TeachingActionType


class InvalidAnalysisClient(LLMClient):
    provider = "invalid-test"

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        return "我还需要一点提示。"

    def analyze_behavior(
        self, teacher_text: str, context: LLMContext | None = None
    ) -> dict[str, object]:
        return {
            "action_type": "not-a-supported-action",
            "concept": "slope",
            "knowledge_accuracy": 4,
            "clarity": 0.8,
            "checked_understanding": False,
            "gave_answer_directly": False,
        }


def test_rule_analyzer_covers_typical_teacher_inputs() -> None:
    analyzer = TeachingBehaviorAnalyzer()
    cases = (
        ("一次函数中，k 表示斜率，b 表示截距。", TeachingActionType.EXPLANATION),
        ("如果固定 k，只改变 b，图像会怎样？", TeachingActionType.GUIDED_QUESTION),
        ("例如固定 k=2，比较 b=1 和 b=3。", TeachingActionType.EXAMPLE),
        ("你能说说 b 改变时直线哪里变吗？", TeachingActionType.QUESTION),
        ("很好，你已经发现方向不同了。", TeachingActionType.FEEDBACK),
        ("不对，b 不影响斜率，只改变截距。", TeachingActionType.CORRECTION),
        ("听懂了吗？能复述一下吗？", TeachingActionType.UNDERSTANDING_CHECK),
        ("答案是 b 只影响截距，记住。", TeachingActionType.DIRECT_ANSWER),
    )

    for teacher_text, expected_action in cases:
        result = analyzer.analyze(teacher_text)
        assert result.action_type is expected_action
        assert 0 <= result.knowledge_accuracy <= 1
        assert 0 <= result.clarity <= 1

    assert analyzer.analyze(cases[1][0]).concept == "slope_and_intercept"
    assert analyzer.analyze(cases[5][0]).knowledge_accuracy >= 0.9
    assert analyzer.analyze(cases[6][0]).checked_understanding is True
    assert analyzer.analyze(cases[7][0]).gave_answer_directly is True


def test_invalid_llm_structure_uses_safe_default_and_logs(caplog) -> None:
    caplog.set_level(logging.WARNING)
    result = TeachingBehaviorAnalyzer().analyze(
        "如果固定 k，只改变 b，图像会怎样？",
        llm_client=InvalidAnalysisClient(),
    )

    assert result.action_type is TeachingActionType.GUIDED_QUESTION
    assert result.analysis_source == "fallback"
    assert result.analysis_error
    assert "结构化分析失败" in caplog.text
