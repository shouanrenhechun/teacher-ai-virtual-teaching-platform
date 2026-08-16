from __future__ import annotations

import re
from dataclasses import dataclass

from .state_rules import is_evidence_insufficient


_LINGUISTIC_HEDGING_MARKERS = (
    "吧", "应该", "我觉得", "觉得", "好像", "嗯", "可能是", "似乎",
)
_CONCEPTUAL_UNCERTAINTY_MARKERS = (
    "不确定", "不太清楚", "不太确定", "拿不准", "不知道", "不明白",
    "不会", "会不会", "不懂",
)
_REASON_MARKERS = (
    "因为", "k相同", "k都", "斜率相同", "只改变b", "只会让直线", "所以倾斜",
    "由k决定", "由k控制",
)
_RESIDUAL_PATTERNS = (
    r"b.{0,18}(越大|变大|更大|增加).{0,18}(陡|倾斜|斜率)",
    r"(?:b|截距|[+＋]\d+).{0,20}(?:更陡|越陡|变陡|会陡|更斜|越斜|变斜|有点(?:更)?陡)",
    r"(?:b|[+＋]\d+).{0,20}影响.{0,12}(?:陡|倾斜|斜率)",
    r"截距.{0,18}(越大|变大|更大|增加).{0,18}(陡|倾斜|斜率|更斜)",
    r"(觉得|感觉|认为|不过|但是|还是|仍然|可能|也许).{0,18}(?:b|往上移|[+＋]\d+).{0,20}(?:陡|倾斜|斜率|影响)",
    r"往上移.{0,12}(会|有点|看起来).{0,12}(陡|倾斜)",
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
    ) -> StudentResponseEvidence:
        text = response.strip()
        normalized = _normalize(text)
        teacher_normalized = _normalize(teacher_text)
        has_k = "k" in normalized and any(
            marker in normalized for marker in ("斜率", "倾斜", "陡", "方向")
        )
        has_b = "b" in normalized and any(
            marker in normalized
            for marker in (
                "截距", "位置", "上下", "上移", "向上", "下移", "平移",
                "上面", "下面", "上方", "下方", "移动", "挪",
            )
        )
        residual = _has_residual_misconception(normalized, teacher_normalized)
        linguistic_hedging = any(
            marker in normalized for marker in _LINGUISTIC_HEDGING_MARKERS
        )
        conceptual_uncertainty = _has_conceptual_uncertainty(
            normalized,
            residual=residual,
        )
        # Compatibility field: old callers used this as a knowledge-state gate.
        # Purely linguistic hedging must not block transfer or correction.
        uncertainty = conceptual_uncertainty
        parrots = _is_parroting(text, previous_teacher_text)
        explains_reason = (
            has_k
            and has_b
            and any(marker in normalized for marker in _REASON_MARKERS)
            and not parrots
        )
        states_correct = has_k and (has_b or residual)
        if states_correct and not residual:
            conclusion_level = "correct"
        elif has_k or has_b:
            conclusion_level = "partial"
        else:
            conclusion_level = "wrong"

        slopes = re.findall(r"y=([+-]?\d+)x", teacher_normalized)
        is_transfer_prompt = len(slopes) >= 2 and len(set(slopes[:2])) == 1
        transfer = (
            is_transfer_prompt
            and states_correct
            and explains_reason
            and any(marker in normalized for marker in ("一样", "相同", "同样"))
            and not residual
            and not conceptual_uncertainty
        )
        knowledge_precision = _knowledge_precision(
            has_k=has_k,
            has_b=has_b,
            explains_reason=explains_reason,
            residual=residual,
            conceptual_uncertainty=conceptual_uncertainty,
        )
        if transfer and explains_reason:
            evidence_level = 3
        elif states_correct or explains_reason:
            evidence_level = 2
        elif has_k or has_b or uncertainty:
            evidence_level = 1
        else:
            evidence_level = 0

        return StudentResponseEvidence(
            states_correct_conclusion=states_correct,
            conclusion_level=conclusion_level,
            explains_reason_correctly=explains_reason,
            shows_residual_misconception=residual,
            shows_uncertainty=uncertainty,
            parrots_teacher=parrots,
            transfer_success=transfer,
            evidence_level=evidence_level,
            linguistic_hedging=linguistic_hedging,
            conceptual_uncertainty=conceptual_uncertainty,
            knowledge_precision=knowledge_precision,
        )


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。！？、,:：；;（）()]+", "", text.lower())


def _has_residual_misconception(response: str, teacher_text: str) -> bool:
    rhetorical_positive = re.search(
        r"(?:b|截距).{0,18}不是会.{0,12}(?:更陡|更斜|倾斜|斜率).{0,4}吗",
        response,
    )
    negative_claim = re.search(
        r"(?:b|截距|往上移).{0,8}(?:不|不会|没有|并不).{0,10}(?:影响|更陡|越陡|变陡|更斜|变斜|倾斜|斜率)",
        response,
    )
    if rhetorical_positive:
        negative_claim = None
    historical_correction = re.search(
        r"(?:以前|原来|曾经).{0,20}(?:b|截距).{0,18}(?:越大|变大|更大|增加).{0,18}(?:陡|倾斜|斜率|更斜).{0,20}(?:现在|后来).{0,12}(?:不是|不对|不会|知道)",
        response,
    )
    if historical_correction and not any(
        marker in response for marker in ("不过", "但是", "还是觉得", "仍然觉得")
    ):
        return False
    positive_residual = any(
        re.search(pattern, response, flags=re.IGNORECASE)
        for pattern in _RESIDUAL_PATTERNS
    )
    if negative_claim:
        # A positive phrase before the negation is not current evidence.
        # Only a new residual claim after the explicit negation can override it.
        tail = response[negative_claim.end() :]
        if not any(
            re.search(pattern, tail, flags=re.IGNORECASE)
            for pattern in _RESIDUAL_PATTERNS
        ):
            return False
    if any(
        re.search(pattern, response, flags=re.IGNORECASE)
        for pattern in _RESIDUAL_PATTERNS
    ):
        return True
    if "2和3" in teacher_text or "y=2x+3" in teacher_text:
        return bool(re.search(r"(?:3|它).{0,16}(越陡|更陡|变陡|会陡)", response))
    return False


def _has_conceptual_uncertainty(response: str, *, residual: bool) -> bool:
    if any(marker in response for marker in _CONCEPTUAL_UNCERTAINTY_MARKERS):
        return True
    if residual and any(marker in response for marker in ("可能", "也许", "有点", "担心")):
        return True
    return False


def _knowledge_precision(
    *,
    has_k: bool,
    has_b: bool,
    explains_reason: bool,
    residual: bool,
    conceptual_uncertainty: bool,
) -> str:
    if residual and not (has_k and has_b):
        return "incorrect"
    if explains_reason and not residual and not conceptual_uncertainty:
        return "correct"
    if has_k or has_b or residual:
        return "partial"
    return "incorrect"


def _is_parroting(response: str, teacher_text: str) -> bool:
    if not teacher_text.strip():
        return False
    response_normalized = _normalize(response)
    teacher_normalized = _normalize(teacher_text)
    if response_normalized == teacher_normalized:
        return True
    canonical = ("k决定倾斜程度b只决定与y轴交点", "k控制斜率b控制纵截距")
    return any(
        phrase in response_normalized and phrase in teacher_normalized
        for phrase in canonical
    )


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
