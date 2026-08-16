from __future__ import annotations

from dataclasses import dataclass

from .state_rules import is_evidence_insufficient
from .semantic import get_semantic_evaluator


_LINGUISTIC_HEDGING_MARKERS = (
    "吧", "应该", "我觉得", "觉得", "好像", "嗯", "可能是", "似乎",
)
_CONCEPTUAL_UNCERTAINTY_MARKERS = (
    "不确定", "不太清楚", "不太确定", "拿不准", "不知道", "不明白",
    "不会", "会不会", "不懂",
)
@dataclass(frozen=True)
class StudentResponseEvidence:
    states_correct_conclusion: bool
    conclusion_level: str
    explains_reason_correctly: bool
    shows_residual_misconception: bool
    shows_uncertainty: bool
    parrots_teacher: bool
    transfer_success: bool
    evidence_level: int
    linguistic_hedging: bool = False
    conceptual_uncertainty: bool = False
    knowledge_precision: str = "incorrect"

    def to_dict(self) -> dict[str, object]:
        return {
            "states_correct_conclusion": self.states_correct_conclusion,
            "correct_conclusion": self.states_correct_conclusion,
            "conclusion_level": self.conclusion_level,
            "explains_reason_correctly": self.explains_reason_correctly,
            "correct_explanation": self.explains_reason_correctly,
            "shows_residual_misconception": self.shows_residual_misconception,
            "shows_uncertainty": self.shows_uncertainty,
            "linguistic_hedging": self.linguistic_hedging,
            "conceptual_uncertainty": self.conceptual_uncertainty,
            "knowledge_precision": self.knowledge_precision,
            "evidence_insufficient": self.evidence_insufficient,
            "parrots_teacher": self.parrots_teacher,
            "transfer_success": self.transfer_success,
            "evidence_level": self.evidence_level,
        }

    @property
    def evidence_insufficient(self) -> bool:
        return is_evidence_insufficient(self.to_dict_without_derived())

    def to_dict_without_derived(self) -> dict[str, object]:
        return {
            "states_correct_conclusion": self.states_correct_conclusion,
            "explains_reason_correctly": self.explains_reason_correctly,
            "shows_residual_misconception": self.shows_residual_misconception,
            "conceptual_uncertainty": self.conceptual_uncertainty,
            "knowledge_precision": self.knowledge_precision,
            "parrots_teacher": self.parrots_teacher,
        }


class StudentResponseEvidenceAnalyzer:
    """Small deterministic analyzer for evidence in a student's answer."""

    def analyze(
        self,
        response: str,
        *,
        teacher_text: str = "",
        previous_teacher_text: str = "",
        misconception: object | None = None,
    ) -> StudentResponseEvidence:
        text = response.strip()
        evaluator = get_semantic_evaluator(
            getattr(misconception, "semantic_type", None)
        )
        domain_evidence = evaluator.analyze(text, teacher_text)
        linguistic_hedging = any(
            marker in text.lower() for marker in _LINGUISTIC_HEDGING_MARKERS
        )
        conceptual_uncertainty = _has_conceptual_uncertainty(
            text.lower(),
            residual=domain_evidence.shows_residual_misconception,
        )
        # Compatibility field: old callers used this as a knowledge-state gate.
        # Purely linguistic hedging must not block transfer or correction.
        uncertainty = conceptual_uncertainty
        parrots = _is_parroting(text, previous_teacher_text)
        explains_reason = domain_evidence.explains_reason_correctly and not parrots
        states_correct = domain_evidence.states_correct_conclusion
        transfer = (
            domain_evidence.transfer_success
            and explains_reason
            and not conceptual_uncertainty
            and not parrots
        )
        knowledge_precision = domain_evidence.knowledge_precision
        if explains_reason and not domain_evidence.shows_residual_misconception and not conceptual_uncertainty:
            knowledge_precision = "correct"
        if transfer and explains_reason:
            evidence_level = 3
        elif states_correct or explains_reason:
            evidence_level = 2
        elif domain_evidence.shows_residual_misconception or uncertainty:
            evidence_level = 1
        else:
            evidence_level = 0

        return StudentResponseEvidence(
            states_correct_conclusion=states_correct,
            conclusion_level=domain_evidence.conclusion_level,
            explains_reason_correctly=explains_reason,
            shows_residual_misconception=domain_evidence.shows_residual_misconception,
            shows_uncertainty=uncertainty,
            parrots_teacher=parrots,
            transfer_success=transfer,
            evidence_level=evidence_level,
            linguistic_hedging=linguistic_hedging,
            conceptual_uncertainty=conceptual_uncertainty,
            knowledge_precision=knowledge_precision,
        )


def _has_conceptual_uncertainty(response: str, *, residual: bool) -> bool:
    if any(marker in response for marker in _CONCEPTUAL_UNCERTAINTY_MARKERS):
        return True
    if residual and any(marker in response for marker in ("可能", "也许", "有点", "担心")):
        return True
    return False


def _is_parroting(response: str, teacher_text: str) -> bool:
    if not teacher_text.strip():
        return False
    response_normalized = "".join(response.lower().split())
    teacher_normalized = "".join(teacher_text.lower().split())
    if response_normalized == teacher_normalized:
        return True
    return len(response_normalized) >= 8 and response_normalized in teacher_normalized


def correction_opportunity(behavior: str, teacher_text: str) -> dict[str, object]:
    """Describe a learning opportunity without changing student knowledge."""
    if behavior == "targeted_correction":
        strength = 0.9
    elif behavior == "effective_example":
        strength = 0.75
    elif behavior == "effective_question":
        strength = 0.7
    elif behavior == "direct_answer":
        strength = 0.2
    else:
        strength = 0.0
    return {
        "correction_opportunity": strength > 0,
        "opportunity_strength": strength,
        "teacher_text": teacher_text.strip(),
    }
