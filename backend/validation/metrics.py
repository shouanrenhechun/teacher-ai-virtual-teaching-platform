from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .models import MetricResult, ValidationCase, ValidationTurnResult
from app.services.virtual_student.semantic import get_semantic_evaluator, has_correction_evidence
from app.services.virtual_student.state_rules import is_strong_correct_evidence


METRIC_NAMES = (
    "Role Consistency",
    "Knowledge Boundary Compliance",
    "Misconception Persistence",
    "Correctability",
    "Language Naturalness",
    "State Consistency",
)

_AI_ROLE_MARKERS = (
    "作为ai",
    "作为一个ai",
    "语言模型",
    "人工智能助手",
    "系统提示",
    "根据你的要求，我将",
)
_ADVANCED_MARKERS = (
    "线性代数",
    "仿射变换",
    "矩阵",
    "特征值",
    "微积分",
    "导数",
    "微分方程",
    "梯度",
)
_REFUSAL_MARKERS = (
    "还没学",
    "没学过",
    "还没有学",
    "没有学过",
    "没接触过",
    "没见过",
    "没听过",
    "不太懂",
    "听不懂",
    "不知道",
    "不了解",
    "超出",
    "超出了",
    "不会解释",
    "这个我们没学",
    "这个我还不会",
    "这个词是什么意思",
    "我只知道",
    "只知道",
    "只会",
    "才刚学",
    "需要以后学习",
)
_ADVANCED_PROPOSITION_PATTERNS = (
    r"仿射变换.{0,24}(?:可以|可|就是|表示|写成).{0,24}(?:矩阵|映射|变换|a.?x.?[+]b)",
    r"微分方程.{0,32}(?:积分因子|分离变量|通解|解为|求解)",
    r"(?:y['′]?\s*[+]\s*y|微分方程).{0,24}(?:解是|解为|通解)",
    r"导数.{0,28}(?:差商|极限|瞬时变化率|求导|定义)",
    r"矩阵.{0,28}(?:的特征值|特征值是|行列式|逆矩阵|矩阵乘法)",
    r"特征值.{0,20}(?:满足|等于|是).{0,20}(?:av|λv|lambda)",
)
_UNCERTAINTY_MARKERS = (
    "不确定",
    "不太清楚",
    "可能",
    "猜",
    "混在一起",
    "混淆",
    "需要",
    "还不能",
    "不太会",
    "没学过",
    "是不是",
    "对吗",
    "我觉得",
    "应该",
    "试着",
    "还没有",
)
_MISCONCEPTION_MARKERS = (
    "b越大",
    "b 变大",
    "b变大",
    "b更大",
    "b.*陡",
    "b.*倾斜",
    "斜率变大",
    "把.*混在",
    "混淆",
)
_CORRECT_CONCEPT_MARKERS = (
    "b不影响斜率",
    "b 不影响斜率",
    "只改变截距",
    "只决定与 y 轴交点",
    "上下移动",
    "位置不同",
)
_STRONG_CERTAINTY_MARKERS = (
    "完全明白",
    "非常简单",
    "当然就是",
    "我很确定",
    "毫无问题",
)


@dataclass(frozen=True)
class BoundaryEvidence:
    """Small, explainable evidence object used only by validation metrics."""

    acknowledges_unknown: bool
    acknowledges_not_learned: bool
    asks_for_explanation: bool
    retreats_to_known_scope: bool
    speculates_from_known_scope: bool
    demonstrates_out_of_scope_knowledge: bool
    scope_level: str = "unknown"

    @property
    def refusal_observed(self) -> bool:
        return (
            self.acknowledges_unknown
            or self.acknowledges_not_learned
            or self.asks_for_explanation
            or self.retreats_to_known_scope
        )

    @property
    def compliant(self) -> bool:
        return self.refusal_observed and not self.demonstrates_out_of_scope_knowledge


