from __future__ import annotations

from enum import StrEnum


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
    if any(phrase in text for phrase in ("b越大越陡", "b越大直线越陡", "b变大更陡")):
        return TeachingBehavior.INCORRECT_EXPLANATION
    if any(phrase in text for phrase in ("答案是", "记住", "直接告诉你", "就是这样")):
        return TeachingBehavior.DIRECT_ANSWER
    if any(phrase in text for phrase in ("例如", "画两条", "对比", "固定k", "举个例子")):
        return TeachingBehavior.EFFECTIVE_EXAMPLE
    if any(phrase in text for phrase in ("为什么", "怎么解释", "如果", "你觉得", "能说明")):
        return TeachingBehavior.EFFECTIVE_QUESTION
    return TeachingBehavior.NEUTRAL
