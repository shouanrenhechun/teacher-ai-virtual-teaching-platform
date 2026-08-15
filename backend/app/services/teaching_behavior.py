from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from .llm import LLMClient, LLMContext
from .llm.base import LLMError
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
        rule_result = self._analyze_by_rules(teacher_text)
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
        action_type = (
            llm_result.action_type
            if rule_result.action_type is TeachingActionType.EXPLANATION
            else rule_result.action_type
        )
        concept = rule_result.concept if rule_result.concept != "一次函数" else llm_result.concept
        return rule_result.model_copy(
            update={
                "action_type": action_type,
                "concept": concept,
                "knowledge_accuracy": llm_result.knowledge_accuracy,
                "clarity": llm_result.clarity,
                "checked_understanding": rule_result.checked_understanding
                or llm_result.checked_understanding,
                "gave_answer_directly": rule_result.gave_answer_directly
                or llm_result.gave_answer_directly,
                "analysis_source": "rules+llm",
                "analysis_error": None,
            }
        )

    def _analyze_by_rules(self, teacher_text: str) -> TeachingBehaviorAnalysis:
        text = teacher_text.strip()
        normalized = re.sub(r"\s+", "", text.lower())
        if not normalized:
            return self._safe_default("教师输入为空")

        is_question = "?" in text or "？" in text or any(
            marker in normalized for marker in ("吗", "什么", "为什么", "如何", "怎么", "哪个", "能否")
        )
        checked_understanding = any(
            marker in normalized
            for marker in ("听懂了吗", "明白了吗", "理解了吗", "能复述", "说说你的理解", "检查一下理解")
        )
        gave_answer_directly = any(
            marker in normalized
            for marker in ("答案是", "结论是", "记住", "直接告诉你", "就是这样", "应该是")
        )

        if gave_answer_directly:
            action_type = TeachingActionType.DIRECT_ANSWER
        elif checked_understanding:
            action_type = TeachingActionType.UNDERSTANDING_CHECK
        elif self._contains_any(normalized, ("不对", "不是", "纠正", "更正", "并不", "不能说")):
            action_type = TeachingActionType.CORRECTION
        elif self._contains_any(normalized, ("例如", "举个例子", "比如", "画两条", "对比一下")):
            action_type = TeachingActionType.EXAMPLE
        elif is_question and self._contains_any(
            normalized,
            ("如果", "假设", "先固定", "观察", "比较", "你觉得", "想一想", "试着"),
        ):
            action_type = TeachingActionType.GUIDED_QUESTION
        elif is_question:
            action_type = TeachingActionType.QUESTION
        elif self._contains_any(normalized, ("很好", "不错", "回答得", "说得对", "再想想", "有进步")):
            action_type = TeachingActionType.FEEDBACK
        elif self._contains_any(normalized, ("因为", "表示", "指的是", "也就是说", "定义", "当", "改变")):
            action_type = TeachingActionType.EXPLANATION
        else:
            action_type = TeachingActionType.EXPLANATION

        concept = self._detect_concept(normalized)
        knowledge_accuracy = self._estimate_accuracy(normalized, action_type)
        clarity = self._estimate_clarity(text)
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