def analyze_boundary_evidence(response: str) -> BoundaryEvidence:
    """Interpret natural boundary language without treating advanced terms alone as violations."""
    advanced = any(marker in response for marker in _ADVANCED_MARKERS)
    acknowledges_not_learned = _contains_any(
        response,
        (
            "还没学",
            "没学过",
            "还没有学",
            "没有学过",
            "没接触过",
            "没见过",
            "没听过",
            "才刚学",
        ),
    )
    acknowledges_unknown = _contains_any(
        response,
        (
            "不知道",
            "不清楚",
            "不太清楚",
            "不了解",
            "不太懂",
            "不明白",
            "没听过",
            "没见过",
        ),
    )
    asks_for_explanation = _contains_any(
        response,
        ("这个词是什么意思", "什么意思", "是什么", "听不懂", "没听过"),
    )
    retreats_to_known_scope = _contains_any(
        response,
        ("我只知道", "只知道", "只会", "目前只学", "我们才刚学"),
    )
    speculates = _contains_any(
        response,
        ("可能", "也许", "好像", "应该", "不确定", "我觉得", "猜", "是不是", "会不会"),
    )
    detailed_advanced_claim = advanced and any(
        re.search(pattern, response, flags=re.IGNORECASE)
        for pattern in _ADVANCED_PROPOSITION_PATTERNS
    )
    speculative_bridge = bool(
        advanced
        and (acknowledges_not_learned or acknowledges_unknown or asks_for_explanation)
        and speculates
        and _has_speculative_bridge(response)
        and not detailed_advanced_claim
    )
    demonstrates = detailed_advanced_claim and not speculative_bridge
    scope_level = (
        "demonstrated_knowledge"
        if demonstrates
        else "speculative_bridge"
        if speculative_bridge
        else "unknown"
    )
    return BoundaryEvidence(
        acknowledges_unknown=acknowledges_unknown,
        acknowledges_not_learned=acknowledges_not_learned,
        asks_for_explanation=asks_for_explanation,
        retreats_to_known_scope=retreats_to_known_scope,
        speculates_from_known_scope=speculates,
        demonstrates_out_of_scope_knowledge=demonstrates,
        scope_level=scope_level,
    )


def _has_speculative_bridge(response: str) -> bool:
    """Require a cautious link to known-scope ideas, not just hedging."""
    return bool(
        re.search(
            r"(?:是不是|会不会|可能|也许|好像|应该|我觉得|猜).{0,18}"
            r"(?:跟|和|与|有关|关系|变化率|类似)",
            response,
            flags=re.IGNORECASE,
        )
    )


def evaluate_run(
    case: ValidationCase, turns: Sequence[ValidationTurnResult]
) -> dict[str, MetricResult]:
    """Evaluate one run with deterministic rules and engine-state comparison."""
    return {
        "Role Consistency": _role_consistency(turns),
        "Knowledge Boundary Compliance": _knowledge_boundary(case, turns),
        "Misconception Persistence": _misconception_persistence(case, turns),
        "Correctability": _correctability(case, turns),
        "Language Naturalness": _language_naturalness(turns),
        "State Consistency": _state_consistency(turns),
    }


def extract_turn_indicators(
    response: str,
    state_after: dict[str, Any],
    *,
    boundary_expected: bool = False,
) -> dict[str, bool]:
    """Expose lightweight, per-turn evidence alongside aggregate metrics."""
    boundary = analyze_boundary_evidence(response)
    classroom = state_after.get("classroom_state", {})
    misconception = _first_misconception(state_after) or {}
    semantic_evidence = get_semantic_evaluator(
        str(misconception.get("semantic_type", "linear_kb"))
    ).analyze(response, "")
    return {
        "role_consistent": not _contains_any(
            response.lower().replace(" ", ""), _AI_ROLE_MARKERS
        ),
        "knowledge_boundary_compliant": (
            boundary.compliant if boundary_expected else not boundary.demonstrates_out_of_scope_knowledge
        ),
        "boundary_refusal_observed": (
            boundary.refusal_observed if boundary_expected else not boundary.demonstrates_out_of_scope_knowledge
        ),
        "boundary_acknowledges_unknown": boundary.acknowledges_unknown,
        "boundary_acknowledges_not_learned": boundary.acknowledges_not_learned,
        "boundary_asks_for_explanation": boundary.asks_for_explanation,
        "boundary_retreated_to_known_scope": boundary.retreats_to_known_scope,
        "boundary_speculates_from_known_scope": boundary.speculates_from_known_scope,
        "boundary_scope_level": boundary.scope_level,
        "boundary_demonstrates_out_of_scope_knowledge": boundary.demonstrates_out_of_scope_knowledge,
        "correctness": (
            semantic_evidence.states_correct_conclusion
            and not semantic_evidence.shows_residual_misconception
        ),
        "misconception_observed": semantic_evidence.shows_residual_misconception,
        "state_marked_corrected": bool(misconception.get("corrected", False)),
        "low_confidence_or_confused": float(classroom.get("confusion", 0.0)) >= 0.45
        or float(classroom.get("understanding", 1.0)) <= 0.65,
    }


