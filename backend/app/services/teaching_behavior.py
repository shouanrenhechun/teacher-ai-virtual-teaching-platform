from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from .llm import LLMClient, LLMContext
from .llm.base import LLMError
from .virtual_student.classroom_intent import ClassroomAct, analyze_classroom_dialogue
from .virtual_student.dialogue_intent import analyze_linear_dialogue_intent
from .virtual_student.propositions import assess_claims
from ..schemas.teaching_behavior import TeachingActionType, TeachingBehaviorAnalysis


logger = logging.getLogger(__name__)


class TeachingBehaviorAnalyzer:
    """Rule-first analysis with optional validated LLM enrichment.

    This is deliberately a small, explainable classifier for the MVP. The LLM
    may refine the structured fields, but malformed or unavailable output never
    interrupts a teaching session.
    """

    def analyze(
        self,
        teacher_text: str,
        *,
        llm_client: LLMClient | None = None,
        context: LLMContext | None = None,
    ) -> TeachingBehaviorAnalysis:
        rule_result = self._analyze_by_rules(teacher_text, context=context)
        if llm_client is None:
            return rule_result

        try:
            raw_result = llm_client.analyze_behavior(teacher_text, context)
            llm_result = TeachingBehaviorAnalysis.model_validate(raw_result)
        except (LLMError, ValidationError, TypeError, ValueError) as exc:
            logger.warning("教学行为结构化分析失败，使用安全默认值: %s", exc)
            return rule_result.model_copy(
                update={
                    "analysis_source": "fallback",
                    "analysis_error": str(exc)[:500],
                }
            )
        except Exception as exc:  # Defensive boundary for third-party providers.
            logger.exception("教学行为分析出现未预期错误，使用安全默认值")
            return rule_result.model_copy(
                update={
                    "analysis_source": "fallback",
                    "analysis_error": str(exc)[:500],
                }
            )

        # Strong local signals win for action labels and boolean safety flags;
        # the validated model may refine the numeric assessment and concept.
        action_type = rule_result.action_type
        concept = rule_result.concept if rule_result.concept != "一次函数" else llm_result.concept
        # A valid JSON score is not verification of a mathematical claim.
        knowledge_accuracy = rule_result.knowledge_accuracy
        return rule_result.model_copy(
            update={
                "action_type": action_type,
                "concept": concept,
                "knowledge_accuracy": knowledge_accuracy,
                "clarity": llm_result.clarity,
                "checked_understanding": rule_result.checked_understanding
                or llm_result.checked_understanding,
                "gave_answer_directly": rule_result.gave_answer_directly,
                "analysis_source": "rules+llm",
                "analysis_error": None,
            }
        )

    def _analyze_by_rules(
        self,
        teacher_text: str,
        *,
        context: LLMContext | None = None,
    ) -> TeachingBehaviorAnalysis:
        text = teacher_text.strip()
        normalized = re.sub(r"\s+", "", text.lower())
        if not normalized:
            return self._safe_default("教师输入为空")
        classroom_intent = analyze_classroom_dialogue(
            text,
            conversation_history=context.conversation_history if context else (),
        )
        linear_intent = analyze_linear_dialogue_intent(
            text, classroom_intent=classroom_intent
        )

        is_question = "?" in text or "？" in text or any(
            marker in normalized for marker in ("吗", "什么", "为什么", "如何", "怎么", "哪个", "能否")
        )
        checked_understanding = classroom_intent.has(ClassroomAct.UNDERSTANDING_CHECK) or any(
            marker in normalized
            for marker in ("听懂了吗", "明白了吗", "理解了吗", "能复述", "说说你的理解", "检查一下理解")
        )
        gave_answer_directly = classroom_intent.has(ClassroomAct.DIRECT_ANSWER)

        is_specific_correction = linear_intent.correction_statement or self._contains_any(
            normalized,
            (
                "不对", "不是", "纠正", "更正", "并不", "不能说",
                "b不影响斜率", "b只影响截距", "b改变的是位置", "k影响倾斜",
                "固定k改变b",
            ),
        )

        if classroom_intent.off_topic:
            action_type = TeachingActionType.OFF_TOPIC
        elif gave_answer_directly:
            action_type = TeachingActionType.DIRECT_ANSWER
        elif classroom_intent.has(ClassroomAct.GUIDED_QUESTION):
            action_type = TeachingActionType.GUIDED_QUESTION
        elif classroom_intent.has(ClassroomAct.QUESTION):
            action_type = TeachingActionType.QUESTION
        elif (is_specific_correction or assess_claims(text).error_stance == 'denied') and '不是不对' not in normalized:
            action_type = TeachingActionType.CORRECTION
        elif classroom_intent.has(ClassroomAct.UNDERSTANDING_CHECK) or checked_understanding:
            action_type = TeachingActionType.UNDERSTANDING_CHECK
        elif classroom_intent.has(ClassroomAct.ELABORATION_REQUEST) or classroom_intent.has(
            ClassroomAct.CONTEXTUAL_REFERENCE
        ):
            action_type = TeachingActionType.QUESTION
        elif classroom_intent.has(ClassroomAct.EXAMPLE) or self._contains_any(
            normalized, ("例如", "举个例子", "比如", "画两条", "对比一下", "比较")
        ):
            action_type = TeachingActionType.EXAMPLE
        elif any(
            classroom_intent.has(act)
            for act in (
                ClassroomAct.FEEDBACK,
                ClassroomAct.ENCOURAGEMENT,
                ClassroomAct.CORRECTIVE_FEEDBACK,
            )
        ):
            action_type = TeachingActionType.FEEDBACK
        elif classroom_intent.off_topic:
            action_type = TeachingActionType.OFF_TOPIC
        elif classroom_intent.primary_act is not ClassroomAct.SUBJECT_CONTENT:
            action_type = TeachingActionType.CLASSROOM_INTERACTION
        elif is_question and self._contains_any(
            normalized,
            ("如果", "假设", "先固定", "观察", "比较", "你觉得", "想一想", "试着"),
        ):
            action_type = TeachingActionType.GUIDED_QUESTION
        elif is_question:
            action_type = TeachingActionType.QUESTION
        elif self._contains_any(normalized, ("因为", "表示", "指的是", "也就是说", "定义", "当", "改变")):
            action_type = TeachingActionType.EXPLANATION
        else:
            action_type = TeachingActionType.EXPLANATION

        if classroom_intent.off_topic:
            concept = "非教学话题"
        elif not classroom_intent.has_subject_content:
            concept = "课堂互动"
        else:
            concept = self._detect_concept(normalized)
        knowledge_accuracy = (
            0.0
            if concept in {"课堂互动", "非教学话题"}
            else self._estimate_accuracy(normalized, action_type)
        )
        clarity = self._estimate_clarity(text)
        claim = assess_claims(text)
        if action_type is TeachingActionType.CLASSROOM_INTERACTION:
            knowledge_accuracy = 0.0
        elif claim.correct is not None:
            knowledge_accuracy = 0.95 if claim.correct else 0.1
        elif claim.error_stance == 'questioned':
            concept = "未判定知识"
            knowledge_accuracy = 0.0
        elif action_type in {TeachingActionType.EXPLANATION, TeachingActionType.DIRECT_ANSWER} and concept not in {"课堂互动", "非教学话题"}:
            concept = "未判定知识"
            knowledge_accuracy = 0.0
        return TeachingBehaviorAnalysis(
            action_type=action_type,
            concept=concept,
            knowledge_accuracy=knowledge_accuracy,
            clarity=clarity,
            checked_understanding=checked_understanding,
            gave_answer_directly=gave_answer_directly,
        )

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)

    @staticmethod
    def _detect_concept(normalized: str) -> str:
        mentions_k = "k" in normalized or "斜率" in normalized or "倾斜" in normalized
        mentions_b = "b" in normalized or "截距" in normalized or "上下移动" in normalized
        if mentions_k and mentions_b:
            return "slope_and_intercept"
        if mentions_k:
            return "slope"
        if mentions_b:
            return "intercept"
        return "一次函数"

    @staticmethod
    def _estimate_accuracy(normalized: str, action_type: TeachingActionType) -> float:
        if any(phrase in normalized for phrase in ("b越大越陡", "b变大更陡", "b越大直线越陡")):
            return 0.2
        if action_type is TeachingActionType.CORRECTION and any(
            phrase in normalized for phrase in ("b不影响斜率", "b只影响截距", "k影响倾斜")
        ):
            return 0.95
        if action_type in {TeachingActionType.QUESTION, TeachingActionType.GUIDED_QUESTION}:
            return 0.8
        return 0.88

    @staticmethod
    def _estimate_clarity(text: str) -> float:
        length_score = 0.9 if 8 <= len(text) <= 100 else 0.72
        structure_score = 0.06 if any(mark in text for mark in ("，", "。", "？", "?")) else 0
        return min(1.0, round(length_score + structure_score, 2))

    @staticmethod
    def _safe_default(error_message: str | None = None) -> TeachingBehaviorAnalysis:
        return TeachingBehaviorAnalysis(
            action_type=TeachingActionType.EXPLANATION,
            concept="一次函数",
            knowledge_accuracy=0.5,
            clarity=0.5,
            checked_understanding=False,
            gave_answer_directly=False,
            analysis_source="fallback" if error_message else "rules",
            analysis_error=error_message,
        )
