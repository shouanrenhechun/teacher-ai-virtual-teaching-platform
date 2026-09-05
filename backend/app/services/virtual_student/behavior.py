from __future__ import annotations

from enum import StrEnum

from .classroom_intent import ClassroomAct, analyze_classroom_dialogue
from .dialogue_intent import analyze_linear_dialogue_intent
from .propositions import assess_claims


class TeachingBehavior(StrEnum):
    EFFECTIVE_EXAMPLE = "effective_example"
    EFFECTIVE_QUESTION = "effective_question"
    DIRECT_ANSWER = "direct_answer"
    INCORRECT_EXPLANATION = "incorrect_explanation"
    TARGETED_CORRECTION = "targeted_correction"
    PRAISE = "praise"
    NEUTRAL = "neutral"


def detect_teacher_behavior(teacher_text: str) -> TeachingBehavior:
    """Use small transparent heuristics until a richer behavior tagger exists."""
    text = teacher_text.lower().replace(" ", "")
    classroom = analyze_classroom_dialogue(teacher_text)
    intent = analyze_linear_dialogue_intent(
        teacher_text, classroom_intent=classroom
    )

    claim = assess_claims(teacher_text)
    if claim.error_stance == 'questioned':
        return TeachingBehavior.EFFECTIVE_QUESTION
    if claim.correct is False:
        return TeachingBehavior.INCORRECT_EXPLANATION
    if claim.error_stance == 'denied':
        return TeachingBehavior.TARGETED_CORRECTION

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
    if classroom.has(ClassroomAct.DIRECT_ANSWER):
        return TeachingBehavior.DIRECT_ANSWER
    if classroom.has(ClassroomAct.QUESTION) or classroom.has(ClassroomAct.GUIDED_QUESTION):
        return TeachingBehavior.EFFECTIVE_QUESTION
    if classroom.has(ClassroomAct.EXAMPLE) or intent.compares_intercept_change:
        return TeachingBehavior.EFFECTIVE_EXAMPLE
    if any(classroom.has(act) for act in {
        ClassroomAct.ELABORATION_REQUEST,
        ClassroomAct.UNDERSTANDING_CHECK,
        ClassroomAct.CONTEXTUAL_REFERENCE,
    }):
        return TeachingBehavior.EFFECTIVE_QUESTION
    if classroom.has(ClassroomAct.FEEDBACK) and not classroom.has(
        ClassroomAct.CORRECTIVE_FEEDBACK
    ):
        return TeachingBehavior.PRAISE
    if classroom.off_topic or (
        classroom.primary_act is not ClassroomAct.SUBJECT_CONTENT
        and not classroom.has_subject_content
    ):
        return TeachingBehavior.NEUTRAL
    if any(
        phrase in text
        for phrase in ("用自己的话", "复述一下", "说说", "分别控制什么", "为什么", "是什么意思", "从哪里来", "解释")
    ):
        return TeachingBehavior.EFFECTIVE_QUESTION
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
