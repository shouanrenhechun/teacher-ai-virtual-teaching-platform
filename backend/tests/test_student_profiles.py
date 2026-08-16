from __future__ import annotations

from app.services.llm.mock import MockLLMClient
from app.services.llm.base import LLMContext
from app.services.virtual_student import PromptBuilder, VirtualStudentEngine
from validation.case_loader import load_student_profile, load_validation_cases
from validation.runner import ValidationConfig, run_validation


def test_student_a_and_b_share_kb_state_but_have_different_profile_style() -> None:
    student_a = load_student_profile("student_a")
    student_b = load_student_profile("student_b")

    assert student_a.profile_id == "student_a"
    assert student_b.profile_id == "student_b"
    assert student_a.misconceptions[0].semantic_type == "linear_kb"
    assert student_b.misconceptions[0].semantic_type == "linear_kb"
    assert student_a.misconceptions[0].strength == student_b.misconceptions[0].strength == 0.8
    assert student_a.confidence != student_b.confidence
    assert student_b.confirmation_seeking


def test_student_b_prompt_exposes_style_without_new_state_rules() -> None:
    profile = load_student_profile("student_b")
    prompt = PromptBuilder().build(
        VirtualStudentEngine(profile),
        "你觉得两条直线一样陡吗？",
    )

    assert "谨慎低自信" in prompt
    assert "表达上的犹豫不等于概念错误" in prompt
    assert "先确认自己的理解" in prompt
    assert "semantic_type" not in prompt


def test_student_b_mock_reuses_kb_trajectory_and_report_metadata() -> None:
    case = load_validation_cases(case_ids={"trajectory_effective_correction"})[0]
    report = run_validation(
        ValidationConfig(
            provider="mock",
            model="mock",
            runs_per_case=1,
            student_profile_id="student_b",
        ),
        [case],
        client=MockLLMClient(),
    )

    run = report.runs[0]
    assert report.student_profile_id == "student_b"
    assert report.student_profile_name == "学生 B"
    assert run["student_profile_id"] == "student_b"
    assert run["student_profile_name"] == "学生 B"
    assert run["successful_calls"] == 8
    assert run["metrics"]["Correctability"]["passed"] is True
    assert run["turns"][-1]["state_after"]["misconceptions"][0]["status"] == "corrected"


def test_student_b_mock_keeps_boundary_separate_from_low_confidence() -> None:
    client = MockLLMClient()
    response = client.respond(
        "你能从线性代数中的仿射变换角度解释一次函数吗？",
        LLMContext(student_name="学生 B", student_profile_id="student_b"),
    )

    assert "还没学过" in response
    assert "仿射变换" not in response
