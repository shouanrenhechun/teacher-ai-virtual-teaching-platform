from __future__ import annotations

from enum import StrEnum
from typing import Mapping

from .base import LLMContext


class PraiseEvidenceState(StrEnum):
    STABLE = "stable"
    PROVISIONAL = "provisional"
    UNCERTAIN = "uncertain"


class PraiseResponsePolicy:
    """Select a deterministic social reply without creating learning evidence."""

    @classmethod
    def respond(
        cls,
        context: LLMContext,
        *,
        previous_response: str | None = None,
    ) -> str:
        state = cls.evidence_state(context)
        confirmation_seeking = cls._strong_confirmation_seeking(context)
        candidates = cls._candidates(state, confirmation_seeking)
        return next(
            (candidate for candidate in candidates if candidate != previous_response),
            candidates[0],
        )

    @staticmethod
    def evidence_state(context: LLMContext) -> PraiseEvidenceState:
        evidence: Mapping[str, object] = context.previous_student_evidence or {}
        residual = bool(evidence.get("shows_residual_misconception", False))
        conceptual_uncertainty = bool(
            evidence.get("conceptual_uncertainty", evidence.get("shows_uncertainty", False))
        )
        correct = bool(
            evidence.get("states_correct_conclusion", evidence.get("correct_conclusion", False))
        )
        explained = bool(
            evidence.get("explains_reason_correctly", evidence.get("correct_explanation", False))
        )
        insufficient = bool(evidence.get("evidence_insufficient", not evidence))

        clean = not residual and not conceptual_uncertainty
        stable_evidence = (
            context.misconception_stable_correct_evidence_count >= 2
            and context.misconception_transfer_evidence >= 1
        )
        if clean and (not evidence or not insufficient) and (
            context.misconception_status == "corrected" or stable_evidence
        ):
            return PraiseEvidenceState.STABLE
        if clean and correct and explained and not insufficient:
            return PraiseEvidenceState.PROVISIONAL
        return PraiseEvidenceState.UNCERTAIN

    @staticmethod
    def _strong_confirmation_seeking(context: LLMContext) -> bool:
        profile_text = " ".join(
            (
                context.confidence_style,
                context.response_style,
                context.confirmation_seeking,
                context.correction_style,
            )
        )
        return context.student_confidence < 0.45 or any(
            marker in profile_text
            for marker in ("喜欢先确认", "主动请求确认", "请求教师再举例", "倾向先确认")
        )

    @staticmethod
    def _candidates(
        state: PraiseEvidenceState,
        confirmation_seeking: bool,
    ) -> tuple[str, ...]:
        if state is PraiseEvidenceState.STABLE:
            if confirmation_seeking:
                return ("嗯，谢谢老师。", "好的，我明白了。", "谢谢老师。")
            return ("谢谢老师。", "好的，我明白了。", "嗯，明白了。")
        if state is PraiseEvidenceState.PROVISIONAL:
            if confirmation_seeking:
                return (
                    "谢谢老师，我想再做一道题确认一下。",
                    "嗯，谢谢老师，我感觉思路清楚一些了。",
                    "谢谢老师，我大概明白了。",
                )
            return (
                "谢谢老师，我感觉思路清楚一些了。",
                "谢谢老师，我大概明白了。",
                "嗯，我想再确认一下。",
            )
        if confirmation_seeking:
            return (
                "谢谢老师，我还想确认一下这里。",
                "嗯，我再想想为什么。",
                "谢谢老师，我再检查一下自己的理由。",
            )
        return (
            "谢谢老师，我再检查一下自己的理由。",
            "嗯，我再想想为什么。",
            "谢谢老师，我还想确认一下这里。",
        )
