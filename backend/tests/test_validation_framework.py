from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.llm.base import LLMClient, LLMContext, LLMServiceError
from app.services.llm.mock import MockLLMClient
from validation.case_loader import load_validation_cases
from validation.metrics import analyze_boundary_evidence, evaluate_run
from validation.runner import (
    RealValidationDisabledError,
    ValidationConfig,
    run_validation,
    write_report,
)
from validation.models import ValidationTurnResult


def test_validation_cases_cover_required_categories() -> None:
    cases = load_validation_cases()
    assert len(cases) == 30
    assert sum(case.misconception_type == "binomial_square" for case in cases) == 11
    categories = {case.category for case in cases}
    assert {
        "普通开场",
        "直接询问错误知识点",
        "教师直接告诉答案",
        "启发式纠正",
        "追问理解",
        "教师错误讲解",
        "超纲诱导",
        "课堂无关问题",
        "多轮：无有效纠正",
        "多轮：有效纠正",
        "多轮：错误教学",
    } <= categories


def test_mock_validation_runs_and_exports_report(tmp_path: Path) -> None:
    cases = load_validation_cases()
    config = ValidationConfig(
        provider="mock",
        model="mock",
        runs_per_case=1,
        report_dir=tmp_path,
    )

    report = run_validation(config, cases, client=MockLLMClient())
    path = write_report(report, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["provider"] == "mock"
    assert payload["basic"]["total_cases"] == 30
    assert payload["basic"]["total_runs"] == 30
    assert payload["basic"]["total_calls"] == 49
    assert payload["basic"]["api_failures"] == 0
    assert payload["overall_metrics"]["Role Consistency"]["total"] == 30
    assert payload["category_metrics"]["多轮：有效纠正"]
    assert payload["failure_cases"]
    assert "LLM_API_KEY" not in path.read_text(encoding="utf-8")


def test_mock_effective_correction_reduces_misconception() -> None:
    case = next(
        case
        for case in load_validation_cases()
        if case.case_id == "trajectory_effective_correction"
    )
    report = run_validation(
        ValidationConfig(provider="mock", model="mock", runs_per_case=1),
        [case],
        client=MockLLMClient(),
    )
    run = report.runs[0]
    assert run["metrics"]["Correctability"]["passed"] is True
    first_strength = run["turns"][0]["state_before"]["misconceptions"][0]["strength"]
    final_strength = run["turns"][-1]["state_after"]["misconceptions"][0]["strength"]
    assert final_strength < first_strength


def test_mock_binomial_square_trajectory_reaches_corrected_state() -> None:
    case = load_validation_cases(case_ids={"binomial_trajectory_effective_correction"})[0]
    report = run_validation(
        ValidationConfig(provider="mock", model="mock", runs_per_case=1),
        [case],
        client=MockLLMClient(),
    )
    run = report.runs[0]
    assert run["successful_calls"] == 8
    assert run["metrics"]["Correctability"]["passed"] is True
    final = run["turns"][-1]["state_after"]["misconceptions"][0]
    assert final["semantic_type"] == "binomial_square"
    assert final["status"] == "corrected"


def test_boundary_rule_accepts_common_spoken_refusal() -> None:
    case = load_validation_cases(case_ids={"out_of_scope_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response="线性代数我们还没学呢，仿射变换是什么我听不懂。",
        state_before={},
        state_after={},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Knowledge Boundary Compliance"]

    assert metric.passed is True


def test_boundary_rule_rejects_refusal_plus_detailed_advanced_explanation() -> None:
    case = load_validation_cases(case_ids={"out_of_scope_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response="我还没学过仿射变换，但它就是把一个图形映射到另一个位置。",
        state_before={},
        state_after={},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Knowledge Boundary Compliance"]

    assert metric.passed is False


@pytest.mark.parametrize(
    ("case_id", "response"),
    [
        (
            "off_topic_01",
            "不太清楚，我们才刚学一次函数，微积分还没见过呢。",
        ),
        (
            "off_topic_02",
            "微分方程？我好像没听过这个词……我只知道一次函数是 y=kx+b。",
        ),
    ],
)
def test_boundary_regressions_accept_natural_unknown_language(
    case_id: str, response: str
) -> None:
    case = load_validation_cases(case_ids={case_id})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response=response,
        state_before={},
        state_after={},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Knowledge Boundary Compliance"]

    assert metric.passed is True


@pytest.mark.parametrize(
    "response",
    [
        "虽然我们没学过微积分，不过导数就是函数变化率，可以用极限定义。",
        "微分方程没学过，但 y'+y=0 的通解是 Ce^-x。",
    ],
)
def test_boundary_rejects_refusal_plus_real_advanced_knowledge(response: str) -> None:
    case = load_validation_cases(case_ids={"off_topic_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response=response,
        state_before={},
        state_after={},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Knowledge Boundary Compliance"]

    assert metric.passed is False


def test_boundary_evidence_explains_natural_refusal() -> None:
    evidence = analyze_boundary_evidence(
        "微分方程？我好像没听过这个词……我只知道一次函数是 y=kx+b。"
    )

    assert evidence.acknowledges_unknown is True
    assert evidence.acknowledges_not_learned is True
    assert evidence.retreats_to_known_scope is True
    assert evidence.demonstrates_out_of_scope_knowledge is False
    assert evidence.compliant is True


def test_misconception_metric_reuses_structured_student_evidence() -> None:
    case = load_validation_cases(case_ids={"direct_question_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response="2好像是让直线倾斜的，3的话……我总觉得3越大直线也会越陡。",
        state_before={"misconceptions": [{"status": "active", "corrected": False}]},
        state_after={"misconceptions": [{"triggered": True, "corrected": False}]},
        behavior="effective_question",
        student_response_evidence={"shows_residual_misconception": True},
    )

    metric = evaluate_run(case, [turn])["Misconception Persistence"]

    assert metric.passed is True


def test_generic_unknown_does_not_expose_misconception() -> None:
    case = load_validation_cases(case_ids={"direct_question_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response="不知道。",
        state_before={"misconceptions": [{"status": "active", "corrected": False}]},
        state_after={"misconceptions": [{"triggered": False, "corrected": False}]},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Misconception Persistence"]

    assert metric.passed is False


@pytest.mark.parametrize(
    "response",
    [
        "线性代数没学过，仿射变换是什么？",
        "微分方程没学过，可能跟变化率有关吧？",
        "矩阵我没学过，我只知道 y=kx+b。",
    ],
)
def test_boundary_allows_unknown_or_known_scope_speculation(response: str) -> None:
    case = load_validation_cases(case_ids={"off_topic_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response=response,
        state_before={},
        state_after={},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Knowledge Boundary Compliance"]

    assert metric.passed is True


@pytest.mark.parametrize(
    "response",
    [
        "线性代数没学过，不过仿射变换可以写成 Ax+b。",
        "微分方程没学过，不过 y'+y=0 的解是 Ce^-x。",
        "导数我们还没学，不过导数在一点就是差商极限。",
    ],
)
def test_boundary_rejects_advanced_knowledge_propositions(response: str) -> None:
    case = load_validation_cases(case_ids={"off_topic_01"})[0]
    turn = ValidationTurnResult(
        sequence=1,
        teacher_input=case.teacher_inputs[0],
        student_response=response,
        state_before={},
        state_after={},
        behavior="neutral",
    )

    metric = evaluate_run(case, [turn])["Knowledge Boundary Compliance"]

    assert metric.passed is False


def test_surface_correct_recall_does_not_fail_persistence() -> None:
    case = load_validation_cases(case_ids={"trajectory_no_correction"})[0]
    turns = [
        ValidationTurnResult(
            sequence=1,
            teacher_input=case.teacher_inputs[0],
            student_response="我觉得 b 越大越陡。",
            state_before={"misconceptions": [{"status": "active", "corrected": False}]},
            state_after={
                "misconceptions": [
                    {"status": "active", "corrected": False, "triggered": True,
                     "strength": 0.8, "stable_correct_evidence_count": 0,
                     "transfer_evidence": 0}
                ]
            },
            behavior="neutral",
            student_response_evidence={"shows_residual_misconception": True},
        ),
        ValidationTurnResult(
            sequence=2,
            teacher_input=case.teacher_inputs[1],
            student_response="一次函数的图像是一条直线。",
            state_before={"misconceptions": [{"status": "active", "corrected": False}]},
            state_after={
                "misconceptions": [
                    {"status": "active", "corrected": False, "triggered": True,
                     "strength": 0.8, "stable_correct_evidence_count": 0,
                     "transfer_evidence": 0}
                ]
            },
            behavior="neutral",
            student_response_evidence={"shows_residual_misconception": True},
        ),
        ValidationTurnResult(
            sequence=4,
            teacher_input=case.teacher_inputs[2],
            student_response="哦……所以陡不陡其实是看 k，b 只是让直线上下移动？",
            state_before={"misconceptions": [{"status": "active", "corrected": False}]},
            state_after={
                "misconceptions": [
                    {"status": "active", "corrected": False, "triggered": False,
                     "strength": 0.8, "stable_correct_evidence_count": 0,
                     "transfer_evidence": 0}
                ]
            },
            behavior="direct_answer",
            student_response_evidence={
                "states_correct_conclusion": True,
                "shows_residual_misconception": False,
                "evidence_insufficient": True,
            },
        ),
    ]

    metric = evaluate_run(case, turns)["Misconception Persistence"]

    assert metric.passed is True


def test_correctability_uses_cumulative_evidence_when_final_field_is_incomplete() -> None:
    case = load_validation_cases(case_ids={"trajectory_effective_correction"})[0]
    strong = {
        "states_correct_conclusion": True,
        "explains_reason_correctly": True,
        "knowledge_precision": "correct",
        "shows_residual_misconception": False,
        "conceptual_uncertainty": False,
        "parrots_teacher": False,
        "transfer_success": True,
    }
    turns = [
        ValidationTurnResult(
            sequence=1,
            teacher_input="在 y=2x+3 中，b 越大是不是越陡？",
            student_response="b 越大越陡。",
            state_before={"misconceptions": [{"strength": 0.8, "status": "active"}]},
            state_after={
                "misconceptions": [{"strength": 0.8, "status": "active", "triggered": True,
                                     "corrected": False, "stable_correct_evidence_count": 0,
                                     "transfer_evidence": 0}]
            },
            behavior="effective_question",
            student_response_evidence={"shows_residual_misconception": True},
        ),
        ValidationTurnResult(
            sequence=2,
            teacher_input="比较两条 k 相同的直线。",
            student_response="k 相同所以一样陡，b 只让它们上下移动。",
            state_before={"misconceptions": [{"strength": 0.8, "status": "active"}]},
            state_after={
                "misconceptions": [{"strength": 0.6, "status": "provisional", "triggered": False,
                                     "corrected": False, "stable_correct_evidence_count": 1,
                                     "transfer_evidence": 1}]
            },
            behavior="effective_question",
            student_response_evidence={**strong},
        ),
        ValidationTurnResult(
            sequence=4,
            teacher_input="请再解释一次。",
            student_response="答案正确，但末轮证据字段不完整。",
            state_before={"misconceptions": [{"strength": 0.6, "status": "provisional"}]},
            state_after={
                "misconceptions": [{"strength": 0.4, "status": "corrected", "triggered": False,
                                     "corrected": True, "stable_correct_evidence_count": 2,
                                     "transfer_evidence": 1}]
            },
            behavior="effective_question",
            student_response_evidence={
                "states_correct_conclusion": True,
                "explains_reason_correctly": True,
                "knowledge_precision": "correct",
                "shows_residual_misconception": False,
                "conceptual_uncertainty": False,
                "parrots_teacher": False,
                "transfer_success": False,
                "evidence_insufficient": True,
            },
        ),
    ]

    metric = evaluate_run(case, turns)["Correctability"]

    assert metric.passed is True


def test_correctability_rejects_corrected_state_with_final_residual_error() -> None:
    case = load_validation_cases(case_ids={"trajectory_effective_correction"})[0]
    turns = [
        ValidationTurnResult(
            sequence=1,
            teacher_input="先观察图像。",
            student_response="b 越大越陡。",
            state_before={"misconceptions": [{"strength": 0.8, "status": "active"}]},
            state_after={"misconceptions": [{"strength": 0.8, "status": "active", "triggered": True}]},
            behavior="effective_question",
            student_response_evidence={"shows_residual_misconception": True},
        ),
        ValidationTurnResult(
            sequence=2,
            teacher_input="比较固定 k 的图像。",
            student_response="k 相同所以一样陡，b 只改变上下位置。",
            state_before={"misconceptions": [{"strength": 0.8, "status": "active"}]},
            state_after={"misconceptions": [{"strength": 0.6, "status": "provisional",
                                               "stable_correct_evidence_count": 1,
                                               "transfer_evidence": 1}]},
            behavior="effective_question",
            student_response_evidence={
                "states_correct_conclusion": True,
                "explains_reason_correctly": True,
                "knowledge_precision": "correct",
                "shows_residual_misconception": False,
                "conceptual_uncertainty": False,
                "parrots_teacher": False,
                "transfer_success": True,
            },
        ),
        ValidationTurnResult(
            sequence=3,
            teacher_input="再判断一次。",
            student_response="但我还是觉得 b 越大越陡。",
            state_before={"misconceptions": [{"strength": 0.6, "status": "provisional"}]},
            state_after={"misconceptions": [{"strength": 0.4, "status": "corrected",
                                               "corrected": True,
                                               "stable_correct_evidence_count": 2,
                                               "transfer_evidence": 1}]},
            behavior="effective_question",
            student_response_evidence={
                "states_correct_conclusion": True,
                "explains_reason_correctly": True,
                "knowledge_precision": "correct",
                "shows_residual_misconception": True,
                "conceptual_uncertainty": True,
                "parrots_teacher": False,
                "transfer_success": False,
            },
        ),
    ]

    metrics = evaluate_run(case, turns)

    assert metrics["Correctability"].passed is False
    assert metrics["State Consistency"].passed is False


def test_real_provider_requires_explicit_safety_switch() -> None:
    config = ValidationConfig(
        provider="real",
        model="test-model",
        runs_per_case=1,
        real_validation_enabled=False,
    )
    case = load_validation_cases(case_ids={"opening_01"})[0]

    with pytest.raises(RealValidationDisabledError):
        run_validation(config, [case], client=MockLLMClient())


def test_prompt_debug_is_off_by_default_and_opt_in(tmp_path: Path) -> None:
    case = load_validation_cases(case_ids={"opening_01"})[0]
    disabled = run_validation(
        ValidationConfig(provider="mock", model="mock", runs_per_case=1),
        [case],
        client=MockLLMClient(),
    )
    enabled = run_validation(
        ValidationConfig(
            provider="mock",
            model="mock",
            runs_per_case=1,
            prompt_debug_enabled=True,
            report_dir=tmp_path,
        ),
        [case],
        client=MockLLMClient(),
    )

    disabled_turn = disabled.runs[0]["turns"][0]
    enabled_turn = enabled.runs[0]["turns"][0]
    assert "sanitized_system_prompt" not in disabled_turn
    assert enabled_turn["prompt_misconception_mode"] == "strong_misconception"
    assert enabled_turn["prompt_misconception_status"] == "active"
    assert enabled_turn["prompt_recent_history_count"] == 0
    assert "LLM_API_KEY" not in enabled_turn["sanitized_system_prompt"]


class FailingValidationClient(LLMClient):
    provider = "real"

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        raise LLMServiceError("模拟模型服务超时")


def test_real_validation_failure_is_saved_without_crashing_suite(tmp_path: Path) -> None:
    case = load_validation_cases(case_ids={"opening_01"})[0]
    config = ValidationConfig(
        provider="real",
        model="test-model",
        runs_per_case=1,
        real_validation_enabled=True,
        report_dir=tmp_path,
    )

    report = run_validation(config, [case], client=FailingValidationClient())

    assert report.failed_runs == 1
    assert report.api_failures == 1
    assert report.failure_cases[0]["case_id"] == "opening_01"
    assert "超时" in report.failure_cases[0]["reason"]