def _role_consistency(turns: Sequence[ValidationTurnResult]) -> MetricResult:
    failures: list[str] = []
    for turn in turns:
        response = turn.student_response.strip()
        lowered = response.lower().replace(" ", "")
        if not response:
            failures.append(f"第{turn.sequence}轮回答为空")
        if any(marker in lowered for marker in _AI_ROLE_MARKERS):
            failures.append(f"第{turn.sequence}轮出现 AI/系统身份表述")
        if "请你作为老师" in response or "建议教师" in response:
            failures.append(f"第{turn.sequence}轮语气转为教师/助手")
    if failures:
        return MetricResult(False, True, "角色一致性失败", tuple(failures))
    return MetricResult(True, True, "回答持续使用学生口吻，未出现明显 AI 或教师身份表述")


def _knowledge_boundary(
    case: ValidationCase, turns: Sequence[ValidationTurnResult]
) -> MetricResult:
    failures: list[str] = []
    refusal_expected = case.expectations.get("boundary_refusal", False)
    for turn in turns:
        response = turn.student_response
        boundary = analyze_boundary_evidence(response)
        advanced = [marker for marker in _ADVANCED_MARKERS if marker in response]
        if boundary.demonstrates_out_of_scope_knowledge:
            failures.append(
                f"第{turn.sequence}轮直接使用超纲术语：{', '.join(advanced)}"
            )
        if refusal_expected and not boundary.refusal_observed:
            failures.append(f"第{turn.sequence}轮未明确承认尚未学习该内容")
    if failures:
        return MetricResult(False, True, "知识边界遵守失败", tuple(failures))
    if refusal_expected:
        return MetricResult(True, True, "超纲问题得到符合年级边界的拒答或降级回答")
    return MetricResult(True, True, "未检测到未经解释的明显超纲知识")


def _misconception_persistence(
    case: ValidationCase, turns: Sequence[ValidationTurnResult]
) -> MetricResult:
    expected = case.expectations.get("misconception_should_persist")
    if expected is not True:
        return MetricResult(False, False, "本案例不要求在未纠正阶段验证错误认知保持")

    failures: list[str] = []
    observed = False
    for turn in turns:
        misconception = _first_misconception(turn.state_before)
        if not misconception or misconception.get("corrected"):
            continue
        response = turn.student_response
        evidence = turn.student_response_evidence
        if "shows_residual_misconception" in evidence:
            # StudentResponseEvidenceAnalyzer is the calibrated semantic source.
            observed_in_turn = bool(evidence.get("shows_residual_misconception"))
        else:
            observed_in_turn = _fallback_misconception_observed(response)
        if observed_in_turn:
            observed = True
        if _is_surface_correct_recall(turn, turns):
            # A direct-answer echo is evidence that mastery is still unproven,
            # even when the student does not verbalize the old error again.
            observed = True
            continue
        if _is_correct_response(case.misconception_type, response, turn.teacher_input) and not _contains_any(
            response, _UNCERTAINTY_MARKERS
        ):
            failures.append(f"第{turn.sequence}轮在未纠正时自信给出正确结论")

    if failures:
        return MetricResult(False, True, "错误认知在未有效纠正前过早消失", tuple(failures))
    if not observed:
        return MetricResult(False, True, "未观察到预设的错误认知或合理犹豫表达")
    return MetricResult(True, True, "未纠正阶段保持错误认知或表现出与之相符的犹豫")


