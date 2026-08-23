from __future__ import annotations

from enum import StrEnum

from .dialogue_intent import analyze_linear_dialogue_intent


class TeachingBehavior(StrEnum):
    EFFECTIVE_EXAMPLE = "effective_example"
    EFFECTIVE_QUESTION = "effective_question"
    DIRECT_ANSWER = "direct_answer"
    INCORRECT_EXPLANATION = "incorrect_explanation"
    TARGETED_CORRECTION = "targeted_correction"
    NEUTRAL = "neutral"


def detect_teacher_behavior(teacher_text: str) -> TeachingBehavior:
    """Use small transparent heuristics until a richer behavior tagger exists."""
    text = teacher_text.lower().replace(" ", "")
    intent = analyze_linear_dialogue_intent(teacher_text)

    if any(
        phrase in text
        for phrase in ("用自己的话", "复述一下", "说说", "分别控制什么", "为什么", "是什么意思", "从哪里来", "解释")
    ):
        return TeachingBehavior.EFFECTIVE_QUESTION

    if intent.correction_statement:
        return TeachingBehavior.TARGETED_CORRECTION

    if any(
        phrase in text
        for phrase in (
            "b不影响斜率",
            "b只影响截距",
            "b改变的是位置",
            "k影响倾斜",
            "固定k改变b",
        )
    ):
        return TeachingBehavior.TARGETED_CORRECTION
    if any(
        phrase in text
        for phrase in (
            "b越大越陡", "b越大直线越陡", "b变大更陡",
            "平方就是分别平方", "没有中间项", "不需要中间项",
        )
    ):
        return TeachingBehavior.INCORRECT_EXPLANATION
    if any(phrase in text for phrase in ("答案是", "记住", "直接告诉你", "就是这样")):
        return TeachingBehavior.DIRECT_ANSWER
    if any(
        phrase in text
        for phrase in (
            "例如", "画两条", "对比", "比较", "固定k", "举个例子",
            "展开", "相乘", "两个相同括号",
        )
    ):
        return TeachingBehavior.EFFECTIVE_EXAMPLE
    if intent.compares_intercept_change:
        return TeachingBehavior.EFFECTIVE_EXAMPLE
    if "?" in text or "？" in text:
        return TeachingBehavior.EFFECTIVE_QUESTION
    if any(phrase in text for phrase in ("怎么解释", "如果", "你觉得", "能说明")):
        return TeachingBehavior.EFFECTIVE_QUESTION
    return TeachingBehavior.NEUTRAL
