from __future__ import annotations

import re
from dataclasses import dataclass


_UNCERTAINTY_MARKERS = (
    "不确定", "不太清楚", "不太确定", "好像", "拿不准", "应该", "吧",
    "有点", "会不会", "但我还", "不过", "但是",
)
_REASON_MARKERS = (
    "因为", "k相同", "斜率相同", "只改变b", "只会让直线", "所以倾斜",
)
_RESIDUAL_PATTERNS = (
    r"b.{0,18}(越大|变大|更大|增加).{0,18}(陡|倾斜|斜率)",
    r"(觉得|感觉|认为|不过|但是|还是|仍然).{0,18}(b|往上移).{0,18}(陡|倾斜)",
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

    def to_dict(self) -> dict[str, object]:
        return {
            "states_correct_conclusion": self.states_correct_conclusion,
            "conclusion_level": self.conclusion_level,
            "explains_reason_correctly": self.explains_reason_correctly,
            "shows_residual_misconception": self.shows_residual_misconception,
            "shows_uncertainty": self.shows_uncertainty,
            "parrots_teacher": self.parrots_teacher,
            "transfer_success": self.transfer_success,
            "evidence_level": self.evidence_level,
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
            marker in normalized for marker in ("截距", "位置", "上下", "上移", "向上", "下移", "平移")
        )
        residual = _has_residual_misconception(normalized, teacher_normalized)
        uncertainty = any(marker in normalized for marker in _UNCERTAINTY_MARKERS)
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
        )
        if transfer and explains_reason and not uncertainty:
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
        )


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。！？、,:：；;（）()]+", "", text.lower())


def _has_residual_misconception(response: str, teacher_text: str) -> bool:
    stability_markers = ("不变", "不影响", "一样陡", "相同", "不会变陡", "没有变陡")
    positive_residual_markers = ("更陡", "越陡", "变陡", "会陡", "有点陡")
    if any(marker in response for marker in stability_markers) and not any(
        marker in response for marker in positive_residual_markers
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