def _correctability(
    case: ValidationCase, turns: Sequence[ValidationTurnResult]
) -> MetricResult:
    if case.expectations.get("correctable") is not True:
        return MetricResult(False, False, "本案例不要求验证有效教学后的可纠正性")
    if not turns:
        return MetricResult(False, True, "没有可评估的教学轮次")

    before = _first_misconception(turns[0].state_before)
    after = _first_misconception(turns[-1].state_after)
    if not before or not after:
        return MetricResult(False, True, "缺少认知错误状态，无法验证可纠正性")

    initial_strength = float(before.get("strength", 0.0))
    final_strength = float(after.get("strength", 0.0))
    final_status = str(after.get("status", "active"))
    if initial_strength <= 0.5:
        return MetricResult(False, True, "初始认知错误强度不足，无法验证有效纠正", level="fail")
    strength_series = [
        float((_first_misconception(turn.state_after) or {}).get("strength", 0.0))
        for turn in turns
    ]
    decreases = sum(
        1 for previous, current in zip([initial_strength, *strength_series], strength_series)
        if current < previous
    )
    effective_behaviors = sum(
        1
        for turn in turns
        if turn.behavior in {"targeted_correction", "effective_example", "effective_question"}
    )
    correction_markers = sum(
        1
        for turn in turns
        if has_correction_evidence(case.misconception_type, turn.teacher_input)
        or _is_correct_response(case.misconception_type, turn.student_response, turn.teacher_input)
    )
    observed_initial_error = any(
        bool(turn.student_response_evidence.get("shows_residual_misconception"))
        or bool((_first_misconception(turn.state_after) or {}).get("triggered"))
        for turn in turns
    )
    if not observed_initial_error:
        return MetricResult(False, True, "没有从学生回答中观察到初始认知错误", level="fail")
    if effective_behaviors < 2 or final_strength >= initial_strength or decreases < 2:
        return MetricResult(
            False,
            True,
            "有效教学轨迹没有形成足够的认知进步证据",
            (f"strength {initial_strength:.2f} -> {final_strength:.2f}",),
            level="fail",
        )
    if correction_markers == 0:
        return MetricResult(False, True, "状态降低但未观察到对应的纠正证据", level="fail")
    if _premature_correction(turns):
        return MetricResult(False, True, "在稳定纠正证据不足前过早标记为 corrected", level="fail")
    transfer_observed = any(
        bool(turn.student_response_evidence.get("transfer_success")) for turn in turns
    )
    if final_status == "corrected":
        final_misconception = _first_misconception(turns[-1].state_after) or {}
        cumulative_strong_evidence = sum(
            1 for turn in turns if is_strong_correct_evidence(turn.student_response_evidence)
        )
        if (
            cumulative_strong_evidence < 2
            or not transfer_observed
            or int(final_misconception.get("stable_correct_evidence_count", 0)) < 2
            or int(final_misconception.get("transfer_evidence", 0)) < 1
            or bool(turns[-1].student_response_evidence.get("shows_residual_misconception"))
        ):
            return MetricResult(
                False,
                True,
                "状态标记为 corrected，但缺少完整学生响应证据",
                level="fail",
            )
        return MetricResult(
            True,
            True,
            "学生独立解释并完成变式迁移，认知错误已满足纠正门槛",
            (f"strength {initial_strength:.2f} -> {final_strength:.2f}",),
            level="pass",
        )
    if final_status in {"weakening", "provisional"}:
        return MetricResult(
            False,
            True,
            "学生已有认知进步，但仍未满足 corrected 的完整证据门槛",
            (f"strength {initial_strength:.2f} -> {final_strength:.2f}", final_status),
            level="partial",
        )
    return MetricResult(False, True, "认知错误仍处于 active，缺少有效修正证据", level="fail")


def _premature_correction(turns: Sequence[ValidationTurnResult]) -> bool:
    """Reject corrected only when its evidence prerequisites are absent."""
    for turn in turns:
        misconception = _first_misconception(turn.state_after) or {}
        if misconception.get("status") != "corrected":
            continue
        had_provisional = any(
            (_first_misconception(previous.state_after) or {}).get("status")
            == "provisional"
            for previous in turns[: turn.sequence - 1]
        )
        if (
            turn.sequence <= 3
            or not had_provisional
            or int(misconception.get("stable_correct_evidence_count", 0)) < 2
            or int(misconception.get("transfer_evidence", 0)) < 1
        ):
            return True
    return False


def _language_naturalness(turns: Sequence[ValidationTurnResult]) -> MetricResult:
    failures: list[str] = []
    responses = [turn.student_response.strip() for turn in turns]
    for turn, response in zip(turns, responses):
        if len(response) > 220:
            failures.append(f"第{turn.sequence}轮超过 220 字，可能过度冗长")
        if response.count("老师") >= 3:
            failures.append(f"第{turn.sequence}轮重复称呼过多")
        if response.count("总结") >= 2 or response.count("首先") >= 2:
            failures.append(f"第{turn.sequence}轮出现明显模板化总结")
    if len(responses) >= 2 and len(set(responses)) == 1:
        failures.append("多轮回答完全重复")
    if failures:
        return MetricResult(False, True, "语言自然度存在明显问题", tuple(failures))
    return MetricResult(True, True, "回答长度、口吻和轮次变化基本符合中学生课堂表达")


def _state_consistency(turns: Sequence[ValidationTurnResult]) -> MetricResult:
    failures: list[str] = []
    for turn in turns:
        state = turn.state_after.get("classroom_state", {})
        response = turn.student_response
        confusion = float(state.get("confusion", 0.0))
        understanding = float(state.get("understanding", 1.0))
        misconception = _first_misconception(turn.state_after) or {}
        if (
            (confusion >= 0.6 or understanding <= 0.45)
            and _contains_any(response, _STRONG_CERTAINTY_MARKERS)
            and not _contains_any(response, _UNCERTAINTY_MARKERS)
        ):
            failures.append(f"第{turn.sequence}轮高困惑/低理解状态与强确定语气冲突")
        if (
            float(misconception.get("strength", 0.0)) >= 0.6
            and not misconception.get("corrected", False)
            and not misconception.get("correction_started", False)
            and _is_correct_response(
                str(misconception.get("semantic_type", "linear_kb")),
                response,
                turn.teacher_input,
            )
            and not _contains_any(response, _UNCERTAINTY_MARKERS)
        ):
            failures.append(f"第{turn.sequence}轮未纠正错误认知却自信表达正确结论")
        evidence = turn.student_response_evidence
        prior_transfer = any(
            bool(previous.student_response_evidence.get("transfer_success"))
            for previous in turns[: turn.sequence - 1]
        )
        if misconception.get("status") == "corrected" and (
            evidence.get("shows_residual_misconception")
            or (not evidence.get("transfer_success") and not prior_transfer)
        ):
            failures.append(f"第{turn.sequence}轮状态标记 corrected，但学生回答仍缺少稳定纠正证据")
    if failures:
        return MetricResult(False, True, "自然语言回答与后端课堂状态存在冲突", tuple(failures))
    return MetricResult(True, True, "自然语言回答与 understanding、confusion 和 misconception 状态一致")


def _is_surface_correct_recall(
    turn: ValidationTurnResult | None,
    turns: Sequence[ValidationTurnResult],
) -> bool:
    """Identify direct-answer recall without treating it as conceptual correction."""
    if turn is None:
        return False
    direct_answer_seen = any(
        previous.behavior == "direct_answer"
        for previous in turns[: turn.sequence]
    )
    if not direct_answer_seen:
        return False
    misconception = _first_misconception(turn.state_after) or {}
    evidence = turn.student_response_evidence
    return (
        bool(evidence.get("states_correct_conclusion"))
        and bool(evidence.get("evidence_insufficient"))
        and not bool(evidence.get("shows_residual_misconception"))
        and misconception.get("status") in {"active", "weakening"}
        and int(misconception.get("stable_correct_evidence_count", 0)) == 0
        and int(misconception.get("transfer_evidence", 0)) == 0
        and not any(
            bool(previous.student_response_evidence.get("transfer_success"))
            for previous in turns[: max(0, turn.sequence - 1)]
        )
    )


def summarize_metrics(
    runs: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for name in METRIC_NAMES:
        applicable = [
            run["metrics"][name]
            for run in runs
            if name in run.get("metrics", {}) and run["metrics"][name].get("applicable")
        ]
        passed = sum(1 for item in applicable if item.get("passed"))
        total = len(applicable)
        summary[name] = {
            "passed": passed,
            "total": total,
            "rate": round(passed / total, 4) if total else None,
            "partial": sum(1 for item in applicable if item.get("level") == "partial"),
        }
    return summary


def _first_misconception(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    misconceptions = snapshot.get("misconceptions", [])
    return misconceptions[0] if misconceptions else None


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    return any(marker in text for marker in markers)


def _contains_any_pattern(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _is_correct_response(semantic_type: str, response: str, teacher_text: str = "") -> bool:
    evidence = get_semantic_evaluator(semantic_type).analyze(response, teacher_text)
    return evidence.states_correct_conclusion and not evidence.shows_residual_misconception


def _fallback_misconception_observed(response: str) -> bool:
    """Legacy fallback for reports without structured student evidence.

    A bare "不知道" is not evidence that the target misconception was exposed.
    "不知道为什么" or a concept-specific hesitation can still be evidence.
    """
    normalized = re.sub(r"[\s。！？!?，,、…]+", "", response).lower()
    if normalized in {"不知道", "我不知道", "不清楚", "我不清楚", "不太清楚", "不太懂"}:
        return False
    return _contains_any_pattern(response, _MISCONCEPTION_MARKERS) or _contains_any(
        response, _UNCERTAINTY_MARKERS
    )
